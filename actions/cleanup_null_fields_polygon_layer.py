"""
Cleanup NULL Fields - Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Analyzes the attribute table of a polygon layer and removes fields where a configurable
percentage of values are NULL. Helps keep attribute tables clean and manageable by
removing fields that are mostly empty.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsWkbTypes, QgsFeatureRequest,
    NULL as QGIS_NULL
)
from qgis.PyQt.QtCore import QVariant, QMetaType


class CleanupNullFieldsPolygonLayerAction(BaseAction):
    """Action to remove high-NULL fields from polygon layer attribute tables."""

    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()

        self.action_id = 'cleanup_null_fields_polygon_layer'
        self.name = 'Clean Up NULL Fields'
        self.category = 'Editing'
        self.description = (
            'Analyzes the attribute table of a polygon layer and deletes fields where '
            'a configurable percentage of cells are NULL. The NULL threshold is adjustable '
            'in settings. Supports undo to restore deleted fields and their original values.'
        )
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            'null_threshold_percentage': {
                'type': 'float',
                'label': 'NULL Threshold (%)',
                'default': 90.0,
                'min': 0.0,
                'max': 100.0,
                'step': 5.0,
                'description': (
                    'Fields where this percentage or more of values are NULL will be deleted. '
                    'E.g. 90 means fields with 90% or more NULL cells will be removed.'
                ),
            },
            'show_preview': {
                'type': 'bool',
                'label': 'Show Preview Before Deleting',
                'default': True,
                'description': (
                    'Show a list of fields that will be deleted and ask for confirmation '
                    'before proceeding. Recommended to keep this enabled.'
                ),
            },
            'show_summary': {
                'type': 'bool',
                'label': 'Show Summary After Cleanup',
                'default': True,
                'description': 'Show a summary of deleted fields after the cleanup is complete.',
            },
        }

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def execute(self, context):
        """Execute the NULL field cleanup action on a polygon layer."""
        # --- Read settings with type conversion ---
        try:
            null_threshold = float(self.get_setting('null_threshold_percentage', 90.0))
            show_preview = bool(self.get_setting('show_preview', True))
            show_summary = bool(self.get_setting('show_summary', True))
        except (ValueError, TypeError) as e:
            self.show_error("Settings Error", f"Invalid setting values: {str(e)}")
            return

        # --- Resolve layer from context ---
        layer = context.get('layer')
        if not layer:
            detected = context.get('detected_features', [])
            if detected:
                layer = detected[0].layer
        if not layer:
            self.show_error("Error", "No layer found in context.")
            return

        if not isinstance(layer, QgsVectorLayer):
            self.show_error("Error", "Target is not a vector layer.")
            return

        # --- Check feature count ---
        feature_count = layer.featureCount()
        if feature_count == 0:
            self.show_info(
                "No Features",
                f"Layer '{layer.name()}' has no features. Nothing to analyze."
            )
            return

        # --- Analyze fields for NULL percentages ---
        fields_to_delete = []
        field_null_info = []

        for field in layer.fields():
            field_name = field.name()
            null_count = 0

            for feature in layer.getFeatures():
                val = feature[field_name]
                # In PyQGIS, NULL attribute values are qgis.core.NULL (not Python None).
                # Also guard against plain None and QVariant nulls for completeness.
                if (val is None
                        or val == QGIS_NULL
                        or (hasattr(val, 'isNull') and val.isNull())):
                    null_count += 1

            null_percentage = (null_count / feature_count) * 100.0

            if null_percentage >= null_threshold:
                fields_to_delete.append(field_name)
                field_null_info.append({
                    'name': field_name,
                    'null_count': null_count,
                    'null_percentage': null_percentage,
                })

        # --- No fields exceed the threshold ---
        if not fields_to_delete:
            self.show_info(
                "Nothing to Clean Up",
                f"No fields found with {null_threshold:.0f}% or more NULL values "
                f"in layer '{layer.name()}'.\n\nAll {len(layer.fields())} field(s) "
                f"are below the threshold."
            )
            self.record_informational(
                description=(
                    f"NULL field cleanup on '{layer.name()}': 0 fields removed "
                    f"(threshold: {null_threshold:.0f}%)"
                ),
                meta={
                    'layer_id': layer.id(),
                    'layer_name': layer.name(),
                    'threshold': null_threshold,
                }
            )
            return

        # --- Show preview and ask for confirmation if enabled ---
        if show_preview:
            lines = [
                f"Layer: {layer.name()}",
                f"Total features: {feature_count}",
                f"NULL threshold: {null_threshold:.0f}%",
                f"\nFields to be deleted ({len(fields_to_delete)}):\n",
            ]
            for info in field_null_info:
                lines.append(
                    f"  \u2022 {info['name']}: {info['null_percentage']:.1f}% NULL "
                    f"({info['null_count']}/{feature_count} cells)"
                )
            lines.append("\nDo you want to delete these fields?")

            if not self.confirm_action("Confirm Field Deletion", "\n".join(lines)):
                return

        # --- Backup fields before deletion (for undo support) ---
        backup = self._create_field_backup(layer, fields_to_delete)

        # --- Start editing and delete fields ---
        was_editing = layer.isEditable()
        if not was_editing:
            if not layer.startEditing():
                self.show_error(
                    "Error",
                    f"Cannot start editing layer '{layer.name()}'. "
                    "The layer may be read-only."
                )
                return

        # Collect current field indices (must be resolved before any deletion)
        field_indices = []
        for field_name in fields_to_delete:
            idx = layer.fields().indexOf(field_name)
            if idx >= 0:
                field_indices.append(idx)

        if not field_indices:
            if not was_editing:
                layer.rollBack()
            self.show_error("Error", "Could not find field indices for deletion.")
            return

        if not layer.deleteAttributes(field_indices):
            if not was_editing:
                layer.rollBack()
            self.show_error("Error", "Failed to delete the selected fields.")
            return

        if not layer.commitChanges():
            layer.rollBack()
            self.show_error("Error", "Failed to commit field deletions to the layer.")
            return

        layer.updateFields()
        layer.triggerRepaint()

        # --- Record to history with full undo payload ---
        undo_payload = {
            'layer_id': layer.id(),
            'layer_name': layer.name(),
            'deleted_fields': backup,
            'threshold': null_threshold,
        }

        self.record_to_history(
            description=(
                f"Deleted {len(fields_to_delete)} NULL-heavy field(s) from "
                f"polygon layer '{layer.name()}' (threshold: {null_threshold:.0f}%)"
            ),
            undo_type='delete_field',
            can_undo=True,
            undo_payload=undo_payload,
            layers=[self.create_layer_descriptor(layer)],
            meta={
                'layer_id': layer.id(),
                'layer_name': layer.name(),
                'threshold': null_threshold,
                'deleted_field_names': [i['name'] for i in field_null_info],
            }
        )

        # --- Show summary ---
        if show_summary:
            lines = [
                f"Layer: {layer.name()}",
                f"\nSuccessfully deleted {len(fields_to_delete)} field(s):\n",
            ]
            for info in field_null_info:
                lines.append(
                    f"  \u2022 {info['name']}: {info['null_percentage']:.1f}% NULL"
                )
            lines.append("\nThis action can be undone via the History panel.")
            self.show_info("Cleanup Complete", "\n".join(lines))

    # -------------------------------------------------------------------------
    # Undo Support
    # -------------------------------------------------------------------------

    def apply_undo(self, payload: dict) -> tuple:
        """Restore fields that were deleted by this action."""
        try:
            layer_id = payload.get('layer_id')
            layer_name = payload.get('layer_name', 'Unknown')
            deleted_fields = payload.get('deleted_fields', [])

            # Locate the layer
            layer = QgsProject.instance().mapLayer(layer_id)
            if not layer:
                return False, (
                    f"Cannot undo: layer '{layer_name}' no longer exists in the project."
                )

            if layer.readOnly():
                return False, f"Cannot undo: layer '{layer_name}' is read-only."

            if not layer.startEditing():
                return False, f"Cannot undo: failed to start editing layer '{layer_name}'."

            # Re-add each deleted field
            for field_data in deleted_fields:
                try:
                    field = QgsField(
                        field_data['name'],
                        QMetaType.Type(field_data['type']),
                        field_data['type_name'],
                        field_data['length'],
                        field_data['precision'],
                        field_data['comment'],
                    )
                    if field_data.get('alias'):
                        field.setAlias(field_data['alias'])
                except Exception:
                    field = QgsField(
                        field_data['name'],
                        field_data['type'],
                        field_data['type_name'],
                        field_data['length'],
                        field_data['precision'],
                        field_data['comment'],
                    )

                if not layer.addAttribute(field):
                    layer.rollBack()
                    return False, (
                        f"Cannot undo: failed to re-add field '{field_data['name']}' "
                        f"to layer '{layer_name}'."
                    )

            layer.updateFields()

            # Restore values for each field
            for field_data in deleted_fields:
                field_name = field_data['name']
                field_idx = layer.fields().indexOf(field_name)
                if field_idx < 0:
                    layer.rollBack()
                    return False, (
                        f"Cannot undo: field '{field_name}' not found after re-adding "
                        f"to layer '{layer_name}'."
                    )

                values_map = field_data.get('values', {})
                for fid_str, value in values_map.items():
                    try:
                        fid = int(fid_str)
                        layer.changeAttributeValue(fid, field_idx, value)
                    except Exception:
                        pass

            if not layer.commitChanges():
                layer.rollBack()
                return False, f"Cannot undo: failed to commit restored fields to layer '{layer_name}'."

            layer.updateFields()
            layer.triggerRepaint()

            restored_names = [f['name'] for f in deleted_fields]
            return True, (
                f"Restored {len(deleted_fields)} field(s) to layer '{layer_name}': "
                f"{', '.join(restored_names)}"
            )

        except Exception as e:
            return False, f"Undo failed with unexpected error: {str(e)}"

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _create_field_backup(layer: QgsVectorLayer, field_names: list) -> list:
        """
        Create a JSON-serializable backup of the given fields including all values.

        Returns:
            list of dicts, one per field, containing definition and per-feature values.
        """
        backup = []
        layer_fields = layer.fields()

        for field_name in field_names:
            field_index = layer_fields.indexOf(field_name)
            if field_index < 0:
                continue

            field = layer_fields.field(field_index)

            field_entry = {
                'name': field.name(),
                'type': int(field.type()),
                'type_name': field.typeName(),
                'length': field.length(),
                'precision': field.precision(),
                'comment': field.comment(),
                'alias': field.alias(),
                'values': {},
            }

            for feature in layer.getFeatures():
                val = feature.attribute(field_index)
                # Normalise value to JSON-compatible types.
                # QGIS returns NULL as qgis.core.NULL, not Python None.
                if (val is None
                        or val == QGIS_NULL
                        or (hasattr(val, 'isNull') and val.isNull())):
                    serialised = None
                elif isinstance(val, (int, float, str, bool)):
                    serialised = val
                else:
                    try:
                        serialised = float(val)
                    except (TypeError, ValueError):
                        serialised = str(val)

                field_entry['values'][str(feature.id())] = serialised

            backup.append(field_entry)

        return backup


# Global instance for automatic discovery
cleanup_null_fields_polygon_layer = CleanupNullFieldsPolygonLayerAction()
