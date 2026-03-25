"""
Create Lines Along Line Between Connected Points

Detects point features that lie on the clicked line, asks the user to
choose which point layer and which field to use for labeling, then
creates a new line layer with segments that follow the original line
between consecutive points. Each segment has attributes `from`, `to`,
and `length` (measured along the line).
"""

from .base_action import BaseAction
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsWkbTypes,
    QgsPointXY,
    QgsFeatureRequest,
    QgsDistanceArea,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QInputDialog


class CreateLinesAlongLineBetweenPointsAction(BaseAction):
    """Create line segments along a line between connected points.

    - Detects point layers with points that lie on the clicked line.
    - Lets the user choose which point layer (if multiple) and which
      field from that layer to use for `from`/`to` labels.
    - Builds a memory line layer with attributes: `from` (str), `to` (str),
      `length` (float) and geometries that follow the original line
      between consecutive points in the order along the line.
    """

    def __init__(self):
        super().__init__()
        self.action_id = "create_lines_along_line_between_points"
        self.name = "Create Lines Along Line Between Points"
        self.category = "Geometry"
        self.description = (
            "Create line segments following a line between connected points. "
            "Segments get attributes 'from', 'to' (values from chosen point field) "
            "and 'length' (measured along the line)."
        )
        self.enabled = True

        # Scope & supported types
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

    def execute(self, context):
        try:
            # Extract clicked feature and layer from context
            feature = context.get('feature') or None
            line_layer = context.get('layer') or None
            if feature is None or line_layer is None:
                self.show_error('Error', 'No line feature available in context')
                return

            line_geom = feature.geometry()
            if line_geom is None or line_geom.isEmpty():
                self.show_error('Error', 'Selected line has no geometry')
                return

            project = QgsProject.instance()

            # Find point layers that have points lying on this line
            connected_layers = {}
            # tolerance in layer units
            tol = 1e-6

            for lyr in project.mapLayers().values():
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                # only point layers
                if lyr.geometryType() != QgsWkbTypes.PointGeometry:
                    continue

                # bounding box filter to speed up
                bbox = line_geom.boundingBox()
                req = QgsFeatureRequest().setFilterRect(bbox)
                pts = []
                transform_needed = False
                try:
                    line_crs = line_layer.crs()
                    pt_crs = lyr.crs()
                    transform_needed = (line_crs != pt_crs)
                except Exception:
                    transform_needed = False

                for pt_feat in lyr.getFeatures(req):
                    try:
                        pt_geom = pt_feat.geometry()
                        if pt_geom is None or pt_geom.isEmpty():
                            continue
                        # transform point geometry to line CRS if needed
                        if transform_needed:
                            from qgis.core import QgsCoordinateTransform
                            tr = QgsCoordinateTransform(lyr.crs(), line_layer.crs(), QgsProject.instance())
                            pt_geom = pt_geom.clone()
                            pt_geom.transform(tr)

                        # Check distance from point to line
                        if line_geom.distance(pt_geom) <= tol:
                            # compute distance along line for ordering
                            try:
                                along = line_geom.lineLocatePoint(pt_geom.asPoint())
                            except Exception:
                                # fallback: use interpolate search by sampling
                                along = None

                            pts.append({'feature': pt_feat, 'geom': pt_geom, 'along': along})
                    except Exception:
                        continue

                if pts:
                    connected_layers[lyr.id()] = {'layer': lyr, 'points': pts}

            if not connected_layers:
                self.show_info('No connected points', 'No point features were found on this line')
                return

            # If multiple point layers found, ask user to choose one
            chosen_layer = None
            if len(connected_layers) == 1:
                chosen_layer = list(connected_layers.values())[0]['layer']
            else:
                items = [v['layer'].name() for v in connected_layers.values()]
                ids = [k for k in connected_layers.keys()]
                chosen_name, ok = QInputDialog.getItem(None, 'Choose point layer', 'Point layer:', items, 0, False)
                if not ok:
                    return
                idx = items.index(chosen_name)
                chosen_layer = project.mapLayer(ids[idx])

            if chosen_layer is None:
                self.show_error('Error', 'No point layer selected')
                return

            points_info = connected_layers.get(chosen_layer.id())['points']

            # Ask user to pick a field from chosen point layer
            field_names = [f.name() for f in chosen_layer.fields()]
            if not field_names:
                self.show_error('Error', 'Chosen point layer has no fields')
                return

            field_name, ok = QInputDialog.getItem(None, 'Choose field', 'Field to use for labels:', field_names, 0, False)
            if not ok:
                return

            # Ensure we have 'along' values for ordering
            # If some along are None, compute approximate along by sampling
            line_length = line_geom.length()
            for p in points_info:
                if p['along'] is None:
                    # brute-force sample search: find closest interpolation distance
                    best_d = None
                    best_dist = float('inf')
                    samples = 200
                    if line_length <= 0:
                        p['along'] = 0.0
                        continue
                    step = line_length / float(samples)
                    cur = 0.0
                    for i in range(samples + 1):
                        try:
                            sample_pt = line_geom.interpolate(min(cur, line_length)).asPoint()
                            d = QgsPointXY(sample_pt).distance(QgsPointXY(p['geom'].asPoint()))
                            if d < best_dist:
                                best_dist = d
                                best_d = cur
                        except Exception:
                            pass
                        cur += step
                    p['along'] = best_d if best_d is not None else 0.0

            # sort points by distance along the line
            points_info.sort(key=lambda x: float(x['along']))

            # Build new memory layer
            out_crs = line_layer.crs()
            out_name = f"Segments along {line_layer.name()}"
            uri = f"LineString?crs={out_crs.authid()}"
            out_layer = QgsVectorLayer(uri, out_name, 'memory')
            pr = out_layer.dataProvider()
            pr.addAttributes([
                QgsField('from', QVariant.String),
                QgsField('to', QVariant.String),
                QgsField('length', QVariant.Double),
            ])
            out_layer.updateFields()

            # prepare distance calculator
            darea = QgsDistanceArea()
            try:
                darea.setSourceCrs(line_layer.crs(), project.transformContext())
            except Exception:
                pass

            # Create segments between consecutive points
            feats_to_add = []
            for i in range(len(points_info) - 1):
                start = points_info[i]
                end = points_info[i + 1]

                start_d = float(start['along'])
                end_d = float(end['along'])
                if end_d <= start_d:
                    continue

                seg_len = end_d - start_d
                # choose sample count proportional to segment length
                samples = max(2, min(200, int(seg_len / max(line_length / 200.0, 1e-9))))
                pts = []
                for s in range(samples + 1):
                    frac = s / float(samples)
                    dist = start_d + frac * seg_len
                    try:
                        pnt = line_geom.interpolate(min(dist, line_length)).asPoint()
                        pts.append(QgsPointXY(pnt))
                    except Exception:
                        pass

                if len(pts) < 2:
                    # fallback to straight segment between interpolated endpoints
                    try:
                        p0 = line_geom.interpolate(start_d).asPoint()
                        p1 = line_geom.interpolate(end_d).asPoint()
                        pts = [QgsPointXY(p0), QgsPointXY(p1)]
                    except Exception:
                        continue

                seg_geom = QgsGeometry.fromPolylineXY(pts)
                # measure length using QgsDistanceArea for proper units
                try:
                    length_val = float(darea.measureLength(seg_geom))
                except Exception:
                    length_val = float(seg_geom.length())

                f = QgsFeature(out_layer.fields())
                val_from = start['feature'].attribute(field_name)
                val_to = end['feature'].attribute(field_name)
                f.setGeometry(seg_geom)
                f.setAttribute('from', '' if val_from is None else str(val_from))
                f.setAttribute('to', '' if val_to is None else str(val_to))
                f.setAttribute('length', length_val)
                feats_to_add.append(f)

            if not feats_to_add:
                self.show_info('No segments', 'Unable to create any segments from the detected points')
                return

            ok, added = pr.addFeatures(feats_to_add)
            out_layer.updateExtents()
            project.addMapLayer(out_layer)

            # Success message
            self.show_info('Done', f'Created {len(feats_to_add)} segment(s) in layer "{out_name}"')

            # Record informational history (create-layer undo handled by generic handler if needed)
            try:
                self.record_to_history(
                    description=f"Created {len(feats_to_add)} segments from line",
                    undo_type='create_layer',
                    can_undo=True,
                    layers=[self.create_layer_descriptor(out_layer)]
                )
            except Exception:
                pass

        except Exception as e:
            self.show_error('Error', f'Failed to create segments: {str(e)}')


# global instance for automatic discovery
create_lines_along_line_between_points = CreateLinesAlongLineBetweenPointsAction()
