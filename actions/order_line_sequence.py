"""
Order Line Sequence Action

Checks that line features in the clicked layer form a single continuous line (end-to-end),
orders them into a single traversal (start to end), orients individual features so their
endpoints chain correctly, and writes a sequential index field to the attribute table.
Records undo (composite) so geometry orientation and attribute writes can be reverted.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox
from qgis.PyQt.QtWidgets import QDoubleSpinBox
from qgis.PyQt.QtCore import QVariant, QMetaType
from qgis.core import QgsProject, QgsWkbTypes, QgsField, QgsGeometry, QgsPointXY


class OrderLineSequenceDialog(QDialog):
    def __init__(self, parent=None, default_tol=0.001, default_field='ord'):
        super().__init__(parent)
        self.setWindowTitle('Order Line Sequence')
        self.setModal(True)
        layout = QVBoxLayout()

        # tolerance input
        tol_layout = QHBoxLayout()
        tol_layout.addWidget(QLabel('Tolerance:'))
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setDecimals(6)
        self.tol_spin.setRange(1e-9, 1e6)
        self.tol_spin.setValue(default_tol)
        tol_layout.addWidget(self.tol_spin)
        layout.addLayout(tol_layout)

        # field name input
        field_layout = QHBoxLayout()
        field_layout.addWidget(QLabel('Order field name:'))
        self.field_edit = QLineEdit()
        self.field_edit.setText(default_field)
        field_layout.addWidget(self.field_edit)
        layout.addLayout(field_layout)

        # single action button - check then run
        btns = QHBoxLayout()
        self.action_btn = QPushButton('Check Connectivity and Run')
        btns.addWidget(self.action_btn)
        layout.addLayout(btns)

        self.setLayout(layout)

        # single-click accepts; action will run check and then proceed if OK
        self.action_btn.clicked.connect(self.accept)

    def get_values(self):
        return {'tolerance': float(self.tol_spin.value()), 'field_name': str(self.field_edit.text()).strip()}


class OrderLineSequenceAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = 'order_line_sequence'
        self.name = 'Order Line Sequence'
        self.category = 'Editing'
        self.description = 'Check connectivity, orient line features into a single traversal and write sequence numbers (undoable).'
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

    def get_settings_schema(self):
        return {
            'default_tolerance': {'type': 'float', 'default': 0.001, 'label': 'Default tolerance for connectivity'},
            'default_field_name': {'type': 'str', 'default': 'ord', 'label': 'Default order field name'}
        }

    def _point_key(self, pt, tol):
        ix = int(round(pt.x() / tol))
        iy = int(round(pt.y() / tol))
        return (ix, iy)

    def _get_endpoints(self, geom):
        if geom is None or geom.isEmpty():
            return None, None
        try:
            if geom.isMultipart():
                m = geom.asMultiPolyline()
                if not m:
                    return None, None
                line = m[0]
                if not line:
                    return None, None
                return line[0], line[-1]
            else:
                line = geom.asPolyline()
                if not line:
                    return None, None
                return line[0], line[-1]
        except Exception:
            return None, None

    def _collect_endpoints(self, layer, tol):
        nodes = {}
        adj = {}
        endpoints = {}
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            a, b = self._get_endpoints(geom)
            if a is None or b is None:
                continue
            ka = self._point_key(a, tol)
            kb = self._point_key(b, tol)
            endpoints[feat.id()] = (ka, kb)
            nodes.setdefault(ka, []).append(feat.id())
            nodes.setdefault(kb, []).append(feat.id())
            adj.setdefault(ka, set()).add(kb)
            adj.setdefault(kb, set()).add(ka)

        return nodes, adj, endpoints

    def _is_continuous(self, nodes, adj, tol):
        if not nodes:
            return False, 'No line features found'

        # BFS to check single connected component
        # Find connected components and report if more than one
        remaining = set(nodes.keys())
        components = []
        while remaining:
            start = next(iter(remaining))
            visited = set()
            stack = [start]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                for nb in adj.get(n, []):
                    if nb not in visited:
                        stack.append(nb)
            components.append(visited)
            remaining -= visited

        if len(components) > 1:
            lines = [f'Layer endpoints are NOT all connected: {len(components)} components found.']
            lines.append('Summary of components (showing up to 5):')
            for comp in components[:5]:
                # collect feature ids belonging to this component
                fids = set()
                for n in comp:
                    for fid in nodes.get(n, []) or []:
                        fids.add(fid)
                lines.append(f' - component nodes={len(comp)} feature_count={len(fids)} sample_features={list(fids)[:10]}')
            lines.append('To fix: ensure all segment endpoints connect cleanly (use snapping, merge/split, or manual edits).')
            return False, '\n'.join(lines)

        # degree check
        degrees = {n: len(adj.get(n, [])) for n in nodes.keys()}
        maxdeg = max(degrees.values()) if degrees else 0
        if maxdeg > 2:
            problematic = [(n, degrees[n], nodes.get(n, [])) for n in nodes.keys() if degrees[n] > 2]
            lines = ['Graph has branching (nodes with degree > 2). Cannot order into single chain.']
            lines.append('Problematic nodes (showing up to 20):')
            for n, deg, fids in problematic[:20]:
                approx_x = n[0] * tol
                approx_y = n[1] * tol
                lines.append(f' - coord ~ ({approx_x:.6f}, {approx_y:.6f})  degree={deg}  features={fids}')
            lines.append('Why this matters: a node with degree > 2 means three or more segments meet at the same point.')
            lines.append('How to fix: inspect the listed feature IDs in the attribute table and/or map, fix topology (split/merge/remove extra branches).')
            return False, '\n'.join(lines)

        return True, 'OK'

    def _build_traversal(self, endpoints, nodes):
        # Find start node (degree 1 if possible)
        deg1 = [n for n, d in ((n, len(nodes.get(n, []))) for n in nodes.keys()) if d == 1]
        if deg1:
            current = deg1[0]
        else:
            current = next(iter(nodes.keys()))

        used_feats = set()
        ordered = []

        while True:
            candidate = None
            cand_next = None
            for fid, (ka, kb) in endpoints.items():
                if fid in used_feats:
                    continue
                if ka == current:
                    candidate = fid
                    cand_next = kb
                    break
                if kb == current:
                    candidate = fid
                    cand_next = ka
                    break
            if candidate is None:
                break
            used_feats.add(candidate)
            ordered.append((candidate, current))
            current = cand_next

        return ordered

    def execute(self, context):
        detected = context.get('detected_features', [])
        if not detected:
            self.show_error('Error', 'No layer in context')
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

        # show dialog for tolerance and field name
        default_tol = float(self.get_setting('default_tolerance', 0.001))
        default_field = str(self.get_setting('default_field_name', 'ord'))
        dlg = OrderLineSequenceDialog(None, default_tol=default_tol, default_field=default_field)
        if dlg.exec_() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        tol = float(vals.get('tolerance', default_tol))
        field_name = vals.get('field_name') or default_field

        # Run connectivity check first; if OK proceed to orient & number automatically

        # collect endpoints
        nodes, adj, endpoints = self._collect_endpoints(layer, tol)

        ok, msg = self._is_continuous(nodes, adj, tol)
        if not ok:
            QMessageBox.information(None, 'Connectivity problem', msg)
            return

        ordered = self._build_traversal(endpoints, nodes)
        if not ordered:
            self.show_info('Result', 'No traversable features found')
            return

        # Prepare to orient geometries and write order field
        # Determine if we need to add the field
        field_names = [f.name() for f in layer.fields()]
        fields_added = []
        if field_name not in field_names:
            try:
                try:
                    meta = QMetaType.Int
                except Exception:
                    meta = QVariant.Int
                layer.dataProvider().addAttributes([QgsField(field_name, meta)])
                layer.updateFields()
                fields_added.append(field_name)
            except Exception:
                pass

        # Prepare backups for composite undo
        geom_features_payload = []
        attr_features_payload = []

        # map id -> feature for quick access
        feat_map = {f.id(): f for f in layer.getFeatures()}

        # Start edit session
        was_in_edit, entered = self.handle_edit_mode(layer, 'Orient & Number')
        if was_in_edit is None and entered is None:
            self.show_error('Error', 'Failed to start edit session on layer')
            return

        changed_geom = 0
        try:
            # First orient geometries where needed
            for fid, expected_start in ordered:
                feat = feat_map.get(fid) or layer.getFeature(fid)
                if not feat or not feat.isValid():
                    continue
                start_pt, end_pt = self._get_endpoints(feat.geometry())
                if start_pt is None:
                    continue
                start_key = self._point_key(start_pt, tol)
                if start_key != expected_start:
                    # backup old geometry
                    old_backup = self.create_feature_backup(feat, layer)
                    old_geom = old_backup.get('geometry') if isinstance(old_backup, dict) else None

                    geom = feat.geometry()
                    if geom.isMultipart():
                        mp = geom.asMultiPolyline()
                        rev_mp = [list(reversed(p)) for p in mp]
                        newgeom = QgsGeometry.fromMultiPolylineXY(rev_mp)
                    else:
                        pl = geom.asPolyline()
                        newgeom = QgsGeometry.fromPolylineXY(list(reversed(pl)))

                    # apply geometry change
                    if not layer.changeGeometry(fid, newgeom):
                        raise Exception(f'changeGeometry failed for fid {fid}')

                    # prepare new geometry data for history
                    try:
                        new_wkb = newgeom.asWkb()
                        import base64
                        new_geom_b64 = base64.b64encode(new_wkb).decode('utf-8')
                    except Exception:
                        new_geom_b64 = None

                    geom_features_payload.append({'fid': fid, 'old_geometry': old_geom, 'new_geometry': {'wkb_base64': new_geom_b64} if new_geom_b64 else None})
                    changed_geom += 1

            # Then write order field values
            # find field index
            idx = layer.fields().indexFromName(field_name)
            # clear existing values
            for f in layer.getFeatures():
                layer.changeAttributeValue(f.id(), idx, None)

            num = 1
            for fid, _ in ordered:
                feat = feat_map.get(fid) or layer.getFeature(fid)
                if not feat or not feat.isValid():
                    continue
                old_val = feat.attribute(idx)
                layer.changeAttributeValue(fid, idx, num)
                attr_features_payload.append({'fid': fid, 'old_attributes': {field_name: old_val}, 'new_attributes': {field_name: num}})
                num += 1

            # Commit changes
            if not self.commit_changes(layer, 'Orient & Number features'):
                return

        except Exception as e:
            self.rollback_changes(layer)
            self.show_error('Error', f'Failed to orient/number features: {e}')
            return

        # Record composite undo: if field added, include schema update sub-op
        try:
            from ..history_manager import get_history_manager
            hm = get_history_manager()
            layer_desc = hm.create_layer_descriptor(layer)
            description = f"Oriented and numbered features in layer '{layer.name()}' ({len(ordered)} features)"

            sub_ops = []
            if fields_added:
                added_fields_desc = []
                for fn in fields_added:
                    try:
                        qmeta = int(QMetaType.Int)
                    except Exception:
                        qmeta = QVariant.Int
                    added_fields_desc.append({'name': fn, 'qmeta_type': qmeta, 'length': None, 'precision': None})
                sub_ops.append({'undo_type': 'update_schema', 'layers': [layer_desc], 'undo_payload': {'added_fields': added_fields_desc}})

            if geom_features_payload:
                sub_ops.append({'undo_type': 'update_geometry', 'layers': [layer_desc], 'features': geom_features_payload})
            if attr_features_payload:
                sub_ops.append({'undo_type': 'update_attributes', 'layers': [layer_desc], 'features': attr_features_payload})

            if sub_ops:
                hm.record(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=description,
                    undo_type='composite',
                    can_undo=True,
                    undo_payload={'sub_operations': sub_ops},
                    layers=[layer_desc],
                    features=(geom_features_payload or attr_features_payload),
                    atomic=True,
                    meta={'field_name': field_name, 'tolerance': tol, 'oriented_count': changed_geom}
                )

        except Exception:
            pass

        self.show_info('Result', f'Oriented {len(ordered)} features, reversed {changed_geom}, field "{field_name}" written.')


# global instance
order_line_sequence = OrderLineSequenceAction()
