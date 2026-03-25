"""
Orient Line Direction Action

Orient all line features in the clicked layer to a user-selected cardinal
direction (north->south, south->north, east->west, west->east). Reverses
feature geometries where necessary. Records undo payload for geometry updates.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QMessageBox
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsWkbTypes, QgsGeometry, QgsProject


class OrientLineDirectionDialog(QDialog):
    def __init__(self, parent=None, default_direction='north_to_south'):
        super().__init__(parent)
        self.setWindowTitle('Orient Line Direction')
        self.setModal(True)
        layout = QVBoxLayout()

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Direction:'))
        self.combo = QComboBox()
        self.combo.addItem('North → South', 'north_to_south')
        self.combo.addItem('South → North', 'south_to_north')
        self.combo.addItem('East → West', 'east_to_west')
        self.combo.addItem('West → East', 'west_to_east')
        # set default
        idx = self.combo.findData(default_direction)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        hl.addWidget(self.combo)
        layout.addLayout(hl)

        btns = QHBoxLayout()
        ok = QPushButton('Run')
        cancel = QPushButton('Cancel')
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

        self.setLayout(layout)

    def get_values(self):
        return {'direction': self.combo.currentData()}


class OrientLineDirectionAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = 'orient_line_direction'
        self.name = 'Orient Line Direction'
        self.category = 'Editing'
        self.description = 'Orient all line features in the layer to a chosen cardinal direction.'
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

    def get_settings_schema(self):
        return {
            'default_direction': {
                'type': 'choice',
                'default': 'north_to_south',
                'label': 'Default direction',
                'options': ['north_to_south', 'south_to_north', 'east_to_west', 'west_to_east']
            }
        }

    def _get_endpoints(self, geom):
        if geom is None or geom.isEmpty():
            return None, None
        try:
            if geom.isMultipart():
                mp = geom.asMultiPolyline()
                if not mp:
                    return None, None
                line = mp[0]
                if not line:
                    return None, None
                return line[0], line[-1]
            else:
                pl = geom.asPolyline()
                if not pl:
                    return None, None
                return pl[0], pl[-1]
        except Exception:
            return None, None

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def get_undo_payload(self, context: dict, execute_result=None) -> dict:
        # execute_result will contain the payload we prepared
        return execute_result or {}

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

        default_direction = str(self.get_setting('default_direction', 'north_to_south'))
        dlg = OrientLineDirectionDialog(None, default_direction=default_direction)
        if dlg.exec_() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        direction = vals.get('direction') or default_direction

        # Map desired predicate: a function that returns True if start->end matches desired
        def needs_reverse(start, end, direction):
            try:
                sx, sy = start.x(), start.y()
                ex, ey = end.x(), end.y()
                if direction == 'north_to_south':
                    return sy <= ey  # start should be north (higher y); reverse if not
                if direction == 'south_to_north':
                    return sy >= ey
                if direction == 'east_to_west':
                    return sx <= ex
                if direction == 'west_to_east':
                    return sx >= ex
            except Exception:
                return False
            return False

        # collect features to process: use selected features if any, else all
        features_iter = None
        try:
            if layer.selectedFeatureCount() > 0:
                features_iter = layer.selectedFeatures()
            else:
                features_iter = layer.getFeatures()
        except Exception:
            features_iter = layer.getFeatures()

        # Prepare backups and changes
        changed = 0
        features_payload = []

        # Start edit session
        was_in_edit, entered = self.handle_edit_mode(layer, 'Orient Line Direction')
        if was_in_edit is None and entered is None:
            self.show_error('Error', 'Failed to start edit session on layer')
            return

        try:
            # Build a map of feature id to feature for quick access when using getFeatures()
            feat_map = {f.id(): f for f in layer.getFeatures()}

            for feat in features_iter:
                fid = feat.id()
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                start, end = self._get_endpoints(geom)
                if start is None or end is None:
                    continue

                # Check if we need to reverse
                if not needs_reverse(start, end, direction):
                    continue

                # Backup old geometry
                old_backup = self.create_feature_backup(feat, layer)

                # Create reversed geometry
                if geom.isMultipart():
                    mp = geom.asMultiPolyline()
                    rev_mp = [list(reversed(p)) for p in mp]
                    newgeom = QgsGeometry.fromMultiPolylineXY(rev_mp)
                else:
                    pl = geom.asPolyline()
                    newgeom = QgsGeometry.fromPolylineXY(list(reversed(pl)))

                # Apply change
                if not layer.changeGeometry(fid, newgeom):
                    raise Exception(f'changeGeometry failed for fid {fid}')

                # prepare new geometry for payload
                try:
                    new_wkb = newgeom.asWkb()
                    import base64
                    new_geom_b64 = base64.b64encode(new_wkb).decode('utf-8')
                except Exception:
                    new_geom_b64 = None

                features_payload.append({'fid': fid, 'old_geometry': old_backup.get('geometry'), 'new_geometry': {'wkb_base64': new_geom_b64} if new_geom_b64 else None})
                changed += 1

            # Commit
            if not self.commit_changes(layer, 'Orient Line Direction'):
                return

        except Exception as e:
            self.rollback_changes(layer)
            self.show_error('Error', f'Failed to orient lines: {e}')
            return

        # Record history
        try:
            layer_desc = self.create_layer_descriptor(layer)
            undo_payload = {
                'undo_type': 'update_geometry',
                'layers': [layer_desc],
                'features': features_payload,
                'description': f"Oriented {changed} features to {direction} in layer '{layer.name()}'"
            }

            self.record_to_history(
                description=undo_payload['description'],
                undo_type='update_geometry',
                can_undo=True,
                undo_payload=undo_payload,
                layers=[layer_desc],
                features=features_payload,
                meta={'direction': direction, 'oriented_count': changed}
            )
        except Exception:
            pass

        self.show_info('Result', f'Oriented {changed} features to {direction.replace("_"," ")}.')


# global instance
orient_line_direction = OrientLineDirectionAction()
