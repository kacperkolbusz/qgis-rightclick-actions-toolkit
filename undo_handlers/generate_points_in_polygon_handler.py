"""
Undo handler for generate_points_in_polygon action

Removes the generated point layer on undo, and restores it on redo if possible.
"""

from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject
except ImportError:
    pass

class GeneratePointsInPolygonUndoHandler(BaseUndoHandler):
    undo_type = "generate_points_in_polygon"

    def undo(self, entry):
        # Remove the generated layer by ID
        for layer_info in entry.layers:
            layer_id = layer_info.get('layer_id')
            if not layer_id:
                continue
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                QgsProject.instance().removeMapLayer(layer_id)
        return True, "Generated points layer removed."

    def redo(self, entry):
        # Restore the generated layer from the stored definition
        payload = entry.undo_payload or {}
        layer_def = payload.get('layer_definition')
        if not layer_def:
            return False, "No layer definition stored for redo."

        try:
            from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsProject, QgsWkbTypes
            from qgis.PyQt.QtCore import QVariant, QByteArray
            import base64

            layer_name = layer_def.get('layer_name', 'Restored Points')
            crs = layer_def.get('crs', '')
            geometry_type = layer_def.get('geometry_type', 'Point')
            fields_def = layer_def.get('fields', [])
            features_def = layer_def.get('features', [])

            # Robust geometry type conversion for repeated undo/redo
            geometry_type_str = geometry_type
            if isinstance(geometry_type, int):
                try:
                    geometry_type_str = QgsWkbTypes.displayString(QgsWkbTypes.Type(geometry_type))
                except Exception:
                    geometry_type_str = 'Point'
            if isinstance(geometry_type_str, str):
                # Use only the geometry part (e.g., 'Point' from 'PointZ')
                geometry_type_str = geometry_type_str.split('Z')[0].split('M')[0].split('25D')[0].strip()
                if geometry_type_str.lower().startswith('multi'):
                    geometry_type_str = geometry_type_str.capitalize()

            # Create memory vector layer
            layer = QgsVectorLayer(f"{geometry_type_str}?crs={crs}", layer_name, "memory")
            if not layer or not layer.isValid():
                return False, f"Failed to create memory layer for redo. Type: {geometry_type_str}, CRS: {crs}"

            # Add fields
            qfields = []
            for f in fields_def:
                name = f.get('name')
                qmeta = f.get('qmeta_type')
                if not name:
                    continue
                try:
                    fld = QgsField(name, int(qmeta) if qmeta is not None else QVariant.String)
                except Exception:
                    fld = QgsField(name, QVariant.String)
                qfields.append(fld)
            if qfields:
                layer.dataProvider().addAttributes(qfields)
                layer.updateFields()

            # Add features
            feats_to_add = []
            for fb in features_def:
                try:
                    feat = QgsFeature(layer.fields())
                    # Geometry
                    geom_info = fb.get('geometry') or {}
                    wkb_b64 = geom_info.get('wkb_base64')
                    if wkb_b64:
                        try:
                            wkb_bytes = base64.b64decode(wkb_b64)
                            qba = QByteArray(wkb_bytes)
                            geom = QgsGeometry.fromWkb(qba)
                        except Exception:
                            geom = QgsGeometry()
                            geom.fromWkb(wkb_bytes)
                        feat.setGeometry(geom)
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
            # Update entry.layers and undo_payload with new layer id for repeated undo/redo
            try:
                from ..history_manager import get_history_manager
                hm = get_history_manager()
                new_layer_desc = hm.create_layer_descriptor(layer)
                entry.layers = [new_layer_desc]
                if entry.undo_payload and isinstance(entry.undo_payload, dict):
                    entry.undo_payload['output_layer_id'] = layer.id()
            except Exception:
                pass
            return True, "Generated points layer restored."
        except Exception as e:
            return False, f"Failed to redo generated points layer: {str(e)}"

handler = GeneratePointsInPolygonUndoHandler()
