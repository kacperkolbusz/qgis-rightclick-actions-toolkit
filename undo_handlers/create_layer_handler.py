"""
Create Layer Undo Handler

Handles undo/redo for actions that CREATE new layers.

Undo: Remove the created layer from the project
Redo: Add the layer back (if stored) or notify user
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler
import os

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer
except ImportError:
    pass


class CreateLayerHandler(BaseUndoHandler):
    """
    Handler for undoing layer creation.
    
    When a layer is created, undo means removing it from the project.
    Note: The layer data may be lost if it's a memory layer.
    """
    
    undo_type = "create_layer"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo layer creation by removing the layer from the project.
        
        Args:
            entry: HistoryEntry with layer info
        
        Returns:
            Tuple of (success, message)
        """
        if not entry.layers:
            return False, "No layer information in undo payload"
        
        removed_count = 0
        
        for layer_info in entry.layers:
            layer_id = layer_info.get('layer_id')
            layer_name = layer_info.get('layer_name', 'Unknown')
            
            if not layer_id:
                continue
            
            layer = QgsProject.instance().mapLayer(layer_id)
            
            if layer:
                QgsProject.instance().removeMapLayer(layer_id)
                removed_count += 1
            else:
                # Layer already removed
                pass
        
        if removed_count > 0:
            return True, f"Layer creation undone ({removed_count} layer(s) removed)"
        else:
            return False, "Layer(s) not found - may have been already removed"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo layer creation.
        
        Note: For memory layers, the data is lost when the layer is removed.
        This method can only restore the layer structure, not its data.
        
        Args:
            entry: HistoryEntry with layer info
        
        Returns:
            Tuple of (success, message)
        """
        # For memory layers, we can't truly redo creation after removal
        # because the data is gone. We can only create an empty layer.
        
        payload = entry.undo_payload or {}

        layer_defs = []
        if 'layer_definitions' in payload:
            layer_defs = payload.get('layer_definitions', [])
        elif 'layer_definition' in payload:
            ld = payload.get('layer_definition')
            if ld:
                layer_defs = [ld]

        if not layer_defs:
            return False, "Cannot redo layer creation: layer definition not stored"

        from qgis.PyQt.QtCore import QByteArray
        import base64
        from qgis.core import QgsFields, QgsField, QgsFeature, QgsGeometry
        from qgis.PyQt.QtCore import QVariant

        created_count = 0
        new_layer_descriptors = []

        for ld in layer_defs:
            try:
                layer_name = ld.get('layer_name', 'Restored Layer')
                crs = ld.get('crs', '')
                geom_type = ld.get('geometry_type', 'Unknown')
                # If the layer definition indicates a raster, try to restore raster
                if ld.get('is_raster'):
                    try:
                        raster_path = ld.get('raster_path')
                        layer = None
                        # Try creating raster from stored path even if file may be virtual (/vsimem etc.)
                        if raster_path:
                            try:
                                layer = QgsRasterLayer(raster_path, layer_name)
                                if not (layer and layer.isValid()):
                                    layer = None
                            except Exception:
                                layer = None

                        # Fallback: try provider or data_source string if available
                        if layer is None:
                            provider_src = ld.get('provider') or ld.get('data_source') or ''
                            if provider_src:
                                try:
                                    layer = QgsRasterLayer(provider_src, layer_name)
                                    if not (layer and layer.isValid()):
                                        layer = None
                                except Exception:
                                    layer = None

                        if layer is None:
                            # Cannot restore raster layer from stored definition
                            continue
                    except Exception:
                        continue

                else:
                    # Create memory vector layer
                    layer = QgsVectorLayer(f"{geom_type}?crs={crs}", layer_name, "memory")
                    if not layer or not layer.isValid():
                        continue

                # Add fields
                fld_list = []
                for f in ld.get('fields', []):
                    name = f.get('name')
                    qmeta = f.get('qmeta_type')
                    if not name:
                        continue
                    try:
                        fld = QgsField(name, int(qmeta) if qmeta is not None else QVariant.String)
                    except Exception:
                        fld = QgsField(name, QVariant.String)
                    fld_list.append(fld)

                if fld_list:
                    layer.dataProvider().addAttributes(fld_list)
                    layer.updateFields()

                # Add features
                feats_to_add = []
                for fb in ld.get('features', []) or []:
                    try:
                        feat = QgsFeature(layer.fields())
                        # Geometry
                        geom_info = fb.get('geometry') or {}
                        wkb_b64 = geom_info.get('wkb_base64')
                        if wkb_b64:
                            try:
                                wkb_bytes = base64.b64decode(wkb_b64)
                                try:
                                    qba = QByteArray(wkb_bytes)
                                    geom = QgsGeometry.fromWkb(qba)
                                except Exception:
                                    # Fallback to instance method
                                    geom = QgsGeometry()
                                    geom.fromWkb(wkb_bytes)
                                feat.setGeometry(geom)
                            except Exception:
                                pass

                        # Attributes
                        attrs = fb.get('attributes', {}) or {}
                        for fld in layer.fields():
                            name = fld.name()
                            if name in attrs:
                                try:
                                    feat.setAttribute(name, attrs.get(name))
                                except Exception:
                                    pass

                        feats_to_add.append(feat)
                    except Exception:
                        continue

                if feats_to_add:
                    layer.dataProvider().addFeatures(feats_to_add)
                    layer.updateExtents()

                # Add restored layer to project
                QgsProject.instance().addMapLayer(layer)
                created_count += 1

                # Create and collect new layer descriptor to update history entry
                try:
                    from ..history_manager import get_history_manager
                    hm = get_history_manager()
                    # history manager expects a vector layer; create a safe descriptor for rasters
                    try:
                        new_layer_descriptors.append(hm.create_layer_descriptor(layer))
                    except Exception:
                        # Fallback descriptor for raster or unexpected layer types
                        try:
                            desc = {
                                'layer_id': layer.id(),
                                'layer_name': layer.name(),
                                'data_source': getattr(layer, 'source', lambda: '')(),
                                'is_temporary': False,
                                'geometry_type': '',
                                'crs': layer.crs().authid() if hasattr(layer, 'crs') and layer.crs().isValid() else ''
                            }
                            new_layer_descriptors.append(desc)
                        except Exception:
                            new_layer_descriptors.append({
                                'layer_id': getattr(layer, 'id', lambda: '')(),
                                'layer_name': getattr(layer, 'name', lambda: '')()
                            })
                except Exception:
                    # Fallback: minimal descriptor
                    new_layer_descriptors.append({
                        'layer_id': layer.id(),
                        'layer_name': layer.name()
                    })

                # Try to apply simple renderer properties if stored
                try:
                    renderer_info = ld.get('renderer') or {}
                    # Prefer full serialized style if available
                    style_str = renderer_info.get('style') or renderer_info.get('style_xml')
                    applied_style = False

                    if style_str:
                        try:
                            # Try known QGIS API calls to load style from string
                            # APIs differ across QGIS versions; try safely
                            if hasattr(layer, 'loadStyleFromString'):
                                try:
                                    layer.loadStyleFromString(style_str)
                                    applied_style = True
                                except Exception:
                                    applied_style = False

                            if not applied_style and hasattr(layer, 'loadNamedStyle'):
                                try:
                                    # loadNamedStyle may accept a filename, but some bindings support passing a string
                                    layer.loadNamedStyle(style_str)
                                    applied_style = True
                                except Exception:
                                    applied_style = False

                            # Some versions expose style manager methods
                            if not applied_style:
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
                                            applied_style = True
                                        except Exception:
                                            applied_style = False
                                except Exception:
                                    applied_style = False
                        except Exception:
                            applied_style = False

                    # Fallback: try simple symbol properties
                    if not applied_style:
                        try:
                            sym_props = renderer_info.get('symbol_properties') if renderer_info else None
                            if sym_props:
                                try:
                                    from qgis.core import QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol
                                    geom_type = layer.geometryType()
                                    symbol = None
                                    if geom_type == 0:  # point
                                        try:
                                            symbol = QgsMarkerSymbol.createSimple(sym_props)
                                        except Exception:
                                            symbol = None
                                    elif geom_type == 1:  # line
                                        try:
                                            symbol = QgsLineSymbol.createSimple(sym_props)
                                        except Exception:
                                            symbol = None
                                    else:  # polygon
                                        try:
                                            symbol = QgsFillSymbol.createSimple(sym_props)
                                        except Exception:
                                            symbol = None

                                    if symbol is not None:
                                        try:
                                            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                                            layer.triggerRepaint()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass

                # Apply simple labeling if stored
                try:
                    labeling_info = ld.get('labeling') or {}
                    if labeling_info and labeling_info.get('enabled'):
                        try:
                            from qgis.core import QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
                            from qgis.PyQt.QtGui import QColor

                            pal = QgsPalLayerSettings()
                            pal.enabled = True
                            fieldName = labeling_info.get('fieldName')
                            if fieldName:
                                pal.fieldName = fieldName
                                pal.isExpression = bool(labeling_info.get('isExpression', False))

                            # Text format
                            tf = QgsTextFormat()
                            size = labeling_info.get('size')
                            try:
                                if size:
                                    tf.setSize(float(size))
                            except Exception:
                                pass
                            pal.setFormat(tf)

                            placement = labeling_info.get('placement')
                            if placement is not None:
                                try:
                                    pal.placement = int(placement)
                                except Exception:
                                    pass

                            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
                            layer.setLabelsEnabled(True)
                        except Exception:
                            pass
                except Exception:
                    pass

            except Exception as e:
                # continue with other layer definitions
                continue

        # If we created layers, update the entry.layers so future undo/redo uses correct IDs
        if created_count > 0:
            try:
                # Replace entry.layers with new descriptors
                entry.layers = new_layer_descriptors
                # Also update undo_payload layer ids if present
                if entry.undo_payload and isinstance(entry.undo_payload, dict):
                    if 'layer_definitions' in entry.undo_payload:
                        # keep original definitions but no layer_ids
                        pass
                    else:
                        entry.undo_payload['layer_ids'] = [d.get('layer_id') for d in new_layer_descriptors]
            except Exception:
                pass

            return True, f"Restored {created_count} layer(s)"
        else:
            return False, "Failed to recreate stored layer definitions"


# Create singleton instance for registration
handler = CreateLayerHandler()
