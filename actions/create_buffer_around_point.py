"""
Create Buffer Around Point

Creates a polygon buffer around a single point feature.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsFeature, QgsGeometry, QgsField,
    QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QInputDialog


class CreateBufferAroundPointAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = "create_buffer_around_point"
        self.name = "Create Buffer Around Point"
        self.category = "Geometry"
        self.description = "Create a polygon buffer around the clicked point feature."
        self.enabled = True

        # Feature scope
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Support point clicks
        self.set_supported_click_types(['point'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    def get_settings_schema(self):
        return {
            'buffer_distance': {
                'type': 'float',
                'default': 100.0,
                'label': 'Buffer distance',
                'description': 'Buffer distance in map units (when layer CRS is geographic, calculation is done in WebMercator)',
                'min': 0.0
            },
            'buffer_segments': {
                'type': 'int',
                'default': 8,
                'label': 'Segments',
                'description': 'Number of segments to approximate curves',
                'min': 1,
                'max': 128
            },
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'options': ['temporary', 'permanent']
            },
            'output_layer_name': {
                'type': 'str',
                'default': 'Point Buffer',
                'label': 'Output layer name'
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project'
            },
            'zoom_to_result': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Result'
            }
        }

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def execute(self, context):
        try:
            default_buffer = float(self.get_setting('buffer_distance', 100.0))
            segments = int(self.get_setting('buffer_segments', 8))
            storage = str(self.get_setting('layer_storage_type', 'temporary'))
            out_name = str(self.get_setting('output_layer_name', 'Point Buffer'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_result = bool(self.get_setting('zoom_to_result', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {e}")
            return

        # Ask user for buffer distance each time
        buffer_distance, ok = QInputDialog.getDouble(
            None,
            "Buffer Distance",
            "Enter buffer distance (map units):",
            default_buffer,
            0.0,
            1e12,
            3
        )
        if not ok:
            return

        detected = context.get('detected_features', [])
        if not detected:
            self.show_error("Error", "No feature detected")
            return

        det = detected[0]
        layer = det.layer
        feature = det.feature

        if not isinstance(layer, QgsVectorLayer):
            self.show_error("Error", "Target layer is not a vector layer")
            return

        # Prepare geometry and handle geographic CRS by transforming to WebMercator for buffering
        geom = QgsGeometry(feature.geometry())
        layer_crs = layer.crs()
        calc_crs = None
        transformed_geom = QgsGeometry(geom)

        if layer_crs.isGeographic():
            try:
                calc_crs = QgsCoordinateReferenceSystem('EPSG:3857')
                transform_to_calc = QgsCoordinateTransform(layer_crs, calc_crs, QgsProject.instance())
                transformed_geom.transform(transform_to_calc)
            except Exception as e:
                self.show_error("CRS Error", f"Failed to transform geometry for buffering: {e}")
                return

        # Buffer in calculation CRS (or layer CRS if not transformed)
        buffer_geom = transformed_geom.buffer(buffer_distance, segments)
        if buffer_geom is None or buffer_geom.isEmpty():
            self.show_error("Error", "Failed to create buffer geometry")
            return

        # Transform buffer back to layer CRS if needed
        if layer_crs.isGeographic():
            try:
                rev = QgsCoordinateTransform(calc_crs, layer_crs, QgsProject.instance())
                buffer_geom.transform(rev)
            except Exception:
                pass

        # Create output layer
        crs_auth = layer.crs().authid() if layer.crs().isValid() else ''
        uri = f"Polygon?crs={crs_auth}" if crs_auth else "Polygon"
        out_layer = QgsVectorLayer(uri, out_name, "memory")
        if not out_layer.isValid():
            self.show_error("Error", "Failed to create output layer")
            return

        # Add simple attribute to link to source
        out_layer.dataProvider().addAttributes([QgsField('source_fid', QVariant.Int)])
        out_layer.updateFields()

        # Create and add feature
        out_feat = QgsFeature(out_layer.fields())
        out_feat.setGeometry(buffer_geom)
        out_feat.setAttribute('source_fid', int(feature.id()))

        ok, added = out_layer.dataProvider().addFeatures([out_feat])
        if not ok:
            self.show_error("Error", "Failed to add buffered feature to output layer")
            return

        out_layer.updateExtents()

        # Optionally add to project
        if add_to_project:
            QgsProject.instance().addMapLayer(out_layer)

        # Zoom
        if zoom_to_result:
            try:
                canvas = context.get('canvas')
                if canvas:
                    canvas.setExtent(out_layer.extent())
                    canvas.refresh()
            except Exception:
                pass

        # Record history
        created = []
        for f in out_layer.getFeatures():
            created.append(self.create_feature_backup(f, out_layer))

        # Build minimal layer definition for redo
        fields = []
        try:
            for field in out_layer.fields():
                fields.append({
                    'name': field.name(),
                    'qmeta_type': field.type(),
                    'length': field.length(),
                    'precision': field.precision()
                })
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
            description=f"Created buffer for feature {feature.id()}",
            undo_type='create_layer',
            can_undo=True,
            undo_payload={'layer_definitions': [layer_def]},
            layers=[self.create_layer_descriptor(out_layer)],
            features=created
        )


# global instance
create_buffer_around_point = CreateBufferAroundPointAction()
