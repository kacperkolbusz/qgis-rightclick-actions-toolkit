"""
Update Layer CRS Undo Handler

Handles undo/redo for changing a layer's CRS. The handler expects the
history entry to include the affected layers (with `layer_id`) and to have
`meta` containing `from_crs` and `to_crs` (authid strings or CRS WKT).

Undo: set layer CRS to `from_crs`
Redo: set layer CRS to `to_crs`
"""

from typing import Tuple, Dict, Any
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsCoordinateReferenceSystem
except ImportError:
    pass


class UpdateLayerCrsHandler(BaseUndoHandler):
    undo_type = "update_layer_crs"

    def _get_layer_any(self, layer_id: str):
        """Return any layer (vector or raster) by id."""
        try:
            return QgsProject.instance().mapLayer(layer_id)
        except Exception:
            return None

    def undo(self, entry) -> Tuple[bool, str]:
        try:
            from_crs = None
            if hasattr(entry, 'meta') and entry.meta:
                from_crs = entry.meta.get('from_crs')

            if not from_crs:
                return False, "No from_crs provided in history entry"

            for layer_info in entry.layers:
                layer_id = layer_info.get('layer_id')
                layer = self._get_layer_any(layer_id)
                if not layer:
                    continue

                try:
                    crs_obj = QgsCoordinateReferenceSystem(from_crs)
                    if crs_obj.isValid():
                        layer.setCrs(crs_obj)
                except Exception:
                    # non-fatal per-layer
                    continue

            return True, "Layer CRS restored"
        except Exception as e:
            return False, f"Undo failed: {e}"

    def redo(self, entry) -> Tuple[bool, str]:
        try:
            to_crs = None
            if hasattr(entry, 'meta') and entry.meta:
                to_crs = entry.meta.get('to_crs')

            if not to_crs:
                return False, "No to_crs provided in history entry"

            for layer_info in entry.layers:
                layer_id = layer_info.get('layer_id')
                layer = self._get_layer_any(layer_id)
                if not layer:
                    continue

                try:
                    crs_obj = QgsCoordinateReferenceSystem(to_crs)
                    if crs_obj.isValid():
                        layer.setCrs(crs_obj)
                except Exception:
                    continue

            return True, "Layer CRS re-applied"
        except Exception as e:
            return False, f"Redo failed: {e}"


# singleton for auto-registration
handler = UpdateLayerCrsHandler()
