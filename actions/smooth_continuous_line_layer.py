"""
Smooth Continuous Line Layer Action

Checks that line features in the clicked layer form a continuous line (end-to-end),
merges them into a single ordered line, smooths that combined geometry as one whole
and creates a new smoothed layer. Undo is implemented (create_layer) so the created
layer can be removed by undo. This follows the patterns in ACTION_DEVELOPMENT_GUIDE.md.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsWkbTypes, QgsFeature, QgsProject, QgsVectorLayer, QgsPointXY
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressDialog, QApplication
)
from qgis.PyQt.QtCore import Qt


class SmoothContinuousLineLayerDialog(QDialog):
    def __init__(self, parent=None, default_iterations=1, default_offset=0.25, feature_count=None):
        super().__init__(parent)
        self.setWindowTitle("Smooth Continuous Line Layer")
        self.setModal(True)
        self.resize(420, 240)

        layout = QVBoxLayout()
        form = QFormLayout()

        if feature_count is not None:
            lbl = QLabel(f"Features in layer: {feature_count}")
            lbl.setStyleSheet("color: gray; font-size: 10px;")
            form.addRow("", lbl)

        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(1, 10)
        self.iter_spin.setValue(default_iterations)
        self.iter_spin.setSuffix(" passes")
        form.addRow("Smoothing Iterations:", self.iter_spin)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(0.0, 1.0)
        self.offset_spin.setDecimals(2)
        self.offset_spin.setSingleStep(0.05)
        self.offset_spin.setValue(default_offset)
        form.addRow("Smoothing Offset:", self.offset_spin)

        layout.addLayout(form)

        self.selected_only = QCheckBox("Only process selected features (if any)")
        self.selected_only.setChecked(False)
        layout.addWidget(self.selected_only)

        btn_layout = QHBoxLayout()
        self.ok = QPushButton("Smooth")
        self.cancel = QPushButton("Cancel")
        self.ok.clicked.connect(self.accept)
        self.cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.ok)
        btn_layout.addWidget(self.cancel)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def get_values(self):
        return {
            'iterations': self.iter_spin.value(),
            'offset': self.offset_spin.value(),
            'selected_only': self.selected_only.isChecked()
        }


class SmoothContinuousLineLayerAction(BaseAction):
    """Layer action: smooth features as a single continuous line."""

    def __init__(self):
        super().__init__()
        self.action_id = 'smooth_continuous_line_layer'
        self.name = 'Smooth Continuous Line Layer'
        self.category = 'Editing'
        self.description = 'If features form a single continuous line, merge, smooth as one line and create a new smoothed layer. Supports undo.'
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

        # state for undo
        self._new_layer = None
        self._created_feature_backup = None

    def get_settings_schema(self):
        return {
            'default_iterations': {'type': 'int', 'default': 1, 'label': 'Default Smoothing Iterations'},
            'default_offset': {'type': 'float', 'default': 0.25, 'label': 'Default Smoothing Offset'},
            'confirm_before_smooth': {'type': 'bool', 'default': True, 'label': 'Confirm Before Smoothing'},
            'show_success_message': {'type': 'bool', 'default': True, 'label': 'Show Success Message'}
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def get_undo_payload(self, context: dict, execute_result=None) -> dict:
        if not self._new_layer or not self._created_feature_backup:
            return None

        layer = self._new_layer
        features = [self._created_feature_backup]

        # build minimal layer definition
        fields = []
        try:
            for field in layer.fields():
                fields.append({'name': field.name(), 'type': field.type(), 'type_name': field.typeName(), 'length': field.length(), 'precision': field.precision()})
        except Exception:
            pass

        layer_def = {
            'layer_name': layer.name(),
            'crs': layer.crs().authid() if layer.crs().isValid() else '',
            'geometry_type': QgsWkbTypes.displayString(layer.wkbType()),
            'wkb_type': layer.wkbType(),
            'fields': fields,
            'features': features
        }

        return {
            'undo_type': 'create_layer',
            'layers': [self.create_layer_descriptor(layer)],
            'features': features,
            'description': f"Created smoothed continuous layer '{layer.name()}'",
            'undo_payload': {'layer_definitions': [layer_def]}
        }

    # -------- Continuity helpers --------
    def _point_key(self, pt, precision=6):
        # return tuple rounded to given precision for reliable matching
        return (round(pt.x(), precision), round(pt.y(), precision))

    def _collect_endpoints(self, features):
        # returns adjacency dict: point_key -> list of (feature_id, is_start(bool))
        adj = {}
        feat_map = {}
        for feat in features:
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            try:
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    # take first part for connectivity check (conservative)
                    if not parts:
                        continue
                    first = parts[0]
                    start = first[0]
                    end = first[-1]
                else:
                    pts = geom.asPolyline()
                    if not pts:
                        continue
                    start = pts[0]
                    end = pts[-1]
            except Exception:
                # fallback: treat as single part
                try:
                    pts = geom.asPolyline()
                    start = pts[0]
                    end = pts[-1]
                except Exception:
                    continue

            s_key = self._point_key(start)
            e_key = self._point_key(end)

            adj.setdefault(s_key, []).append((feat.id(), True))
            adj.setdefault(e_key, []).append((feat.id(), False))
            feat_map[feat.id()] = (start, end, geom)

        return adj, feat_map

    def _is_continuous(self, adj):
        # connected graph and degree conditions: either exactly two nodes degree 1 (open line)
        # or all nodes degree 2 (closed ring)
        if not adj:
            return False

        # quick degree counts
        deg1 = 0
        for k, v in adj.items():
            d = len(v)
            if d == 1:
                deg1 += 1
            elif d == 2:
                continue
            else:
                return False

        # either open chain (2 ends) or closed loop (0 ends)
        return deg1 == 2 or deg1 == 0

    def _order_features(self, adj, feat_map):
        # find start node: a node with degree 1 if open, otherwise pick any node
        start = None
        for k, v in adj.items():
            if len(v) == 1:
                start = k
                break
        if start is None:
            # closed loop - pick arbitrary node
            start = next(iter(adj))

        ordered_feats = []
        used = set()
        current_node = start

        # node -> list of (fid, is_start)
        while True:
            entries = adj.get(current_node, [])
            found = False
            for fid, is_start in entries:
                if fid in used:
                    continue
                used.add(fid)
                # append feature keeping orientation consistent
                start_pt, end_pt, geom = feat_map[fid]
                s_key = self._point_key(start_pt)
                e_key = self._point_key(end_pt)
                # determine orientation: if current_node == s_key, use as is, next node = e_key
                if current_node == s_key:
                    ordered_feats.append((fid, False))
                    current_node = e_key
                else:
                    # need to reverse feature when concatenating
                    ordered_feats.append((fid, True))
                    current_node = s_key
                found = True
                break

            if not found:
                break

        # ensure all features used
        if len(used) != len(feat_map):
            return None
        return ordered_feats

    def execute(self, context):
        try:
            iterations = int(self.get_setting('default_iterations', 1))
            offset = float(self.get_setting('default_offset', 0.25))
            confirm_before = bool(self.get_setting('confirm_before_smooth', True))
            show_success = bool(self.get_setting('show_success_message', True))
        except (ValueError, TypeError) as e:
            self.show_error('Error', f'Invalid setting values: {e}')
            return

        detected = context.get('detected_features', [])
        if not detected:
            self.show_error('Error', 'No line layer in context')
            return

        layer = detected[0].layer
        if layer is None:
            self.show_error('Error', 'No layer found in context')
            return

        try:
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
                self.show_error('Error', 'This action only works on line layers')
                return
        except Exception:
            pass

        # show dialog
        feature_count = layer.featureCount()
        dlg = SmoothContinuousLineLayerDialog(None, default_iterations=iterations, default_offset=offset, feature_count=feature_count)
        if dlg.exec_() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        iterations = vals['iterations']
        offset = vals['offset']
        selected_only = vals['selected_only']

        # build feature list
        iterator = layer.selectedFeatures() if (selected_only and layer.selectedFeatureCount() > 0) else layer.getFeatures()
        feats = [f for f in iterator]
        if not feats:
            self.show_error('Error', 'No features to process')
            return

        # collect endpoints
        adj, feat_map = self._collect_endpoints(feats)
        if not self._is_continuous(adj):
            self.show_error('Error', 'Features do not form a single continuous line (graph is disconnected or branching)')
            return

        ordered = self._order_features(adj, feat_map)
        if ordered is None:
            self.show_error('Error', 'Could not order features into a single continuous sequence')
            return

        # build combined point list
        combined = []
        for fid, reverse in ordered:
            start_pt, end_pt, geom = feat_map[fid]
            try:
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    pts = parts[0]
                else:
                    pts = geom.asPolyline()
            except Exception:
                pts = geom.asPolyline()

            if reverse:
                pts = list(reversed(pts))

            if not combined:
                combined.extend(pts)
            else:
                # avoid duplicating joining point - compare by rounded coordinates
                if self._point_key(combined[-1]) == self._point_key(pts[0]):
                    combined.extend(pts[1:])
                else:
                    combined.extend(pts)

        if not combined:
            self.show_error('Error', 'Combined geometry is empty')
            return

        merged_geom = QgsGeometry.fromPolylineXY(combined)
        if not merged_geom or merged_geom.isEmpty():
            self.show_error('Error', 'Failed to build merged geometry')
            return

        # confirm
        if confirm_before:
            if not self.confirm_action('Smooth Continuous Line Layer', f"Smooth combined line from layer '{layer.name()}' ({len(combined)} vertices)?"):
                return

        # smooth as whole
        smoothed = QgsGeometry(merged_geom).smooth(iterations, offset)
        if not smoothed or smoothed.isEmpty():
            self.show_error('Error', 'Smoothing produced invalid geometry')
            return

        # create new layer and split smoothed geometry back into segments matching original features
        new_name = f"{layer.name()} - smoothed_continuous"
        new_layer = QgsVectorLayer(f"LineString?crs={layer.crs().authid()}", new_name, 'memory')
        try:
            new_layer.dataProvider().addAttributes(layer.fields())
            new_layer.updateFields()
        except Exception:
            pass

        # Compute cumulative lengths along original merged geometry to get split positions
        orig_lengths = []
        orig_total = 0.0
        for fid, reverse in ordered:
            # feature geometry from feat_map
            s_pt, e_pt, geom = feat_map[fid]
            try:
                seg_len = geom.length()
            except Exception:
                # fallback: compute from vertices
                try:
                    pts = geom.asPolyline() if not geom.isMultipart() else geom.asMultiPolyline()[0]
                    seg_len = 0.0
                    for i in range(1, len(pts)):
                        seg_len += QgsPointXY(pts[i]).distance(QgsPointXY(pts[i-1]))
                except Exception:
                    seg_len = 0.0
            orig_lengths.append(seg_len)
            orig_total += seg_len

        if orig_total <= 0:
            self.show_error('Error', 'Original combined length is zero; cannot split')
            return

        # cumulative boundaries in original
        cum = [0.0]
        acc = 0.0
        for l in orig_lengths:
            acc += l
            cum.append(acc)

        # smoothed total length and vertex cumulative distances
        sm_total = smoothed.length()
        if sm_total <= 0:
            self.show_error('Error', 'Smoothed length is zero')
            return

        # Prepare smoothed polyline vertex list for projection-based splitting
        try:
            if smoothed.isMultipart():
                sm_poly = smoothed.asMultiPolyline()[0]
            else:
                sm_poly = smoothed.asPolyline()
        except Exception:
            sm_poly = smoothed.asPolyline() if not smoothed.isMultipart() else smoothed.asMultiPolyline()[0]

        # helper: project a point onto the smoothed polyline and return distance along polyline
        def project_point_onto_polyline_distance(poly_pts, point):
            import math

            best = None
            # precompute cumulative distances
            cumd = [0.0]
            for i in range(1, len(poly_pts)):
                cumd.append(cumd[-1] + QgsPointXY(poly_pts[i]).distance(QgsPointXY(poly_pts[i-1])))

            for i in range(len(poly_pts) - 1):
                a = QgsPointXY(poly_pts[i])
                b = QgsPointXY(poly_pts[i+1])
                dx = b.x() - a.x()
                dy = b.y() - a.y()
                seg_len2 = dx * dx + dy * dy
                if seg_len2 == 0:
                    # degenerate segment
                    t = 0.0
                    proj_x = a.x()
                    proj_y = a.y()
                else:
                    t = ((point.x() - a.x()) * dx + (point.y() - a.y()) * dy) / seg_len2
                    if t < 0:
                        t = 0.0
                    elif t > 1:
                        t = 1.0
                    proj_x = a.x() + t * dx
                    proj_y = a.y() + t * dy

                # distance from point to projection
                ddx = point.x() - proj_x
                ddy = point.y() - proj_y
                dist = math.hypot(ddx, ddy)

                # distance along polyline to projection
                proj_along = cumd[i] + (t * (QgsPointXY(b).distance(QgsPointXY(a))))

                if best is None or dist < best[0]:
                    best = (dist, proj_along)

            return best[1] if best is not None else None

        # Build a regular sampling of the smoothed geometry to preserve smoothness
        # Choose sampling density: aim for ~1 sample per 0.5 map unit, min 200, max 5000
        try:
            target_spacing = 0.5
            sample_count = max(int(sm_total / target_spacing), 200)
            sample_count = min(sample_count, 5000)
        except Exception:
            sample_count = 500

        sample_step = sm_total / float(sample_count)
        sampled = []
        cur = 0.0
        i = 0

        progress = QProgressDialog('Sampling smoothed geometry...', 'Cancel', 0, sample_count)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        while i <= sample_count:
            try:
                p = smoothed.interpolate(min(cur, sm_total)).asPoint()
                sampled.append((cur, QgsPointXY(p)))
            except Exception:
                pass

            # update progress and allow cancellation
            try:
                progress.setValue(i)
                QApplication.processEvents()
                if progress.wasCanceled():
                    progress.close()
                    self.show_info('Cancelled', 'Operation cancelled by user')
                    return
            except Exception:
                pass

            i += 1
            cur = i * sample_step

        try:
            progress.setValue(sample_count)
            progress.close()
        except Exception:
            pass

        def sample_segment_points(start_dist, end_dist):
            # gather sampled points whose distances lie within [start_dist, end_dist]
            pts = []
            eps = 1e-9
            for d, p in sampled:
                if d + eps < start_dist:
                    continue
                if d - eps > end_dist:
                    break
                pts.append(p)

            # ensure endpoints are present
            try:
                p0 = smoothed.interpolate(start_dist).asPoint()
                p0 = QgsPointXY(p0)
            except Exception:
                p0 = None
            try:
                p1 = smoothed.interpolate(end_dist).asPoint()
                p1 = QgsPointXY(p1)
            except Exception:
                p1 = None

            if p0 is not None:
                if not pts or self._point_key(pts[0]) != self._point_key(p0):
                    pts.insert(0, p0)
            if p1 is not None:
                if not pts or self._point_key(pts[-1]) != self._point_key(p1):
                    pts.append(p1)

            if len(pts) < 2:
                return None
            return pts

        # Build new geometries for each original feature (preserve attributes)
        new_geoms = []
        progress_build = QProgressDialog('Building smoothed segments...', 'Cancel', 0, len(orig_lengths))
        progress_build.setWindowModality(Qt.WindowModal)
        progress_build.setMinimumDuration(0)
        for idx in range(len(orig_lengths)):
            start_orig = cum[idx]
            end_orig = cum[idx+1]
            # map to smoothed distances by fraction
            start_sm = (start_orig / orig_total) * sm_total
            end_sm = (end_orig / orig_total) * sm_total

            if end_sm <= start_sm:
                # create minimal straight segment between interpolated points
                try:
                    p0 = smoothed.interpolate(start_sm).asPoint()
                    p1 = smoothed.interpolate(end_sm).asPoint()
                    seg_pts = [QgsPointXY(p0), QgsPointXY(p1)]
                except Exception:
                    continue
            else:
                seg_pts = sample_segment_points(start_sm, end_sm)
                if seg_pts is None:
                    # fallback to endpoints only
                    try:
                        p0 = smoothed.interpolate(start_sm).asPoint()
                        p1 = smoothed.interpolate(end_sm).asPoint()
                        seg_pts = [QgsPointXY(p0), QgsPointXY(p1)]
                    except Exception:
                        continue

            # prepare new geometry for this original feature
            new_geom = QgsGeometry.fromPolylineXY(seg_pts)
            new_geoms.append((ordered[idx][0], new_geom))

            # update progress and allow cancellation
            try:
                progress_build.setValue(idx)
                QApplication.processEvents()
                if progress_build.wasCanceled():
                    progress_build.close()
                    self.show_info('Cancelled', 'Operation cancelled by user')
                    return
            except Exception:
                pass

        try:
            progress_build.setValue(len(orig_lengths))
            progress_build.close()
        except Exception:
            pass

        # Now perform in-place geometry update on the original layer
        # Prepare old/new geometry payloads for history
        import base64
        from ..history_manager import HistoryManager

        features_payload = []
        # map fid->feature object for quick lookup
        feat_by_id = {f.id(): f for f in feats}

        for fid, new_geom in new_geoms:
            orig_feat = feat_by_id.get(fid)
            if orig_feat is None:
                # try to fetch from layer
                try:
                    request = layer.getFeatures()
                    for f in request:
                        if f.id() == fid:
                            orig_feat = f
                            break
                except Exception:
                    orig_feat = None

            # old geometry backup
            old_backup = None
            try:
                if orig_feat is not None:
                    old_backup = self.create_feature_backup(orig_feat, layer)
                else:
                    old_backup = {'fid': fid}
            except Exception:
                old_backup = {'fid': fid}

            # new geometry WKB
            try:
                wkb = new_geom.asWkb()
                wkb_b64 = base64.b64encode(wkb).decode('utf-8')
                new_geom_data = {'wkb_base64': wkb_b64}
            except Exception:
                new_geom_data = None

            feature_entry = {
                'fid': fid,
                'old_geometry': old_backup.get('geometry') if isinstance(old_backup, dict) else None,
                'new_geometry': new_geom_data
            }
            features_payload.append(feature_entry)

        # apply changes in edit session
        was_in_edit, entered = self.handle_edit_mode(layer, 'Smooth Continuous Line')
        if was_in_edit is None and entered is None:
            self.show_error('Error', 'Failed to start edit session on layer')
            return

        # progress while applying geometry updates
        progress_apply = QProgressDialog('Applying geometry updates...', 'Cancel', 0, len(new_geoms))
        progress_apply.setWindowModality(Qt.WindowModal)
        progress_apply.setMinimumDuration(0)

        try:
            for i, (fid, new_geom) in enumerate(new_geoms):
                try:
                    if not layer.changeGeometry(int(fid), new_geom):
                        raise Exception(f"changeGeometry failed for fid {fid}")
                except Exception as e:
                    # rollback and report
                    self.rollback_changes(layer)
                    progress_apply.close()
                    self.show_error('Error', f'Failed to update feature geometry: {e}')
                    return

                # update progress and allow cancellation
                try:
                    progress_apply.setValue(i)
                    QApplication.processEvents()
                    if progress_apply.wasCanceled():
                        # rollback partial changes
                        self.rollback_changes(layer)
                        progress_apply.close()
                        self.show_info('Cancelled', 'Operation cancelled by user')
                        return
                except Exception:
                    pass

            # commit
            if not self.commit_changes(layer, 'Smooth Continuous Line'):
                progress_apply.close()
                return

        except Exception as e:
            self.rollback_changes(layer)
            progress_apply.close()
            self.show_error('Error', f'Error applying geometry updates: {e}')
            return

        try:
            progress_apply.setValue(len(new_geoms))
            progress_apply.close()
        except Exception:
            pass

        # record history (update_geometry)
        try:
            self.record_to_history(
                description=f"Smoothed geometries in layer '{layer.name()}'",
                undo_type=HistoryManager.UNDO_TYPE_UPDATE_GEOMETRY,
                can_undo=True,
                layers=[self.create_layer_descriptor(layer)],
                features=features_payload
            )
        except Exception:
            pass

        if show_success:
            self.show_info('Success', f"Updated geometries for {len(new_geoms)} features in layer '{layer.name()}'")


# global instance
smooth_continuous_line_layer = SmoothContinuousLineLayerAction()
