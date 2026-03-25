"""
Count Points in Polygon Action for Right-click Utilities and Shortcuts Hub

Counts how many point features are within the selected polygon feature.
Shows which layers the points belong to and how many points are in each layer.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsVectorLayer, QgsGeometry, QgsWkbTypes, QgsCoordinateTransform
from ..history_manager import get_history_manager


class CountPointsInPolygonAction(BaseAction):
    """Action to count point features within a polygon feature."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "count_points_in_polygon"
        self.name = "Count Points in Polygon"
        self.category = "Analysis"
        self.description = "Count how many point features are within the selected polygon feature. Shows which layers the points belong to and how many points are in each layer. Works with all point layers in the project and handles CRS transformations automatically."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # DISPLAY SETTINGS - Easy to customize output format
            'show_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature ID',
                'description': 'Display the polygon feature ID in the result dialog',
            },
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Display the polygon layer name in the result dialog',
            },
            'show_empty_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Show Empty Layers',
                'description': 'Display point layers that have no points within the polygon',
            },
            'sort_by_count': {
                'type': 'bool',
                'default': True,
                'label': 'Sort by Count',
                'description': 'Sort point layers by count (highest first) in the result',
            },
            'show_total_count': {
                'type': 'bool',
                'default': True,
                'label': 'Show Total Count',
                'description': 'Display the total number of points across all layers',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'include_visible_only': {
                'type': 'bool',
                'default': False,
                'label': 'Visible Layers Only',
                'description': 'Only count points from visible point layers',
            },
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a brief success message after counting',
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """
        Get a setting value for this action.
        
        Args:
            setting_name (str): Name of the setting to retrieve
            default_value: Default value if setting not found
            
        Returns:
            Setting value or default_value
        """
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def _get_point_layers(self, include_visible_only=False):
        """
        Get all point layers from the project.
        
        Args:
            include_visible_only (bool): If True, only return visible layers
            
        Returns:
            list: List of QgsVectorLayer objects that are point layers
        """
        project = QgsProject.instance()
        point_layers = []
        
        for layer_id, layer in project.mapLayers().items():
            # Check if it's a vector layer
            if not isinstance(layer, QgsVectorLayer):
                continue
            
            # Check if it's a point layer
            if layer.geometryType() != QgsWkbTypes.PointGeometry:
                continue
            
            # Check if layer is valid
            if not layer.isValid():
                continue
            
            # Check visibility if requested
            if include_visible_only:
                root = project.layerTreeRoot()
                layer_tree_layer = root.findLayer(layer_id)
                if not layer_tree_layer or not layer_tree_layer.isVisible():
                    continue
            
            point_layers.append(layer)
        
        return point_layers
    
    def execute(self, context):
        """Execute the count points in polygon action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            show_feature_id = bool(self.get_setting('show_feature_id', schema['show_feature_id']['default']))
            show_layer_name = bool(self.get_setting('show_layer_name', schema['show_layer_name']['default']))
            show_empty_layers = bool(self.get_setting('show_empty_layers', schema['show_empty_layers']['default']))
            sort_by_count = bool(self.get_setting('sort_by_count', schema['sort_by_count']['default']))
            show_total_count = bool(self.get_setting('show_total_count', schema['show_total_count']['default']))
            include_visible_only = bool(self.get_setting('include_visible_only', schema['include_visible_only']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get feature geometry
            polygon_geometry = feature.geometry()
            if not polygon_geometry:
                self.show_error("Error", "Feature has no geometry")
                return
            
            if polygon_geometry.isEmpty():
                self.show_error("Error", "Feature has empty geometry")
                return
            
            # Get polygon layer CRS
            polygon_crs = layer.crs()
            
            # Get all point layers
            point_layers = self._get_point_layers(include_visible_only)
            
            if not point_layers:
                self.show_warning("No Point Layers", "No point layers found in the project.")
                return
            
            # Count points by layer
            layer_counts = {}  # {layer_name: count}
            total_count = 0
            
            for point_layer in point_layers:
                layer_name = point_layer.name()
                count = 0
                
                # Get point layer CRS
                point_crs = point_layer.crs()
                
                # Check if CRS transformation is needed
                needs_transformation = polygon_crs != point_crs
                
                if needs_transformation:
                    try:
                        transform = QgsCoordinateTransform(point_crs, polygon_crs, QgsProject.instance())
                    except Exception as e:
                        self.show_warning("CRS Warning", f"Could not create CRS transformation for layer '{layer_name}': {str(e)}. Skipping this layer.")
                        continue
                
                # Iterate through all points in the layer
                for point_feature in point_layer.getFeatures():
                    point_geometry = point_feature.geometry()
                    if not point_geometry or point_geometry.isEmpty():
                        continue
                    
                    # Transform point geometry if needed
                    if needs_transformation:
                        try:
                            point_geometry.transform(transform)
                        except Exception as e:
                            # Skip points that can't be transformed
                            continue
                    
                    # Check if point is within polygon
                    # Use contains() for strict containment, or intersects() for any overlap
                    # We'll use contains() to match "within" requirement
                    if polygon_geometry.contains(point_geometry):
                        count += 1
                
                # Store count for this layer
                if count > 0 or show_empty_layers:
                    layer_counts[layer_name] = count
                    total_count += count
            
            # Build result message
            result_lines = []
            
            if show_feature_id:
                result_lines.append(f"Polygon Feature ID: {feature.id()}")
            
            if show_layer_name:
                result_lines.append(f"Polygon Layer: {layer.name()}")
            
            result_lines.append("")
            
            if show_total_count:
                result_lines.append(f"Total Points: {total_count}")
                result_lines.append("")
            
            if not layer_counts:
                result_lines.append("No points found within this polygon.")
            else:
                result_lines.append("Points by Layer:")
                result_lines.append("")
                
                # Sort by count if requested
                if sort_by_count:
                    sorted_layers = sorted(layer_counts.items(), key=lambda x: x[1], reverse=True)
                else:
                    sorted_layers = sorted(layer_counts.items(), key=lambda x: x[0])
                
                for layer_name, count in sorted_layers:
                    result_lines.append(f"  • {layer_name}: {count} point{'s' if count != 1 else ''}")
            
            result_text = "\n".join(result_lines)
            
            # Show result
            self.show_info("Points in Polygon", result_text)
            
            # Show success message if requested
            if show_success_message and total_count > 0:
                self.show_info("Success", f"Found {total_count} point{'s' if total_count != 1 else ''} within the polygon.")
            
            # Record informational history entry (read-only operation)
            try:
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}

                meta = {
                    'feature_id': feature.id(),
                    'polygon_layer': layer_desc,
                    'total_count': int(total_count),
                    'counts_by_layer': layer_counts,
                    'settings': {
                        'show_empty_layers': bool(show_empty_layers),
                        'sort_by_count': bool(sort_by_count),
                        'include_visible_only': bool(include_visible_only),
                    }
                }

                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Counted points within polygon feature {feature.id()} on layer {layer.name()}",
                    meta=meta
                )
            except Exception:
                # History recording must not break the main action
                pass
        except Exception as e:
            self.show_error("Error", f"Failed to count points: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
count_points_in_polygon_action = CountPointsInPolygonAction()

