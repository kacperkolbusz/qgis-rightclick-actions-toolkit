"""
Delete Field Undo Handler for Right-click Actions Toolkit

Handles undo/redo for actions that DELETE fields from layers (e.g. NULL cleanup actions).

Undo: Re-add the deleted field(s) with their original definitions and restore
      all previously stored per-feature values.
Redo: Delete the field(s) again.

Payload expected in entry.undo_payload:
    {
        'layer_id':      str   - QGIS layer ID,
        'layer_name':    str   - Human-readable layer name (for error messages),
        'deleted_fields': [
            {
                'name':       str   - Field name,
                'type':       int   - QMetaType.Type integer value,
                'type_name':  str   - Type name string,
                'length':     int   - Field length,
                'precision':  int   - Field precision,
                'comment':    str   - Field comment,
                'alias':      str   - Field alias (may be empty),
                'values':     dict  - {str(feature_id): value, ...}
            },
            ...
        ]
    }
"""

from typing import Tuple

from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsField
    from qgis.PyQt.QtCore import QMetaType, QVariant
except ImportError:
    pass


class DeleteFieldHandler(BaseUndoHandler):
    """
    Handler for undoing field deletion.

    Undo  → re-add the fields and restore per-feature values.
    Redo  → delete the fields again.
    """

    undo_type = "delete_field"

    # ------------------------------------------------------------------
    # Undo: restore deleted fields
    # ------------------------------------------------------------------

    def undo(self, entry) -> Tuple[bool, str]:
        """Re-add deleted fields and restore their original values."""
        try:
            payload = entry.undo_payload or {}
            layer_id = payload.get('layer_id') or (
                entry.layers[0].get('layer_id') if entry.layers else None
            )
            layer_name = payload.get('layer_name', 'Unknown')
            deleted_fields = payload.get('deleted_fields', [])

            if not layer_id:
                return False, "Cannot undo: no layer ID in payload."

            layer = self.get_layer(layer_id)
            if not layer:
                return False, f"Cannot undo: layer '{layer_name}' no longer exists in the project."

            if layer.readOnly():
                return False, f"Cannot undo: layer '{layer_name}' is read-only."

            if not deleted_fields:
                return True, "Nothing to restore (no field data stored)."

            # --- Session 1: add the field definitions (schema change) ---
            # Schema changes and data changes must be committed separately;
            # combining them in one session causes commit failures on many providers.
            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Cannot undo: failed to start editing layer '{layer_name}'."

            try:
                for field_data in deleted_fields:
                    field = self._build_field(field_data)
                    if not layer.addAttribute(field):
                        self.rollback(layer, was_editing)
                        return False, (
                            f"Cannot undo: failed to re-add field "
                            f"'{field_data['name']}' to layer '{layer_name}'."
                        )

                ok, msg = self.commit_or_rollback(layer, was_editing)
                if not ok:
                    return False, msg

                layer.updateFields()

            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Undo error (schema phase): {str(e)}"

            # --- Session 2: restore per-feature values (data change) ---
            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Cannot undo: failed to start editing layer '{layer_name}' for value restore."

            try:
                for field_data in deleted_fields:
                    field_name = field_data['name']
                    field_idx = layer.fields().indexOf(field_name)
                    if field_idx < 0:
                        self.rollback(layer, was_editing)
                        return False, (
                            f"Cannot undo: field '{field_name}' not found after "
                            f"re-adding to layer '{layer_name}'."
                        )

                    for fid_str, value in field_data.get('values', {}).items():
                        try:
                            # Stored None means the original value was NULL;
                            # pass QVariant() so QGIS sets a proper NULL, not 0.
                            restore_val = QVariant() if value is None else value
                            layer.changeAttributeValue(int(fid_str), field_idx, restore_val)
                        except Exception:
                            pass  # Skip individual failures; continue restoring others

                ok, msg = self.commit_or_rollback(layer, was_editing)
                if not ok:
                    return False, msg

                layer.updateFields()
                layer.triggerRepaint()

                restored = [f['name'] for f in deleted_fields]
                return True, (
                    f"Restored {len(restored)} field(s) to layer '{layer_name}': "
                    + ", ".join(restored)
                )

            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Undo error (value restore phase): {str(e)}"

        except Exception as e:
            return False, f"Undo failed: {str(e)}"

    # ------------------------------------------------------------------
    # Redo: delete the fields again
    # ------------------------------------------------------------------

    def redo(self, entry) -> Tuple[bool, str]:
        """Delete the fields again (re-apply the original cleanup)."""
        try:
            payload = entry.undo_payload or {}
            layer_id = payload.get('layer_id') or (
                entry.layers[0].get('layer_id') if entry.layers else None
            )
            layer_name = payload.get('layer_name', 'Unknown')
            deleted_fields = payload.get('deleted_fields', [])

            if not layer_id:
                return False, "Cannot redo: no layer ID in payload."

            layer = self.get_layer(layer_id)
            if not layer:
                return False, f"Cannot redo: layer '{layer_name}' no longer exists."

            if layer.readOnly():
                return False, f"Cannot redo: layer '{layer_name}' is read-only."

            if not deleted_fields:
                return True, "Nothing to redo."

            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Cannot redo: failed to start editing layer '{layer_name}'."

            try:
                field_indices = []
                for field_data in deleted_fields:
                    idx = layer.fields().indexOf(field_data['name'])
                    if idx >= 0:
                        field_indices.append(idx)

                if not field_indices:
                    self.rollback(layer, was_editing)
                    return True, "Fields are already absent from the layer."

                if not layer.deleteAttributes(field_indices):
                    self.rollback(layer, was_editing)
                    return False, f"Cannot redo: failed to delete fields from layer '{layer_name}'."

                ok, msg = self.commit_or_rollback(layer, was_editing)
                if not ok:
                    return False, msg

                layer.updateFields()
                layer.triggerRepaint()

                names = [f['name'] for f in deleted_fields]
                return True, (
                    f"Re-deleted {len(names)} field(s) from layer '{layer_name}': "
                    + ", ".join(names)
                )

            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Redo error: {str(e)}"

        except Exception as e:
            return False, f"Redo failed: {str(e)}"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_field(field_data: dict) -> 'QgsField':
        """Reconstruct a QgsField from its serialised definition."""
        name = field_data['name']
        type_name = field_data.get('type_name', '')
        length = field_data.get('length', 0)
        precision = field_data.get('precision', 0)
        comment = field_data.get('comment', '')
        alias = field_data.get('alias', '')

        try:
            # Prefer QMetaType (avoids deprecation warnings in QGIS 3.x)
            meta_type = QMetaType.Type(int(field_data['type']))
            field = QgsField(name, meta_type, type_name, length, precision, comment)
        except Exception:
            # Fallback: pass integer type directly
            field = QgsField(name, int(field_data['type']), type_name, length, precision, comment)

        if alias:
            field.setAlias(alias)

        return field


# Singleton instance for automatic discovery by the handler registry
handler = DeleteFieldHandler()
