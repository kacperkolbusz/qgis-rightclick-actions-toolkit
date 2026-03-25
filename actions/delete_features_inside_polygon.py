"""
Delete Features Inside Polygon Action

Allows the user to choose which geometry types (points, lines, polygons)
should be searched for features inside the clicked polygon, presents a
checkboxed list of found features (with Select/Deselect All) and deletes the
checked features. Records a full backup for undo support.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsFeatureRequest,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsMessageLog,
)


class DeleteFeaturesInsidePolygonAction(BaseAction):
    """Delete features of selected geometry types that are inside a polygon."""

    def __init__(self):
        super().__init__()
        self.action_id = 'delete_features_inside_polygon'
        self.name = 'Delete Features Inside Polygon'
        self.category = 'Editing'
        self.description = 'Delete selected point/line/polygon features fully contained inside the clicked polygon.'

        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

        # Internal state populated during execute()
        self._backups = []
        self._affected_layers = []
        self._deleted_fids_by_layer = {}

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def get_undo_payload(self, context: dict, execute_result=None) -> dict:
        if not self._backups:
            return None

        layers = [self.create_layer_descriptor(layer) for layer in self._affected_layers]

        return {
            'undo_type': 'delete_feature',
            'layers': layers,
            'features': self._backups,
            'description': f"Deleted {sum(len(v) for v in self._deleted_fids_by_layer.values())} features inside polygon",
            'meta': {}
        }

    def _choose_geometry_types_dialog(self):
        dlg = QDialog()
        dlg.setWindowTitle('Choose feature types to search')
        layout = QVBoxLayout()

        layout.addWidget(QLabel('Select which geometry types to search for inside the polygon:'))
        cb_point = QCheckBox('Points')
        cb_line = QCheckBox('Lines')
        cb_polygon = QCheckBox('Polygons')
        # default all checked
        cb_point.setChecked(True)
        cb_line.setChecked(True)
        cb_polygon.setChecked(True)

        layout.addWidget(cb_point)
        layout.addWidget(cb_line)
        layout.addWidget(cb_polygon)

        btns = QHBoxLayout()
        ok = QPushButton('Continue')
        cancel = QPushButton('Cancel')
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)

        layout.addLayout(btns)

        dlg.setLayout(layout)

        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)

        result = dlg.exec_()
        if result != QDialog.Accepted:
            return None

        chosen = []
        if cb_point.isChecked():
            chosen.append('point')
        if cb_line.isChecked():
            chosen.append('line')
        if cb_polygon.isChecked():
            chosen.append('polygon')

        # include multipolygon as same category
        if 'polygon' in chosen:
            chosen.append('multipolygon')

        return chosen

    def _select_features_dialog(self, items_by_layer):
        from qgis.PyQt.QtCore import Qt

        dlg = QDialog()
        dlg.setWindowTitle('Select features to delete')
        dlg.resize(520, 450)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(
            'Check features to delete. Each layer has its own Select All / Deselect All buttons.'
        ))

        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.NoSelection)
        list_widget.setSpacing(1)

        # layer_id -> [QListWidgetItem, ...]  – only the checkable feature rows
        layer_feature_items = {}

        for layer, feats in items_by_layer.items():
            if not feats:
                continue

            # ── Layer header row ─────────────────────────────────────────
            header_item = QListWidgetItem()
            header_item.setFlags(Qt.ItemIsEnabled)
            list_widget.addItem(header_item)

            header_widget = QWidget()
            h_layout = QHBoxLayout(header_widget)
            h_layout.setContentsMargins(4, 2, 4, 2)
            h_layout.addWidget(QLabel(f"<b>{layer.name()}</b>  ({len(feats)} feature{'s' if len(feats) != 1 else ''})"))
            h_layout.addStretch()

            # Per-layer Select All / Deselect All buttons
            btn_sel   = QPushButton('Select All')
            btn_desel = QPushButton('Deselect All')
            btn_sel.setFixedHeight(22)
            btn_desel.setFixedHeight(22)
            h_layout.addWidget(btn_sel)
            h_layout.addWidget(btn_desel)

            header_item.setSizeHint(header_widget.sizeHint())
            list_widget.setItemWidget(header_item, header_widget)

            # ── Feature rows for this layer ───────────────────────────────
            feature_items = []
            for feat in feats:
                text = f"  fid={feat.id()}"
                try:
                    attrs = feat.attributes()
                    preview = [str(a) for a in attrs[:3] if a is not None]
                    if preview:
                        text += f"  ({', '.join(preview)})"
                except Exception:
                    pass

                fi = QListWidgetItem(text)
                fi.setFlags(fi.flags() | Qt.ItemIsUserCheckable)
                fi.setCheckState(Qt.Checked)
                fi.setData(Qt.UserRole, (layer.id(), feat.id()))
                list_widget.addItem(fi)
                feature_items.append(fi)

            layer_feature_items[layer.id()] = feature_items

            # Connect per-layer buttons (capture feature_items list in closure)
            def _make_layer_setter(items, state):
                def _set():
                    for item in items:
                        item.setCheckState(state)
                return _set

            btn_sel.clicked.connect(_make_layer_setter(feature_items, Qt.Checked))
            btn_desel.clicked.connect(_make_layer_setter(feature_items, Qt.Unchecked))

        layout.addWidget(list_widget)

        # ── Global Select All / Deselect All ──────────────────────────────
        global_row = QHBoxLayout()
        btn_all    = QPushButton('Select All (all layers)')
        btn_none   = QPushButton('Deselect All (all layers)')
        global_row.addWidget(btn_all)
        global_row.addWidget(btn_none)
        global_row.addStretch()
        layout.addLayout(global_row)

        def _set_global(state):
            for items in layer_feature_items.values():
                for item in items:
                    item.setCheckState(state)

        btn_all.clicked.connect(lambda: _set_global(Qt.Checked))
        btn_none.clicked.connect(lambda: _set_global(Qt.Unchecked))

        # ── OK / Cancel ───────────────────────────────────────────────────
        ok_cancel = QHBoxLayout()
        cancel = QPushButton('Cancel')
        ok     = QPushButton('Delete Selected')
        ok_cancel.addStretch()
        ok_cancel.addWidget(cancel)
        ok_cancel.addWidget(ok)
        layout.addLayout(ok_cancel)

        cancel.clicked.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)

        if dlg.exec_() != QDialog.Accepted:
            return None

        # Collect checked feature ids
        checked = {}
        for i in range(list_widget.count()):
            it = list_widget.item(i)
            if not it or not it.data(Qt.UserRole):
                continue
            if it.checkState() == Qt.Checked:
                layer_id, fid = it.data(Qt.UserRole)
                checked.setdefault(layer_id, []).append(fid)

        return checked

    def get_settings_schema(self):
        return {
            'confirm_deletion': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm before deleting',
                'description': 'Show a confirmation dialog before performing the deletion'
            }
        }

    def _find_features_inside_polygon(self, poly_geom, poly_layer, poly_feature_id, chosen_types):
        """
        Search all vector layers in the project for features of the given geometry
        types that intersect the supplied polygon geometry.

        Returns: dict  {QgsVectorLayer: [QgsFeature, ...]}
        """
        LOG_TAG = 'RightClickActions'
        results = {}

        poly_crs = poly_layer.crs() if poly_layer else None

        for lyr in QgsProject.instance().mapLayers().values():

            # ── 1. Only valid vector layers ───────────────────────────────
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue

            # ── 2. Filter by geometry type ────────────────────────────────
            # int() cast ensures safe comparison regardless of QGIS enum version
            geom_type = int(lyr.geometryType())
            #   0 = Point, 1 = Line, 2 = Polygon  (QgsWkbTypes.GeometryType)
            include = (
                (geom_type == 0 and 'point'   in chosen_types) or
                (geom_type == 1 and 'line'    in chosen_types) or
                (geom_type == 2 and 'polygon' in chosen_types)
            )
            if not include:
                continue

            # ── 3. Clone polygon geometry via WKT (most reliable method) ─
            poly_for_layer = QgsGeometry.fromWkt(poly_geom.asWkt())
            if poly_for_layer.isEmpty():
                QgsMessageLog.logMessage(
                    f"Delete Inside Polygon: polygon clone is empty for layer '{lyr.name()}'",
                    LOG_TAG, Qgis.Warning)
                continue

            # ── 4. Transform polygon to this layer's CRS if needed ────────
            if poly_crs and lyr.crs().authid() != poly_crs.authid():
                try:
                    tr = QgsCoordinateTransform(poly_crs, lyr.crs(), QgsProject.instance())
                    poly_for_layer.transform(tr)
                except Exception as e:
                    QgsMessageLog.logMessage(
                        f"Delete Inside Polygon: CRS transform failed for layer '{lyr.name()}': {e}",
                        LOG_TAG, Qgis.Warning)
                    continue

            # ── 5. Pre-filter features by bounding box ────────────────────
            bbox = poly_for_layer.boundingBox()
            req  = QgsFeatureRequest().setFilterRect(bbox)

            found      = []
            candidates = 0

            for f in lyr.getFeatures(req):
                # Skip the source polygon feature itself
                if poly_layer and lyr.id() == poly_layer.id() and f.id() == poly_feature_id:
                    continue

                g = f.geometry()
                if not g or g.isEmpty():
                    continue

                candidates += 1

                try:
                    if poly_for_layer.intersects(g):
                        found.append(f)
                except Exception as e:
                    QgsMessageLog.logMessage(
                        f"Delete Inside Polygon: intersects() error fid={f.id()} "
                        f"layer='{lyr.name()}': {e}", LOG_TAG, Qgis.Warning)

            QgsMessageLog.logMessage(
                f"Delete Inside Polygon: '{lyr.name()}' "
                f"geom={geom_type} CRS={lyr.crs().authid()} "
                f"bbox_candidates={candidates} matched={len(found)}",
                LOG_TAG)

            if found:
                results[lyr] = found

        return results

    def execute(self, context):
        feature          = context.get('feature')
        layer_of_polygon = context.get('layer')

        if feature is None:
            self.show_error('Error', 'No polygon feature found in context')
            return

        poly_geom = feature.geometry()
        if poly_geom is None or poly_geom.isEmpty():
            self.show_error('Error', 'Polygon geometry is empty')
            return

        # Ask user which geometry types to search
        chosen_types = self._choose_geometry_types_dialog()
        if not chosen_types:
            return  # cancelled

        # Expand 'polygon' to also include multipolygon (handled as geom_type==2)
        # (multipolygon geometryType() still returns 2 in QGIS)

        # ── Detect all matching features across all project vector layers ─
        items_by_layer = self._find_features_inside_polygon(
            poly_geom, layer_of_polygon, feature.id(), chosen_types
        )

        if not items_by_layer:
            self.show_info('No features found', 'No matching features found inside the polygon.')
            return

        # ask user to select which features to delete
        checked = self._select_features_dialog(items_by_layer)
        if not checked:
            return

        # prepare backups
        backups = []
        affected_layers = []
        deleted_fids_by_layer = {}

        for lyr in items_by_layer.keys():
            to_delete = checked.get(lyr.id(), [])
            if not to_delete:
                continue
            # create backups for each feature
            layer_backups = []
            for f in items_by_layer[lyr]:
                if f.id() in to_delete:
                    layer_backups.append(self.create_feature_backup(f, lyr))
            if layer_backups:
                backups.extend(layer_backups)
                affected_layers.append(lyr)
                deleted_fids_by_layer[lyr.id()] = [b['fid'] for b in layer_backups]

        if not backups:
            return

        # Confirm deletion (respect setting)
        count = sum(len(v) for v in deleted_fids_by_layer.values())
        try:
            confirm_setting = bool(self.get_setting('confirm_deletion', True))
        except Exception:
            confirm_setting = True

        if confirm_setting:
            if not self.confirm_action('Confirm deletion', f'Delete {count} features?'):
                return

        # Perform deletions per layer
        for lyr in affected_layers:
            fids = deleted_fids_by_layer.get(lyr.id(), [])
            if not fids:
                continue
            was_in_edit, entered = self.handle_edit_mode(lyr, 'delete features inside polygon')
            if was_in_edit is None:
                # failed to start editing
                # rollback previously edited layers
                for l in affected_layers:
                    try:
                        self.rollback_changes(l)
                    except Exception:
                        pass
                return

            try:
                # delete features
                for fid in fids:
                    lyr.deleteFeature(fid)
                if not self.commit_changes(lyr, 'delete features inside polygon'):
                    # commit_changes already shows error and rolled back
                    return
            except Exception as e:
                self.rollback_changes(lyr)
                self.show_error('Error', f'Failed to delete features from layer {lyr.name()}: {str(e)}')
                return

        # Save internal state for undo
        self._backups = backups
        self._affected_layers = affected_layers
        self._deleted_fids_by_layer = deleted_fids_by_layer

        # Record to history for undo
        self.record_to_history(
            description=f"Deleted {count} features inside polygon",
            undo_type='delete_feature',
            can_undo=True,
            undo_payload=self.get_undo_payload(context),
            layers=[self.create_layer_descriptor(l) for l in affected_layers],
            features=backups,
        )

        self.show_info('Deletion complete', f'Deleted {count} features.')


# Create global instance for automatic discovery
delete_features_inside_polygon_action = DeleteFeaturesInsidePolygonAction()
