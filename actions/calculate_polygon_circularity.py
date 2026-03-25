"""
Calculate Polygon Circularity Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the circularity of polygon features.
Circularity measures how close a polygon is to a perfect circle (0 to 1 scale).
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager
import math


class CalculatePolygonCircularityAction(BaseAction):
    """Action to calculate and display polygon circularity."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_polygon_circularity"
        self.name = "Calculate Polygon Circularity"
        self.category = "Analysis"
        self.description = "Calculate and display the circularity of the selected polygon feature. Circularity measures how close a polygon is to a perfect circle, ranging from 0 (not circular) to 1 (perfect circle). Uses the formula: 4π × area / perimeter². Shows result in information dialog with customizable formatting options."
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
                'default': 4,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in circularity calculation',
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
            'show_area_perimeter': {
                'type': 'bool',
                'default': True,
                'label': 'Show Area and Perimeter',
                'description': 'Display the area and perimeter values used in the calculation',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result dialog',
            },
            'show_interpretation': {
                'type': 'bool',
                'default': True,
                'label': 'Show Interpretation',
                'description': 'Display interpretation of the circularity value (e.g., "Very circular", "Moderately circular")',
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
                'description': 'Copy the circularity value to clipboard for easy pasting',
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
    
    def _get_circularity_interpretation(self, circularity):
        """
        Get a human-readable interpretation of the circularity value.
        
        Args:
            circularity (float): Circularity value (0 to 1)
            
        Returns:
            str: Interpretation text
        """
        if circularity >= 0.95:
            return "Very circular (nearly perfect circle)"
        elif circularity >= 0.85:
            return "Highly circular"
        elif circularity >= 0.70:
            return "Moderately circular"
        elif circularity >= 0.50:
            return "Somewhat circular"
        elif circularity >= 0.30:
            return "Not very circular"
        else:
            return "Not circular (elongated or irregular)"
    
    def execute(self, context):
        """Execute the calculate polygon circularity action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            decimal_places = int(self.get_setting('decimal_places', schema['decimal_places']['default']))
            show_feature_id = bool(self.get_setting('show_feature_id', schema['show_feature_id']['default']))
            show_layer_name = bool(self.get_setting('show_layer_name', schema['show_layer_name']['default']))
            show_area_perimeter = bool(self.get_setting('show_area_perimeter', schema['show_area_perimeter']['default']))
            show_crs_info = bool(self.get_setting('show_crs_info', schema['show_crs_info']['default']))
            show_interpretation = bool(self.get_setting('show_interpretation', schema['show_interpretation']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
            copy_to_clipboard = bool(self.get_setting('copy_to_clipboard', schema['copy_to_clipboard']['default']))
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
            
            if geometry.isEmpty():
                self.show_error("Error", "Feature has empty geometry")
                return
            
            # CRITICAL: Handle CRS transformation for accurate area and perimeter calculation
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            
            # For area and perimeter calculations, we need to ensure we're in a projected CRS
            # Geographic CRS (like WGS84) gives area in square degrees which is not meaningful
            if layer_crs.isGeographic():
                # Transform to a projected CRS for accurate calculation
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
                try:
                    geometry.transform(transform)
                except Exception as e:
                    self.show_error("Error", f"Failed to transform geometry: {str(e)}")
                    return
                calculation_crs = projected_crs
            else:
                # Already in projected CRS
                calculation_crs = layer_crs
            
            # Calculate area and perimeter
            area = geometry.area()
            perimeter = geometry.length()
            
            # Check for valid values
            if area <= 0:
                self.show_error("Error", "Polygon has zero or negative area")
                return
            
            if perimeter <= 0:
                self.show_error("Error", "Polygon has zero or negative perimeter")
                return
            
            # Calculate circularity: 4π × area / perimeter²
            # This formula gives a value from 0 to 1, where 1 is a perfect circle
            circularity = (4 * math.pi * area) / (perimeter * perimeter)
            
            # Clamp circularity to valid range (0 to 1)
            circularity = max(0.0, min(1.0, circularity))
            
            # Format the circularity value
            circularity_formatted = f"{circularity:.{decimal_places}f}"
            
            # Get unit information
            unit_name = "map units"
            if calculation_crs.isGeographic():
                unit_name = "degrees"
            else:
                try:
                    unit_name = calculation_crs.mapUnits().name().lower()
                except:
                    unit_name = "map units"
            
            # Build result message
            result_lines = []
            
            if show_feature_id:
                result_lines.append(f"Feature ID: {feature.id()}")
            
            if show_layer_name:
                result_lines.append(f"Layer: {layer.name()}")
            
            result_lines.append(f"Circularity: {circularity_formatted}")
            result_lines.append(f"  (Range: 0 = not circular, 1 = perfect circle)")
            
            if show_interpretation:
                interpretation = self._get_circularity_interpretation(circularity)
                result_lines.append(f"Interpretation: {interpretation}")
            
            if show_area_perimeter:
                result_lines.append("")
                result_lines.append(f"Area: {area:.2f} square {unit_name}")
                result_lines.append(f"Perimeter: {perimeter:.2f} {unit_name}")
            
            if show_crs_info:
                result_lines.append("")
                result_lines.append(f"CRS: {calculation_crs.description()}")
            
            result_text = "\n".join(result_lines)
            
            # Show result
            self.show_info("Circularity Calculation", result_text)
            
            # Copy to clipboard if requested
            if copy_to_clipboard:
                from qgis.PyQt.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(circularity_formatted)
            
            # Show success message if requested
            if show_success_message:
                interpretation = self._get_circularity_interpretation(circularity)
                self.show_info("Success", f"Circularity calculated: {circularity_formatted} - {interpretation}")
            
            # Record an informational history entry (read-only operation)
            try:
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}

                meta = {
                    'feature_id': feature.id(),
                    'layer': layer_desc,
                    'circularity': float(circularity),
                    'circularity_formatted': circularity_formatted,
                    'area': float(area),
                    'perimeter': float(perimeter),
                    'units': unit_name,
                    'calculation_crs': calculation_crs.authid() if hasattr(calculation_crs, 'authid') else str(calculation_crs)
                }

                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Calculated circularity for feature {feature.id()} on layer {layer.name()}",
                    meta=meta
                )
            except Exception:
                # Do not let history recording break the calculation
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate circularity: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_polygon_circularity_action = CalculatePolygonCircularityAction()

