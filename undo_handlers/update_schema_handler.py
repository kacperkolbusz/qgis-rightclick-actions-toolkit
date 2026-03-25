"""
Update Schema Undo Handler

Handles undo/redo for schema changes such as adding or removing fields.

Undo: Remove newly added fields (if present) and optionally restore removed fields.
Redo: Re-create previously removed fields or re-add added fields.
"""
from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsField
    from qgis.PyQt.QtCore import QMetaType
    from qgis.core import QgsVectorLayer
except ImportError:
    pass


class UpdateSchemaHandler(BaseUndoHandler):
    """Handler for schema (field) changes."""

    undo_type = "update_schema"

    def undo(self, entry) -> Tuple[bool, str]:
        """Undo schema changes by removing added fields."""
        payload = entry.undo_payload or {}
        added_fields = payload.get('added_fields', [])

        for layer_info in entry.layers:
            layer = self.get_layer(layer_info.get('layer_id'))
            if not isinstance(layer, QgsVectorLayer):
                continue

            try:
                # Find indices of added fields (if they exist)
                indices = []
                fields = layer.fields()
                for f in added_fields:
                    name = f.get('name')
                    if not name:
                        continue
                    idx = fields.indexOf(name)
                    if idx >= 0:
                        indices.append(idx)

                if indices:
                    layer.dataProvider().deleteAttributes(indices)
                    layer.updateFields()

            except Exception as e:
                return False, f"Failed to undo schema changes: {e}"

        return True, "Schema undo successful"

    def redo(self, entry) -> Tuple[bool, str]:
        """Redo schema changes by re-adding fields described in payload."""
        payload = entry.undo_payload or {}
        added_fields = payload.get('added_fields', [])

        for layer_info in entry.layers:
            layer = self.get_layer(layer_info.get('layer_id'))
            if not isinstance(layer, QgsVectorLayer):
                continue

            try:
                fields_to_add = []
                for f in added_fields:
                    name = f.get('name')
                    qmeta = f.get('qmeta_type')
                    length = f.get('length')
                    precision = f.get('precision')
                    if not name or qmeta is None:
                        continue

                    try:
                        fld = QgsField(name, int(qmeta))
                        if length:
                            try:
                                fld.setLength(int(length))
                            except Exception:
                                pass
                        if precision:
                            try:
                                fld.setPrecision(int(precision))
                            except Exception:
                                pass
                        fields_to_add.append(fld)
                    except Exception:
                        # Skip problematic field descriptors
                        continue

                if fields_to_add:
                    layer.dataProvider().addAttributes(fields_to_add)
                    layer.updateFields()

            except Exception as e:
                return False, f"Failed to redo schema changes: {e}"

        return True, "Schema redo successful"


# Create singleton instance for registration
handler = UpdateSchemaHandler()
