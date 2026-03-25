"""
Calculate Line Length Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the length of the clicked line feature.
Shows length in appropriate units based on the layer CRS and supports
copying the result to the clipboard and recording an informational history entry.
"""

from .base_action import BaseAction
from qgis.core import QgsWkbTypes


class CalculateLineLengthAction(BaseAction):
    """
    Action to calculate and display the length of a single line feature.
    """

    def __init__(self):
        super().__init__()

        # Required properties
        self.action_id = "calculate_line_length"
        self.name = "Calculate Line Length"
        self.category = "Analysis"
        self.description = (
            "Calculate and display the length of the selected line feature. "
            "Shows result in appropriate units based on the layer CRS."
        )
        self.enabled = True

        # Action scoping - feature-level action
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

    def get_settings_schema(self):
        return {
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in the length output',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature ID',
                'description': 'Include the feature ID in the result dialog',
            },
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Include the layer name in the result dialog',
            },
            'show_units': {
                'type': 'bool',
                'default': True,
                'label': 'Show Units',
                'description': 'Display units (meters, feet, degrees, etc.) in the result',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show CRS Information',
                'description': 'Display CRS information in the result dialog',
            },
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Show a brief success message after calculation',
            },
            'copy_to_clipboard': {
                'type': 'bool',
                'default': False,
                'label': 'Copy to Clipboard',
                'description': 'Copy the formatted length result to the clipboard',
            },
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    def execute(self, context):
        try:
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_feature_id = bool(self.get_setting('show_feature_id', True))
            show_layer_name = bool(self.get_setting('show_layer_name', True))
            show_units = bool(self.get_setting('show_units', True))
            show_crs_info = bool(self.get_setting('show_crs_info', False))
            show_success_message = bool(self.get_setting('show_success_message', False))
            copy_to_clipboard = bool(self.get_setting('copy_to_clipboard', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        detected_features = context.get('detected_features', [])

        if not detected_features:
            self.show_error("Error", "No line features found at this location")
            return

        detected = detected_features[0]
        feature = detected.feature
        layer = detected.layer

        try:
            geometry = feature.geometry()
            if not geometry:
                self.show_error("Error", "Feature has no geometry")
                return

            if geometry.type() != QgsWkbTypes.LineGeometry:
                self.show_error("Error", "This action only works with line features")
                return

            # Calculate length in layer map units
            length = geometry.length()

            # Determine unit name
            unit_name = "units"
            if show_units:
                try:
                    crs = layer.crs()
                    if crs.isGeographic():
                        unit_name = "degrees"
                    else:
                        try:
                            unit_name = crs.mapUnits().name().lower()
                        except Exception:
                            unit_name = "map units"
                except Exception:
                    unit_name = "map units"

            length_formatted = f"{length:.{decimal_places}f}"
            if show_units:
                length_text = f"{length_formatted} {unit_name}"
            else:
                length_text = length_formatted

            # Build result message
            lines = []
            if show_feature_id:
                lines.append(f"Feature ID: {feature.id()}")
            if show_layer_name:
                lines.append(f"Layer: {layer.name()}")

            lines.append(f"Line Length: {length_text}")

            if show_crs_info:
                try:
                    crs = layer.crs()
                    lines.append(f"CRS: {crs.description()}")
                except Exception:
                    pass

            result_text = "\n".join(lines)

            # Show result
            self.show_info("Line Length", result_text)

            # Record informational history entry
            try:
                meta = {
                    'feature_id': feature.id(),
                    'layer_id': layer.id() if hasattr(layer, 'id') else None,
                    'layer_name': layer.name() if hasattr(layer, 'name') else None,
                    'length': float(length),
                    'length_formatted': length_text,
                }
                description = f"Calculated length {length_text} for feature {feature.id()} on layer {layer.name()}"
                self.record_informational(description, meta=meta)
            except Exception:
                pass

            # Copy to clipboard if requested
            if copy_to_clipboard:
                try:
                    from qgis.PyQt.QtWidgets import QApplication
                    clipboard = QApplication.clipboard()
                    clipboard.setText(length_text)
                except Exception:
                    pass

            if show_success_message:
                self.show_info("Success", f"Length calculated: {length_text}")

        except Exception as e:
            self.show_error("Error", f"Failed to calculate length: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_line_length = CalculateLineLengthAction()
