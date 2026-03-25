"""
Update Raster Rendering Undo Handler

Handles undo/redo for changes to raster rendering parameters such as
brightness, contrast, and saturation which are implemented using
QgsBrightnessContrastFilter and QgsHueSaturationFilter on a layer's pipe.

Undo: Apply previous rendering settings
Redo: Re-apply the new rendering settings
"""
from typing import Tuple, Dict, Any
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject
    from qgis.core import QgsBrightnessContrastFilter, QgsHueSaturationFilter
except Exception:
    # Running in test environment without QGIS available
    QgsProject = None
    QgsBrightnessContrastFilter = None
    QgsHueSaturationFilter = None


class UpdateRenderingHandler(BaseUndoHandler):
    """
    Handler for undoing raster rendering parameter changes.

    Expects history entry.undo_payload to be a dict with 'settings' key:
        {'settings': {'brightness': int, 'contrast': int, 'saturation': int}}

    The entry.layers should contain a layer descriptor with 'layer_id'.
    """

    undo_type = 'update_rendering'

    def _apply_settings_to_layer(self, layer, settings: Dict[str, Any]) -> bool:
        if layer is None:
            return False
        try:
            # Try to obtain the raster pipe
            try:
                pipe = layer.pipe()
            except Exception:
                pipe = None

            if pipe is None:
                return False

            # Build desired values
            try:
                desired_brightness = int(settings.get('brightness', 0))
            except Exception:
                desired_brightness = 0
            try:
                desired_contrast = int(settings.get('contrast', 0))
            except Exception:
                desired_contrast = 0
            try:
                desired_saturation = int(settings.get('saturation', 0))
            except Exception:
                desired_saturation = 0

            # Collect existing filters (version-tolerant)
            existing_filters = []
            try:
                if hasattr(pipe, 'size') and hasattr(pipe, 'filter'):
                    for i in range(pipe.size()):
                        try:
                            f = pipe.filter(i)
                            if f is not None:
                                existing_filters.append(f)
                        except Exception:
                            continue
                elif hasattr(pipe, 'filters'):
                    try:
                        fl = pipe.filters()
                        if fl:
                            existing_filters = list(fl)
                    except Exception:
                        existing_filters = []
                else:
                    existing_filters = []
            except Exception:
                existing_filters = []

            applied = False

            # Try to update existing filters in-place
            for f in existing_filters:
                try:
                    if QgsBrightnessContrastFilter is not None and isinstance(f, QgsBrightnessContrastFilter):
                        try:
                            f.setBrightness(desired_brightness)
                        except Exception:
                            pass
                        try:
                            f.setContrast(desired_contrast)
                        except Exception:
                            pass
                        applied = True
                    elif QgsHueSaturationFilter is not None and isinstance(f, QgsHueSaturationFilter):
                        try:
                            f.setSaturation(desired_saturation)
                        except Exception:
                            pass
                        applied = True
                except Exception:
                    continue

            # If no existing filters were updated, try to set new ones on the pipe
            if not applied:
                try:
                    if QgsBrightnessContrastFilter is not None:
                        bc_filter = QgsBrightnessContrastFilter()
                        try:
                            bc_filter.setBrightness(desired_brightness)
                        except Exception:
                            pass
                        try:
                            bc_filter.setContrast(desired_contrast)
                        except Exception:
                            pass
                        try:
                            pipe.set(bc_filter)
                            applied = True
                        except Exception:
                            pass

                    if QgsHueSaturationFilter is not None:
                        hs_filter = QgsHueSaturationFilter()
                        try:
                            hs_filter.setSaturation(desired_saturation)
                        except Exception:
                            pass
                        try:
                            pipe.set(hs_filter)
                            applied = True
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                layer.triggerRepaint()
            except Exception:
                pass

            return applied
        except Exception:
            return False

    def undo(self, entry) -> Tuple[bool, str]:
        try:
            payload = entry.undo_payload or {}
            settings = payload.get('settings') or {}

            # Find layer
            layer_id = None
            if entry.layers:
                layer_id = entry.layers[0].get('layer_id')

            layer = None
            if layer_id and QgsProject is not None:
                layer = QgsProject.instance().mapLayer(layer_id)

            if layer is None:
                return False, 'Layer not found for rendering undo'

            success = self._apply_settings_to_layer(layer, settings)
            return (True, 'Rendering restored') if success else (False, 'Failed to restore rendering')
        except Exception as e:
            return False, f'Undo failed: {e}'

    def redo(self, entry) -> Tuple[bool, str]:
        try:
            payload = entry.redo_payload or entry.undo_payload or {}
            settings = payload.get('settings') or {}

            layer_id = None
            if entry.layers:
                layer_id = entry.layers[0].get('layer_id')

            layer = None
            if layer_id and QgsProject is not None:
                layer = QgsProject.instance().mapLayer(layer_id)

            if layer is None:
                return False, 'Layer not found for rendering redo'

            success = self._apply_settings_to_layer(layer, settings)
            return (True, 'Rendering re-applied') if success else (False, 'Failed to re-apply rendering')
        except Exception as e:
            return False, f'Redo failed: {e}'

