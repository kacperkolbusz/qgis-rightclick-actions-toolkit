"""
Create Buffer Around Polygon Layer

Creates buffers around all polygon features in the clicked layer and writes them to a new polygon layer.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsFeature, QgsGeometry, QgsField,
    QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QInputDialog


class CreateBufferAroundPolygonLayerAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = "create_buffer_around_polygon_layer"
        self.name = "Create Buffer Around Polygon Layer"
        self.category = "Geometry"
        self.description = "Create buffers around all polygons in the clicked polygon layer."
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def get_settings_schema(self):
        return {
            'buffer_distance': {'type': 'float', 'default': 100.0},
            'buffer_segments': {'type': 'int', 'default': 8},
            'output_layer_name': {'type': 'str', 'default': 'Polygon Buffers'},
            'add_to_project': {'type': 'bool', 'default': True},
            'zoom_to_result': {'type': 'bool', 'default': True}
        }

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def execute(self, context):
        try:
            default_buffer = float(self.get_setting('buffer_distance', 100.0))
            segments = int(self.get_setting('buffer_segments', 8))
            out_name = str(self.get_setting('output_layer_name', 'Polygon Buffers'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_result = bool(self.get_setting('zoom_to_result', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {e}")
            return

        layer = context.get('layer')
        if not isinstance(layer, QgsVectorLayer):
            self.show_error("Error", "Target layer is not a vector layer")
            return

        # Ask user for buffer distance each time
        buffer_distance, ok = QInputDialog.getDouble(
            None,
            "Buffer Distance",
            f"Enter buffer distance for layer '{layer.name()}' (map units):",
            default_buffer,
            0.0,
            1e12,
            3
        )
        if not ok:
            return

        features = list(layer.getFeatures())
        if not features:
            self.show_warning("No features", "The selected layer contains no features")
            return

        layer_crs = layer.crs()
        calc_crs = QgsCoordinateReferenceSystem('EPSG:3857') if layer_crs.isGeographic() else None

        crs_auth = layer.crs().authid() if layer.crs().isValid() else ''
        uri = f"Polygon?crs={crs_auth}" if crs_auth else "Polygon"
        out_layer = QgsVectorLayer(uri, out_name, "memory")
        if not out_layer.isValid():
            self.show_error("Error", "Failed to create output layer")
            return

        out_layer.dataProvider().addAttributes([QgsField('source_fid', QVariant.Int)])
        out_layer.updateFields()

        out_feats = []
        for f in features:
            geom = QgsGeometry(f.geometry())
            if calc_crs:
                try:
                    transform_to_calc = QgsCoordinateTransform(layer_crs, calc_crs, QgsProject.instance())
                    geom.transform(transform_to_calc)
                except Exception:
                    pass

            buf = geom.buffer(buffer_distance, segments)
            if buf is None or buf.isEmpty():
                continue

            if calc_crs:
                try:
                    rev = QgsCoordinateTransform(calc_crs, layer_crs, QgsProject.instance())
                    buf.transform(rev)
                except Exception:
                    pass

            newf = QgsFeature(out_layer.fields())
            newf.setGeometry(buf)
            newf.setAttribute('source_fid', int(f.id()))
            out_feats.append(newf)

        if not out_feats:
            self.show_error("Error", "No buffers created")
            return

        ok, added = out_layer.dataProvider().addFeatures(out_feats)
        if not ok:
            self.show_error("Error", "Failed to add buffered features to output layer")
            return

        out_layer.updateExtents()
        if add_to_project:
            QgsProject.instance().addMapLayer(out_layer)

        if zoom_to_result:
            try:
                canvas = context.get('canvas')
                if canvas:
                    canvas.setExtent(out_layer.extent())
                    canvas.refresh()
            except Exception:
                pass

        created = [self.create_feature_backup(f, out_layer) for f in out_layer.getFeatures()]

        fields = []
        try:
            for field in out_layer.fields():
                fields.append({'name': field.name(), 'qmeta_type': field.type(), 'length': field.length(), 'precision': field.precision()})
        except Exception:
            pass

        layer_def = {
            'layer_name': out_layer.name(),
            'crs': out_layer.crs().authid() if out_layer.crs().isValid() else '',
            'geometry_type': QgsWkbTypes.displayString(out_layer.wkbType()),
            'fields': fields,
            'features': created
        }

        self.record_to_history(
            description=f"Created {len(created)} buffers for layer {layer.name()}",
            undo_type='create_layer',
            can_undo=True,
            undo_payload={'layer_definitions': [layer_def]},
            layers=[self.create_layer_descriptor(out_layer)],
            features=created
        )


# global instance
create_buffer_around_polygon_layer = CreateBufferAroundPolygonLayerAction()
