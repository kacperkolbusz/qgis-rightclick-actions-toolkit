"""
Trace Polygon Layer Outline Action for Right-click Utilities and Shortcuts Hub

Analyzes a polygon layer, unions all polygon features into one combined shape,
then extracts the outer outline as a single line layer. The result is one line
that traces around the entire polygon layer — not individual per-polygon outlines.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsFeatureRequest,
    QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant, QMetaType, QDateTime
from qgis.PyQt.QtWidgets import QFileDialog


class TracePolygonLayerOutlineAction(BaseAction):
    """Action to trace the combined outer outline of all polygons in a layer as one line."""

    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()

        # Required properties
        self.action_id = 'trace_polygon_layer_outline'
        self.name = 'Trace Polygon Layer Outline'
        self.category = 'Geometry'
        self.description = (
            'Unions all polygon features in the layer into one combined shape, '
            'then traces a single outline line around the entire polygon layer. '
            'The result is one line feature (or multi-line if the layer has '
            'disconnected polygon groups) rather than separate outlines per polygon.'
        )
        self.enabled = True

        # Action scoping - works on entire polygon layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        # Feature type support - only polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

        # Internal state for undo support
        self._created_layer_id = None

    # ------------------------------------------------------------------
    # Settings schema
    # ------------------------------------------------------------------

    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            'layer_storage_type': {
                'type': 'choice',
                'label': 'Layer Storage Type',
                'default': 'temporary',
                'description': (
                    'Temporary layers are held in memory only (lost when QGIS closes). '
                    'Permanent layers are saved to disk as a file.'
                ),
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'label': 'Output Layer Name',
                'default': '{layer_name} - Outline',
                'description': (
                    'Name for the output line layer. '
                    'Use {layer_name} to include the source layer name, '
                    '{timestamp} for the current date/time.'
                ),
            },
            'add_to_project': {
                'type': 'bool',
                'label': 'Add to Project',
                'default': True,
                'description': 'Automatically add the output line layer to the project.',
            },
            'zoom_to_layer': {
                'type': 'bool',
                'label': 'Zoom to Result',
                'default': True,
                'description': 'Automatically zoom to the new line layer after creation.',
            },
            'show_success_message': {
                'type': 'bool',
                'label': 'Show Success Message',
                'default': True,
                'description': 'Display a summary message after the conversion finishes.',
            },
        }

    # ------------------------------------------------------------------
    # Undo support
    # ------------------------------------------------------------------

    def supports_undo(self) -> bool:
        """Undo removes the created layer from the project."""
        return True

    def get_undo_category(self) -> str:
        return 'trivial'

    def get_undo_payload(self, context, execute_result=None):
        if self._created_layer_id is None:
            return {}
        return {
            'undo_type': 'create_layer',
            'layer_id': self._created_layer_id,
        }

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, context):
        """Execute the convert-polygon-to-lines action."""
        self._created_layer_id = None

        # ---- Retrieve and validate settings ----
        try:
            storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            name_template = str(self.get_setting('layer_name_template', '{layer_name} - Outline'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_layer = bool(self.get_setting('zoom_to_layer', True))
            show_success = bool(self.get_setting('show_success_message', True))
        except (ValueError, TypeError) as e:
            self.show_error('Error', f'Invalid setting values: {e}')
            return

        # ---- Get source layer ----
        layer = context.get('layer')
        if not isinstance(layer, QgsVectorLayer):
            self.show_error('Error', 'No valid polygon layer found in context.')
            return

        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
            self.show_error('Error', 'The selected layer is not a polygon layer.')
            return

        source_features = list(layer.getFeatures())
        if not source_features:
            self.show_warning('No Features', 'The selected layer contains no features.')
            return

        layer_crs = layer.crs()

        # ---- Collect valid geometries ----
        geoms = []
        skipped = 0
        for feat in source_features:
            g = feat.geometry()
            if g and not g.isEmpty() and g.isGeosValid():
                geoms.append(g)
            else:
                # Try to fix invalid geometry before discarding
                if g and not g.isEmpty():
                    fixed = g.makeValid()
                    if fixed and not fixed.isEmpty():
                        geoms.append(fixed)
                    else:
                        skipped += 1
                else:
                    skipped += 1

        if not geoms:
            self.show_warning('No Valid Geometries', 'No valid polygon geometries found in the layer.')
            return

        # ---- Compute convex hull across all polygon geometries ----
        # Merge all geometries into one collection, then compute the convex hull.
        # This produces exactly ONE closed line that wraps tightly around all
        # outermost polygon vertices — like a rubber band snapped around them.
        # Works regardless of whether the polygons touch each other or not.
        collected = QgsGeometry.collectGeometry(geoms)
        if collected is None or collected.isEmpty():
            self.show_error('Error', 'Failed to collect polygon geometries.')
            return

        hull_polygon = collected.convexHull()
        if hull_polygon is None or hull_polygon.isEmpty():
            self.show_error('Error', 'Failed to compute convex hull of the layer.')
            return

        # Extract the exterior ring of the hull as a line
        hull_rings = hull_polygon.asPolygon()
        if not hull_rings or not hull_rings[0]:
            self.show_error('Error', 'Convex hull exterior ring is empty.')
            return

        boundary = QgsGeometry.fromPolylineXY(hull_rings[0])
        if boundary is None or boundary.isEmpty():
            self.show_error('Error', 'Extracted outline geometry is empty.')
            return

        # ---- Build output layer name ----
        timestamp = QDateTime.currentDateTime().toString('yyyyMMdd_HHmmss')
        output_name = (
            name_template
            .replace('{layer_name}', layer.name())
            .replace('{timestamp}', timestamp)
        )

        # ---- Build output fields ----
        out_fields = QgsFields()

        src_count_field = QgsField()
        src_count_field.setName('src_count')
        src_count_field.setType(QMetaType.Type.Int)
        out_fields.append(src_count_field)

        src_layer_field = QgsField()
        src_layer_field.setName('src_layer')
        src_layer_field.setType(QMetaType.Type.QString)
        src_layer_field.setLength(100)
        out_fields.append(src_layer_field)

        # ---- Create output layer ----
        crs_auth = layer_crs.authid() if layer_crs.authid() else 'EPSG:4326'
        layer_uri = f'MultiLineString?crs={crs_auth}'
        out_layer = QgsVectorLayer(layer_uri, output_name, 'memory')

        if not out_layer.isValid():
            self.show_error('Error', 'Failed to create output line layer.')
            return

        out_layer.dataProvider().addAttributes(out_fields.toList())
        out_layer.updateFields()

        # ---- Write the single combined boundary feature ----
        out_feat = QgsFeature(out_layer.fields())
        out_feat.setGeometry(boundary)
        out_feat.setAttribute('src_count', len(geoms))
        out_feat.setAttribute('src_layer', layer.name()[:100])

        success, _ = out_layer.dataProvider().addFeatures([out_feat])
        if not success:
            self.show_error('Error', 'Failed to write boundary feature to the output layer.')
            return

        out_layer.updateExtents()

        # ---- Handle permanent storage ----
        if storage_type == 'permanent':
            save_path, _ = QFileDialog.getSaveFileName(
                None,
                'Save Outline Layer As',
                f'{output_name}.gpkg',
                'GeoPackage (*.gpkg);;Shapefile (*.shp);;All Files (*.*)'
            )
            if not save_path:
                storage_type = 'temporary'
            else:
                from qgis.core import QgsVectorFileWriter, QgsCoordinateTransformContext
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = (
                    'GPKG' if save_path.lower().endswith('.gpkg') else 'ESRI Shapefile'
                )
                options.fileEncoding = 'UTF-8'

                error_code, error_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    out_layer, save_path,
                    QgsCoordinateTransformContext(), options
                )

                if error_code != QgsVectorFileWriter.NoError:
                    self.show_error('Save Error', f'Could not save layer to disk: {error_msg}')
                    storage_type = 'temporary'
                else:
                    out_layer = QgsVectorLayer(save_path, output_name, 'ogr')
                    if not out_layer.isValid():
                        self.show_error('Error', 'Saved file layer could not be loaded.')
                        return

        # ---- Add to project ----
        if add_to_project:
            QgsProject.instance().addMapLayer(out_layer)
            self._created_layer_id = out_layer.id()

        # ---- Zoom to result ----
        if zoom_to_layer and add_to_project:
            canvas = context.get('canvas')
            if canvas:
                try:
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    extent = out_layer.extent()
                    if canvas_crs != layer_crs:
                        transform = QgsCoordinateTransform(
                            layer_crs, canvas_crs, QgsProject.instance()
                        )
                        extent = transform.transformBoundingBox(extent)
                    extent.grow(extent.width() * 0.05 + extent.height() * 0.05)
                    canvas.setExtent(extent)
                    canvas.refresh()
                except Exception:
                    pass

        # ---- Record to history ----
        layer_info = self.create_layer_descriptor(out_layer) if add_to_project else {}
        self.record_to_history(
            description=(
                f"Traced convex hull outline of polygon layer '{layer.name()}' "
                f"({len(geoms)} polygons, 1 outline line)"
            ),
            undo_type='create_layer',
            layers=[layer_info],
            meta={
                'source_layer': layer.name(),
                'source_feature_count': len(source_features),
                'unioned_count': len(geoms),
                'skipped_count': skipped,
                'storage_type': storage_type,
            }
        )

        # ---- Success message ----
        if show_success:
            detail_lines = [
                f'Source layer:     {layer.name()}',
                f'Polygons unioned: {len(geoms)}',
                f'Output layer:     {output_name}',
                f'Storage type:     {storage_type}',
            ]
            if skipped:
                detail_lines.append(f'Features skipped (invalid geometry): {skipped}')

            self.show_info(
                'Trace Polygon Layer Outline — Complete',
                '\n'.join(detail_lines)
            )


# REQUIRED: Create global instance for automatic discovery
trace_polygon_layer_outline = TracePolygonLayerOutlineAction()
