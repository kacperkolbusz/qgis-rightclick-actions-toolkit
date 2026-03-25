"""
Reverse Line Direction Action for Right-click Utilities and Shortcuts Hub

Reverses the vertex order of the selected line feature, effectively flipping its
digitizing direction (start becomes end and end becomes start). Works with both
simple line and multiline features.
"""

from .base_action import BaseAction
from qgis.core import QgsWkbTypes, QgsGeometry


class ReverseLineDirectionAction(BaseAction):
    """Action to reverse the vertex order (direction) of a line feature."""

    def __init__(self):
        super().__init__()

        # Required properties
        self.action_id = "reverse_line_direction"
        self.name = "Reverse Line Direction"
        self.category = "Editing"
        self.description = (
            "Reverse the digitizing direction of the selected line feature by flipping "
            "the order of its vertices (start becomes end, end becomes start). "
            "Works with both simple LineString and MultiLineString geometries. "
            "Supports undo to restore the original direction."
        )
        self.enabled = True

        # Action scoping - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Feature type support - only line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

        # Internal undo state
        self._original_geometry_backup = None
        self._target_layer = None
        self._target_fid = None

    # -------------------------------------------------------------------------
    # Undo support
    # -------------------------------------------------------------------------

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

    def get_settings_schema(self):
        return {
            'confirm_reversal': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Reversing',
                'description': 'Show a confirmation dialog before reversing the line direction',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when the line direction has been reversed successfully',
            },
            'show_bearing_change': {
                'type': 'bool',
                'default': False,
                'label': 'Show Bearing Change',
                'description': 'Include the original and new overall bearing in the success message',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after reversing (recommended)',
            },
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _reverse_geometry(geometry):
        """
        Return a new QgsGeometry with reversed vertex order.

        Handles both LineString and MultiLineString. Returns None on failure.
        """
        if geometry is None or geometry.isEmpty():
            return None

        geom_type = geometry.wkbType()

        if QgsWkbTypes.flatType(geom_type) == QgsWkbTypes.LineString:
            line = geometry.asPolyline()
            if not line:
                return None
            return QgsGeometry.fromPolylineXY(list(reversed(line)))

        if QgsWkbTypes.flatType(geom_type) == QgsWkbTypes.MultiLineString:
            multi = geometry.asMultiPolyline()
            if not multi:
                return None
            reversed_multi = [list(reversed(part)) for part in multi]
            return QgsGeometry.fromMultiPolylineXY(reversed_multi)

        return None

    @staticmethod
    def _overall_bearing(geometry):
        """Return a rough bearing string (start->end) or empty string on failure."""
        try:
            import math
            if QgsWkbTypes.flatType(geometry.wkbType()) == QgsWkbTypes.LineString:
                line = geometry.asPolyline()
            else:
                multi = geometry.asMultiPolyline()
                line = multi[0] if multi else []

            if len(line) < 2:
                return ""

            dx = line[-1].x() - line[0].x()
            dy = line[-1].y() - line[0].y()
            bearing = math.degrees(math.atan2(dx, dy)) % 360.0
            return f"{bearing:.1f}\u00b0"
        except Exception:
            return ""

    # -------------------------------------------------------------------------
    # Execute
    # -------------------------------------------------------------------------

    def execute(self, context):
        """Execute the reverse line direction action."""

        # --- settings ---
        try:
            confirm_reversal = bool(self.get_setting('confirm_reversal', False))
            show_success = bool(self.get_setting('show_success_message', True))
            show_bearing = bool(self.get_setting('show_bearing_change', False))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        # Reset undo state
        self._original_geometry_backup = None
        self._target_layer = None
        self._target_fid = None

        # --- extract context ---
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
            return

        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer

        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            self.show_error("Error", "The selected feature has no geometry")
            return

        if geometry.type() != QgsWkbTypes.LineGeometry:
            self.show_error("Error", "This action only works with line features")
            return

        fid = int(feature.id())

        # --- optional confirmation ---
        if confirm_reversal:
            msg = (
                f"Reverse the direction of line feature ID {fid} "
                f"from layer '{layer.name()}'?"
            )
            if not self.confirm_action("Reverse Line Direction", msg):
                return

        # --- compute reversed geometry ---
        reversed_geom = self._reverse_geometry(geometry)
        if reversed_geom is None:
            self.show_error("Error", "Could not reverse the line geometry")
            return

        # --- bearing info before change ---
        bearing_before = self._overall_bearing(geometry) if show_bearing else ""
        bearing_after = self._overall_bearing(reversed_geom) if show_bearing else ""

        # --- backup original geometry for undo ---
        try:
            original_backup = self.create_feature_backup(feature, layer,
                                                          include_geometry=True,
                                                          include_attributes=False)
        except Exception:
            original_backup = None

        # Also store the reversed geometry for redo
        try:
            import base64
            reversed_geom_backup = {
                'wkb_base64': base64.b64encode(reversed_geom.asWkb()).decode('utf-8')
            }
        except Exception:
            reversed_geom_backup = None

        # --- enter edit mode ---
        was_in_edit_mode, edit_mode_entered = self.handle_edit_mode(
            layer, "reverse line direction"
        )
        if was_in_edit_mode is None:
            return

        try:
            if not layer.changeGeometry(fid, reversed_geom):
                self.show_error("Error", "Failed to apply reversed geometry to the feature")
                self.rollback_changes(layer)
                return

            if auto_commit:
                if not self.commit_changes(layer, "reverse line direction"):
                    return

            layer.triggerRepaint()

            # --- record history ---
            try:
                if original_backup is not None:
                    # Build a payload that update_geometry handler can use for undo/redo
                    feature_entry = {
                        'fid': fid,
                        'old_geometry': original_backup.get('geometry'),
                        'new_geometry': reversed_geom_backup,
                    }
                    self.record_to_history(
                        description=f"Reversed direction of line feature {fid} in layer '{layer.name()}'",
                        undo_type='update_geometry',
                        can_undo=True,
                        layers=[self.create_layer_descriptor(layer)],
                        features=[feature_entry],
                        meta={'feature_id': fid, 'layer_name': layer.name()}
                    )
            except Exception:
                pass  # History recording must not block a successful action

            # --- success message ---
            if show_success:
                msg = (
                    f"Line feature ID {fid} in layer '{layer.name()}' "
                    f"has been reversed successfully."
                )
                if show_bearing and bearing_before and bearing_after:
                    msg += f"\n\nBearing before: {bearing_before}\nBearing after:  {bearing_after}"
                self.show_info("Line Reversed", msg)

        except Exception as e:
            self.show_error("Error", f"An unexpected error occurred: {str(e)}")
            try:
                self.rollback_changes(layer)
            except Exception:
                pass


# Required: global instance for automatic discovery
reverse_line_direction = ReverseLineDirectionAction()
