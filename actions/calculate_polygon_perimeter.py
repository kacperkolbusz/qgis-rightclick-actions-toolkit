"""
Calculate Polygon Perimeter Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the perimeter of polygon features.
Shows perimeter in appropriate units based on layer CRS.
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager


class CalculatePolygonPerimeterAction(BaseAction):
    """
    Action to calculate and display polygon perimeter.
    
    This action calculates the perimeter of polygon features and displays
    the result in appropriate units based on the layer's coordinate reference system.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_polygon_perimeter"
        self.name = "Calculate Polygon Perimeter"
        self.category = "Analysis"
        self.description = "Calculate and display the perimeter of the selected polygon feature. Shows perimeter in appropriate units based on layer CRS. Displays result in information dialog."
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
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in perimeter calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_crs_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result',
            },
            'show_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature ID',
                'description': 'Display feature ID in the result',
            },
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Display layer name in the result',
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
        Execute the calculate perimeter action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_crs_info = bool(self.get_setting('show_crs_info', True))
            show_feature_id = bool(self.get_setting('show_feature_id', True))
            show_layer_name = bool(self.get_setting('show_layer_name', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements using new universal format
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        if not canvas:
            self.show_error("Error", "Map canvas not available")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get feature geometry
            geometry = feature.geometry()
            if not geometry:
                self.show_error("Error", "Feature has no geometry")
                return
            
            # CRITICAL: Handle CRS transformation for accurate perimeter calculation
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            
            # For perimeter calculations, we need to ensure we're in a projected CRS
            # Geographic CRS (like WGS84) gives perimeter in degrees which is not meaningful
            if layer_crs.isGeographic():
                # Transform to a projected CRS for accurate perimeter calculation
                from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
                
                # Use UTM zone if possible, otherwise Web Mercator
                try:
                    # Try to get UTM zone for the feature centroid
                    centroid = geometry.centroid().asPoint()
                    utm_zone = int((centroid.x() + 180) / 6) + 1
                    hemisphere = 'north' if centroid.y() >= 0 else 'south'
                    utm_epsg = f"EPSG:{32600 + utm_zone}" if hemisphere == 'north' else f"EPSG:{32700 + utm_zone}"
                    projected_crs = QgsCoordinateReferenceSystem(utm_epsg)
                except:
                    # Fallback to Web Mercator
                    projected_crs = QgsCoordinateReferenceSystem("EPSG:3857")
                
                # Transform geometry to projected CRS
                transform = QgsCoordinateTransform(layer_crs, projected_crs, QgsProject.instance())
                geometry.transform(transform)
                calculation_crs = projected_crs
            else:
                # Already in projected CRS
                calculation_crs = layer_crs
            
            # Calculate perimeter
            perimeter = geometry.length()
            
            # Get unit information
            unit_name = "units"
            if calculation_crs.isGeographic():
                unit_name = "degrees"
            else:
                # For projected CRS, get the map units
                try:
                    unit_name = calculation_crs.mapUnits().name().lower()
                except:
                    unit_name = "map units"
            
            # Build result message
            result_parts = []
            
            if show_feature_id:
                result_parts.append(f"Feature ID: {feature.id()}")
            
            if show_layer_name:
                result_parts.append(f"Layer: {layer.name()}")
            
            result_parts.append(f"Perimeter: {perimeter:.{decimal_places}f} {unit_name}")
            
            if show_crs_info:
                result_parts.append(f"Layer CRS: {layer_crs.description()}")
                if layer_crs.isGeographic():
                    result_parts.append(f"Calculation CRS: {calculation_crs.description()} (transformed for accurate measurement)")
            
            result_text = "\n".join(result_parts)
            
            # Show result
            self.show_info("Perimeter Calculation", result_text)
            
            # Record an informational history entry (read-only operation)
            try:
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}

                perimeter_formatted = f"{perimeter:.{decimal_places}f}"

                meta = {
                    'feature_id': feature.id(),
                    'layer': layer_desc,
                    'perimeter': float(perimeter),
                    'perimeter_formatted': perimeter_formatted,
                    'units': unit_name,
                    'calculation_crs': calculation_crs.authid() if hasattr(calculation_crs, 'authid') else str(calculation_crs)
                }

                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Calculated perimeter for feature {feature.id()} on layer {layer.name()}",
                    meta=meta
                )
            except Exception:
                # Do not let history recording break the main action
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate perimeter: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_polygon_perimeter_action = CalculatePolygonPerimeterAction()
