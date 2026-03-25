"""
Undo handler for layer style updates

Handles undo/redo for the custom 'update_layer_style' undo type. Expects
the history entry.undo_payload to contain a 'layers' list with dicts having:
  - layer_id
  - old_style (qml string or None)
  - old_custom (dict)
  - new_style (qml string or None)
  - new_custom (dict)

The handler restores old_style/old_custom on undo and reapplies new_style/new_custom on redo.
"""

from typing import Tuple
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsFeatureRenderer, QgsReadWriteContext
    from qgis.PyQt.QtXml import QDomDocument
except Exception:
    QgsProject = None
    QgsFeatureRenderer = None
    QgsReadWriteContext = None
    QDomDocument = None


class UpdateLayerStyleHandler(BaseUndoHandler):
    undo_type = 'update_layer_style'

    def _apply_style_string(self, layer, style_str) -> bool:
        if not layer or not style_str:
            return False
        try:
            # Prefer high-level style loading APIs which restore renderer, labeling,
            # and other layer-level settings. Try multiple known QGIS calls.
            try:
                if hasattr(layer, 'loadStyleFromString'):
                    try:
                        layer.loadStyleFromString(style_str)
                        return True
                    except Exception:
                        pass

                if hasattr(layer, 'loadNamedStyle'):
                    try:
                        layer.loadNamedStyle(style_str)
                        return True
                    except Exception:
                        pass

                # Try style manager approach
                try:
                    sm = getattr(layer, 'styleManager', None)
                    if callable(sm):
                        mgr = sm()
                    else:
                        mgr = sm
                    if mgr is not None and hasattr(mgr, 'addStyle'):
                        try:
                            mgr.addStyle('restored', style_str)
                            mgr.applyStyle('restored')
                            return True
                        except Exception:
                            pass
                except Exception:
                    pass

            except Exception:
                pass

            # Fallback: try to parse renderer element and load renderer only
            if QDomDocument is None or QgsFeatureRenderer is None or QgsReadWriteContext is None:
                return False
            doc = QDomDocument()
            if not doc.setContent(style_str):
                return False
            elem = doc.documentElement()
            renderer_elem = elem.firstChildElement('renderer-v2')
            # Try to find renderer element more robustly if not a direct child
            if renderer_elem.isNull():
                child = elem.firstChild()
                while not child.isNull():
                    try:
                        if child.nodeName() == 'renderer-v2':
                            renderer_elem = child.toElement()
                            break
                    except Exception:
                        pass
                    child = child.nextSibling()

            if renderer_elem.isNull():
                return False
            ctx = QgsReadWriteContext()
            try:
                if hasattr(ctx, 'setProject'):
                    ctx.setProject(QgsProject.instance())
            except Exception:
                pass
            r = QgsFeatureRenderer.load(renderer_elem, ctx)
            if not r:
                return False
            layer.setRenderer(r)
            return True
        except Exception:
            return False

    def _apply_custom_props(self, layer, props: dict) -> None:
        if not layer or not isinstance(props, dict):
            return
        try:
            # Remove existing custom properties then set provided ones
            try:
                for k in list(layer.customPropertyKeys()):
                    try:
                        layer.removeCustomProperty(k)
                    except Exception:
                        pass
            except Exception:
                pass

            for k, v in props.items():
                try:
                    layer.setCustomProperty(k, v)
                except Exception:
                    pass
        except Exception:
            pass

    def undo(self, entry) -> Tuple[bool, str]:
        try:
            payload = entry.undo_payload or {}
            layers = payload.get('layers', [])
            if not layers:
                return False, 'No layer data in undo payload'

            for info in layers:
                layer_id = info.get('layer_id')
                old_style = info.get('old_style')
                old_custom = info.get('old_custom', {}) or {}

                layer = None
                if QgsProject is not None and layer_id:
                    layer = QgsProject.instance().mapLayer(layer_id)

                if not layer:
                    # skip missing layers
                    continue

                # Try to restore style string first
                applied = False
                if old_style:
                    applied = self._apply_style_string(layer, old_style)

                # Restore custom props regardless
                self._apply_custom_props(layer, old_custom)

                try:
                    layer.triggerRepaint()
                except Exception:
                    pass

            return True, 'Layer styles restored'
        except Exception as e:
            return False, f'Undo failed: {e}'

    def redo(self, entry) -> Tuple[bool, str]:
        try:
            payload = entry.redo_payload or entry.undo_payload or {}
            layers = payload.get('layers', [])
            if not layers:
                return False, 'No layer data in redo payload'

            for info in layers:
                layer_id = info.get('layer_id')
                new_style = info.get('new_style')
                new_custom = info.get('new_custom', {}) or {}

                layer = None
                if QgsProject is not None and layer_id:
                    layer = QgsProject.instance().mapLayer(layer_id)

                if not layer:
                    continue

                applied = False
                if new_style:
                    applied = self._apply_style_string(layer, new_style)

                self._apply_custom_props(layer, new_custom)

                try:
                    layer.triggerRepaint()
                except Exception:
                    pass

            return True, 'Layer styles re-applied'
        except Exception as e:
            return False, f'Redo failed: {e}'


# Singleton handler instance used by the registry discovery
handler = UpdateLayerStyleHandler()
