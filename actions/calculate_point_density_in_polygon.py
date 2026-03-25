"""
Calculate Point Density in Polygon Action for Right-click Utilities and Shortcuts Hub

Calculates point density within the selected polygon feature.
Shows point counts and densities for each point layer, plus overall density.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsVectorLayer, QgsGeometry, QgsWkbTypes, QgsCoordinateTransform


class CalculatePointDensityInPolygonAction(BaseAction):
    """Action to calculate point density within a polygon feature."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_point_density_in_polygon"
        self.name = "Calculate Point Density in Polygon"
        self.category = "Analysis"
        self.description = "Calculate point density within the selected polygon feature. Shows point counts and densities for each point layer, plus overall density. Density is calculated as points per unit area based on the polygon layer's CRS."
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
            'show_polygon_area': {
                'type': 'bool',
                'default': True,
                'label': 'Show Polygon Area',
                'description': 'Display the polygon area in the result dialog',
            },
            'show_empty_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Show Empty Layers',
                'description': 'Display point layers that have no points within the polygon',
            },
            'show_point_counts': {
                'type': 'bool',
                'default': True,
                'label': 'Show Point Counts',
                'description': 'Display the number of points for each layer',
            },
            'show_densities': {
                'type': 'bool',
                'default': True,
                'label': 'Show Densities',
                'description': 'Display point density (points per unit area) for each layer',
            },
            'sort_by_density': {
                'type': 'bool',
                'default': True,
                'label': 'Sort by Density',
                'description': 'Sort point layers by density (highest first) in the result',
            },
            'show_total_count': {
                'type': 'bool',
                'default': True,
                'label': 'Show Total Count',
                'description': 'Display the total number of points across all layers',
            },
            'show_overall_density': {
                'type': 'bool',
                'default': True,
                'label': 'Show Overall Density',
                'description': 'Display the overall point density across all layers',
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places for density values',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'include_visible_only': {
                'type': 'bool',
                'default': False,
                'label': 'Visible Layers Only',
                'description': 'Only analyze points from visible point layers',
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
    
    def _get_area_unit_name(self, crs):
        """
        Get the appropriate area unit name for the CRS.
        
        Args:
            crs: QgsCoordinateReferenceSystem
            
        Returns:
            str: Unit name for area (e.g., "square meters", "square degrees")
        """
        if crs.isGeographic():
            return "square degrees"
        elif crs.isValid() and crs.mapUnits() != 0:
            unit_name = crs.mapUnits().name().lower()
            if unit_name == "meters" or unit_name == "meter":
                return "square meters"
            elif unit_name == "feet" or unit_name == "foot":
                return "square feet"
            elif unit_name == "us feet" or unit_name == "us foot":
                return "square US feet"
            else:
                return f"square {unit_name}"
        else:
            return "square units"
    
    def _format_density(self, density, decimal_places):
        """
        Format density value intelligently to avoid showing 0.00 for very small values.
        
        Args:
            density (float): Density value to format
            decimal_places (int): Preferred number of decimal places
            
        Returns:
            str: Formatted density string
        """
        if density == 0.0:
            return "0.00"
        
        # If density is very small (< 0.01), use more decimal places to show meaningful value
        if density < 0.01:
            # Use more decimal places to show at least 2 significant digits
            import math
            if density > 0:
                # Calculate decimal places needed to show 2 significant digits
                magnitude = math.floor(math.log10(abs(density)))
                needed_places = abs(magnitude) + 1
                # Cap at reasonable maximum (12 decimal places)
                needed_places = min(needed_places, 12)
                return f"{density:.{needed_places}f}"
        
        # For normal values, use the requested decimal places
        return f"{density:.{decimal_places}f}"
    
    def execute(self, context):
        """Execute the calculate point density in polygon action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            show_feature_id = bool(self.get_setting('show_feature_id', schema['show_feature_id']['default']))
            show_layer_name = bool(self.get_setting('show_layer_name', schema['show_layer_name']['default']))
            show_polygon_area = bool(self.get_setting('show_polygon_area', schema['show_polygon_area']['default']))
            show_empty_layers = bool(self.get_setting('show_empty_layers', schema['show_empty_layers']['default']))
            show_point_counts = bool(self.get_setting('show_point_counts', schema['show_point_counts']['default']))
            show_densities = bool(self.get_setting('show_densities', schema['show_densities']['default']))
            sort_by_density = bool(self.get_setting('sort_by_density', schema['sort_by_density']['default']))
            show_total_count = bool(self.get_setting('show_total_count', schema['show_total_count']['default']))
            show_overall_density = bool(self.get_setting('show_overall_density', schema['show_overall_density']['default']))
            decimal_places = int(self.get_setting('decimal_places', schema['decimal_places']['default']))
            include_visible_only = bool(self.get_setting('include_visible_only', schema['include_visible_only']['default']))
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
            
            # CRITICAL: Handle CRS transformation for accurate area calculation
            # For area calculations, we need to ensure we're in a projected CRS
            # Geographic CRS (like WGS84) gives area in square degrees which is not meaningful
            if polygon_crs.isGeographic():
                # Transform to a projected CRS for accurate area calculation
                from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
                
                # Use UTM zone if possible, otherwise Web Mercator
                try:
                    # Try to get UTM zone for the feature centroid
                    centroid = polygon_geometry.centroid().asPoint()
                    utm_zone = int((centroid.x() + 180) / 6) + 1
                    hemisphere = 'north' if centroid.y() >= 0 else 'south'
                    utm_epsg = f"EPSG:{32600 + utm_zone}" if hemisphere == 'north' else f"EPSG:{32700 + utm_zone}"
                    projected_crs = QgsCoordinateReferenceSystem(utm_epsg)
                except:
                    # Fallback to Web Mercator
                    projected_crs = QgsCoordinateReferenceSystem("EPSG:3857")
                
                # Transform geometry to projected CRS for area calculation
                geometry_for_area = QgsGeometry(polygon_geometry)
                transform = QgsCoordinateTransform(polygon_crs, projected_crs, QgsProject.instance())
                try:
                    geometry_for_area.transform(transform)
                    calculation_crs = projected_crs
                except Exception as e:
                    # If transformation fails, use original CRS (will have wrong units)
                    geometry_for_area = polygon_geometry
                    calculation_crs = polygon_crs
            else:
                # Already in projected CRS
                geometry_for_area = polygon_geometry
                calculation_crs = polygon_crs
            
            # Calculate polygon area in calculation CRS
            polygon_area = geometry_for_area.area()
            
            if polygon_area <= 0:
                self.show_error("Error", "Polygon has zero or negative area. Cannot calculate density.")
                return
            
            area_unit_name = self._get_area_unit_name(calculation_crs)
            
            # Get all point layers
            point_layers = self._get_point_layers(include_visible_only)
            
            if not point_layers:
                self.show_warning("No Point Layers", "No point layers found in the project.")
                return
            
            # Count points by layer
            layer_data = {}  # {layer_name: {'count': int, 'density': float}}
            total_count = 0
            
            for point_layer in point_layers:
                layer_name = point_layer.name()
                count = 0
                
                # Get point layer CRS
                point_crs = point_layer.crs()
                
                # Check if CRS transformation is needed (for containment check, use original polygon_crs)
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
                    
                    # Transform point geometry if needed (to polygon_crs for containment check)
                    if needs_transformation:
                        try:
                            point_geometry.transform(transform)
                        except Exception as e:
                            # Skip points that can't be transformed
                            continue
                    
                    # Check if point is within polygon (using original polygon geometry)
                    if polygon_geometry.contains(point_geometry):
                        count += 1
                
                # Calculate density for this layer (using area in calculation_crs)
                density = count / polygon_area if polygon_area > 0 else 0.0
                
                # Store data for this layer
                if count > 0 or show_empty_layers:
                    layer_data[layer_name] = {
                        'count': count,
                        'density': density
                    }
                    total_count += count
            
            # Calculate overall density
            overall_density = total_count / polygon_area if polygon_area > 0 else 0.0
            
            # Build result message
            result_lines = []
            
            if show_feature_id:
                result_lines.append(f"Polygon Feature ID: {feature.id()}")
            
            if show_layer_name:
                result_lines.append(f"Polygon Layer: {layer.name()}")
            
            if show_polygon_area:
                result_lines.append(f"Polygon Area: {polygon_area:.{decimal_places}f} {area_unit_name}")
            
            result_lines.append("")
            
            if show_total_count:
                result_lines.append(f"Total Points: {total_count}")
            
            if show_overall_density:
                formatted_density = self._format_density(overall_density, decimal_places)
                result_lines.append(f"Overall Density: {formatted_density} points per {area_unit_name}")
            
            result_lines.append("")
            
            if not layer_data:
                result_lines.append("No points found within this polygon.")
            else:
                result_lines.append("Points by Layer:")
                result_lines.append("")
                
                # Sort by density or name
                if sort_by_density:
                    sorted_layers = sorted(layer_data.items(), key=lambda x: x[1]['density'], reverse=True)
                else:
                    sorted_layers = sorted(layer_data.items(), key=lambda x: x[0])
                
                for layer_name, data in sorted_layers:
                    count = data['count']
                    density = data['density']
                    
                    layer_line = f"  • {layer_name}:"
                    
                    if show_point_counts:
                        layer_line += f" {count} point{'s' if count != 1 else ''}"
                    
                    if show_point_counts and show_densities:
                        layer_line += " |"
                    
                    if show_densities:
                        formatted_density = self._format_density(density, decimal_places)
                        layer_line += f" Density: {formatted_density} points per {area_unit_name}"
                    
                    result_lines.append(layer_line)
            
            result_text = "\n".join(result_lines)
            
            # Show result
            self.show_info("Point Density in Polygon", result_text)
            
            # Record informational history entry with JSON-serializable metadata
            try:
                from ..history_manager import get_history_manager
                hm = get_history_manager()

                # Build per-layer summary metadata (serialize names, counts, densities)
                layers_meta = []
                for lname, data in layer_data.items():
                    try:
                        layers_meta.append({
                            'layer_name': str(lname),
                            'count': int(data.get('count', 0)),
                            'density': float(data.get('density', 0.0))
                        })
                    except Exception:
                        layers_meta.append({'layer_name': str(lname), 'count': data.get('count'), 'density': data.get('density')})

                meta_info = {
                    'polygon_feature_id': int(feature.id()),
                    'polygon_layer': hm.create_layer_descriptor(layer),
                    'polygon_area': float(polygon_area),
                    'area_unit': area_unit_name,
                    'total_count': int(total_count),
                    'overall_density': float(overall_density),
                    'layers': layers_meta,
                    'parameters': {
                        'include_visible_only': bool(include_visible_only),
                        'sort_by_density': bool(sort_by_density),
                        'show_empty_layers': bool(show_empty_layers)
                    }
                }

                description = f"Calculated point densities for polygon {feature.id()} on layer {layer.name()}"
                hm.record_informational(self.action_id, self.name, description, meta=meta_info)
            except Exception:
                # Continue silently if history manager unavailable
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate point density: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_point_density_in_polygon_action = CalculatePointDensityInPolygonAction()

