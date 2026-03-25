"""
Calculate Polygon to Nearest Polygon Distance Action for Right-click Utilities and Shortcuts Hub

Calculates the distance from the selected polygon feature to the nearest polygon feature in the same layer.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY
from ..history_manager import get_history_manager


class CalculatePolygonToNearestPolygonAction(BaseAction):
    """
    Action to calculate distance from selected polygon to nearest polygon in same layer.
    
    This action finds the nearest polygon feature in the same layer and calculates
    the distance between them, displaying the result in appropriate units.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_polygon_to_nearest_polygon"
        self.name = "Calculate Distance to Nearest Polygon"
        self.category = "Analysis"
        self.description = "Calculate the distance from the selected polygon feature to the nearest polygon feature in the same layer. Shows distance in appropriate units based on layer CRS."
        self.enabled = True
        
        # Action scoping configuration - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'nearest_features_count': {
                'type': 'int',
                'default': 5,
                'label': 'Number of Nearest Features',
                'description': 'Number of nearest features to find and display',
                'min': 1,
                'max': 50,
                'step': 1,
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in distance calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_nearest_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature IDs',
                'description': 'Display the IDs of the nearest features in the result',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result',
            },
            'exclude_self': {
                'type': 'bool',
                'default': True,
                'label': 'Exclude Self',
                'description': 'Exclude the clicked feature from nearest feature search',
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
    
    def execute(self, context):
        """
        Execute the calculate distance to nearest polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            nearest_features_count = int(self.get_setting('nearest_features_count', 5))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_nearest_feature_id = bool(self.get_setting('show_nearest_feature_id', True))
            show_crs_info = bool(self.get_setting('show_crs_info', True))
            exclude_self = bool(self.get_setting('exclude_self', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        # Get the clicked feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get clicked feature geometry
            clicked_geometry = feature.geometry()
            if not clicked_geometry:
                self.show_error("Error", "Clicked feature has no geometry")
                return
            
            # Find nearest polygon features in the same layer
            feature_distances = []
            
            # Iterate through all features in the layer
            for other_feature in layer.getFeatures():
                # Skip self if exclude_self is enabled
                if exclude_self and other_feature.id() == feature.id():
                    continue
                
                other_geometry = other_feature.geometry()
                if not other_geometry:
                    continue
                
                # Calculate distance between geometries
                distance = clicked_geometry.distance(other_geometry)
                
                # Store feature and distance
                feature_distances.append((other_feature, distance))
            
            if not feature_distances:
                self.show_warning("No Other Features", "No other polygon features found in this layer.")
                return
            
            # Sort by distance and take the requested number of nearest features
            feature_distances.sort(key=lambda x: x[1])
            nearest_features = feature_distances[:nearest_features_count]
            
            # Get layer CRS for units
            crs = layer.crs()
            unit_name = "units"
            if crs.isGeographic():
                unit_name = "degrees"
            elif crs.isValid() and crs.mapUnits() != 0:  # 0 = Unknown units
                unit_name = crs.mapUnits().name().lower()
            
            # Build result message
            result_parts = []
            result_parts.append(f"From Feature ID: {feature.id()}")
            result_parts.append(f"Found {len(nearest_features)} nearest polygon features:")
            result_parts.append("")
            
            for i, (nearest_feature, distance) in enumerate(nearest_features, 1):
                if show_nearest_feature_id:
                    result_parts.append(f"{i}. Feature ID {nearest_feature.id()}: {distance:.{decimal_places}f} {unit_name}")
                else:
                    result_parts.append(f"{i}. {distance:.{decimal_places}f} {unit_name}")
            
            if show_crs_info:
                result_parts.append("")
                result_parts.append(f"CRS: {crs.description()}")
            
            result_text = "\n".join(result_parts)
            
            # Show result
            self.show_info("Distances to Nearest Polygons", result_text)
            
            # Record informational history entry (read-only)
            try:
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}

                nearest_list = []
                for nf, dist in nearest_features:
                    nearest_list.append({'feature_id': int(nf.id()), 'distance': float(dist)})

                meta = {
                    'feature_id': int(feature.id()),
                    'layer': layer_desc,
                    'nearest': nearest_list,
                    'units': unit_name,
                    'crs': crs.authid() if hasattr(crs, 'authid') else str(crs)
                }

                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Found {len(nearest_list)} nearest polygons for feature {feature.id()} on layer {layer.name()}",
                    meta=meta
                )
            except Exception:
                # History recording must not block the action
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate distance: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_polygon_to_nearest_polygon_action = CalculatePolygonToNearestPolygonAction()
