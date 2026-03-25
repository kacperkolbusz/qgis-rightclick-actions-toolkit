"""
Calculate Polygon Area Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the area of polygon features with proper CRS handling.
Works on polygon and multipolygon features with customizable display options.
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager


class CalculatePolygonAreaAction(BaseAction):
    """Action to calculate and display polygon area with CRS handling."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_polygon_area"
        self.name = "Calculate Polygon Area"
        self.category = "Analysis"
        self.description = "Calculate and display the area of the selected polygon feature. Shows area in appropriate units based on layer CRS. Displays result in information dialog with customizable formatting options."
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
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in area calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature ID',
                'description': 'Display the feature ID in the result dialog',
            },
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Display the layer name in the result dialog',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result dialog',
            },
            'show_units': {
                'type': 'bool',
                'default': True,
                'label': 'Show Units',
                'description': 'Display units (square meters, square degrees, etc.) in the result',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a brief success message after calculation',
            },
            'copy_to_clipboard': {
                'type': 'bool',
                'default': False,
                'label': 'Copy to Clipboard',
                'description': 'Copy the area value to clipboard for easy pasting',
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
        """Execute the calculate polygon area action."""
        # Get settings with proper type conversion
        try:
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_feature_id = bool(self.get_setting('show_feature_id', True))
            show_layer_name = bool(self.get_setting('show_layer_name', True))
            show_crs_info = bool(self.get_setting('show_crs_info', True))
            show_units = bool(self.get_setting('show_units', True))
            show_success_message = bool(self.get_setting('show_success_message', False))
            copy_to_clipboard = bool(self.get_setting('copy_to_clipboard', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
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
            
            # CRITICAL: Handle CRS transformation for accurate area calculation
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            
            # For area calculations, we need to ensure we're in a projected CRS
            # Geographic CRS (like WGS84) gives area in square degrees which is not meaningful
            if layer_crs.isGeographic():
                # Transform to a projected CRS for accurate area calculation
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
            
            # Calculate area
            area = geometry.area()
            
            # Get unit information
            unit_name = "square units"
            if show_units:
                if calculation_crs.isGeographic():
                    unit_name = "square degrees"
                else:
                    # For projected CRS, get the map units
                    try:
                        unit_name = f"square {calculation_crs.mapUnits().name().lower()}"
                    except:
                        unit_name = "square map units"
            
            # Format the area value
            area_formatted = f"{area:.{decimal_places}f}"
            
            # Build result message
            result_lines = []
            
            if show_feature_id:
                result_lines.append(f"Feature ID: {feature.id()}")
            
            if show_layer_name:
                result_lines.append(f"Layer: {layer.name()}")
            
            result_lines.append(f"Area: {area_formatted}")
            
            if show_units:
                result_lines.append(f"Units: {unit_name}")
            
            if show_crs_info:
                result_lines.append(f"CRS: {calculation_crs.description()}")
            
            result_text = "\n".join(result_lines)
            
            # Show result
            self.show_info("Area Calculation", result_text)
            
            # Copy to clipboard if requested
            if copy_to_clipboard:
                from qgis.PyQt.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(area_formatted)
            
            # Show success message if requested
            if show_success_message:
                self.show_info("Success", f"Area calculated successfully: {area_formatted} {unit_name}")
            
            # Record an informational history entry (read-only operation)
            try:
                hm = get_history_manager()
                layer_desc = None
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}

                meta = {
                    'feature_id': feature.id(),
                    'layer': layer_desc,
                    'area': float(area),
                    'area_formatted': area_formatted,
                    'units': unit_name,
                    'calculation_crs': calculation_crs.authid() if hasattr(calculation_crs, 'authid') else str(calculation_crs)
                }

                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Calculated area for feature {feature.id()} on layer {layer.name()}",
                    meta=meta
                )
            except Exception:
                # History recording should never block the main action
                pass
        except Exception as e:
            self.show_error("Error", f"Failed to calculate area: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_polygon_area_action = CalculatePolygonAreaAction()
