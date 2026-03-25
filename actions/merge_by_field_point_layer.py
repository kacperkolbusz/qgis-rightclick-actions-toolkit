"""
Merge Points By Field (Layer Action)

Group point features by a chosen field value and merge them into a single feature
per distinct value (multipart points). Original features are removed and merged
features are added to the same layer.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsPointXY,
)


class MergePointsByFieldLayerAction(BaseAction):
    """Merge point features by a chosen attribute field on the entire layer."""

    def __init__(self):
        super().__init__()
        self.action_id = "merge_points_by_field_layer"
        self.name = "Merge Points By Field"
        self.category = "Editing"
        self.description = "Merge point features in the layer by an attribute field. Features with the same value are combined into a single multipart point feature."
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    def execute(self, context):
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error('Error', 'No layer context available')
            return

        layer = detected_features[0].layer

        # Validate geometry
        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error('Error', 'This action only works with point layers')
            return

        # Let user choose a field
        field_names = [f.name() for f in layer.fields()]
        if not field_names:
            self.show_error('Error', 'Layer has no fields to group by')
            return

        field, ok = QInputDialog.getItem(None, 'Choose Field', 'Select field to merge by:', field_names, 0, False)
        if not ok or not field:
            return

        field_idx = layer.fields().indexOf(field)

        # Group features by attribute value
        groups = {}
        original_fids = []
        original_features = []
        first_feature_by_group = {}
        for feat in layer.getFeatures():
            if feat.geometry().isEmpty():
                continue
            key = feat.attribute(field_idx)
            original_fids.append(int(feat.id()))
            original_features.append(feat)
            groups.setdefault(key, []).append(feat.geometry())
            if key not in first_feature_by_group:
                first_feature_by_group[key] = feat

        if not groups:
            self.show_info('No Features', 'No valid geometries to merge')
            return

        new_features = []
        for key, geom_list in groups.items():
            pts = []
            for g in geom_list:
                try:
                    # handle single and multi point geometries
                    if g.isMultipart():
                        mpts = g.asMultiPoint()
                        pts.extend([QgsPointXY(p) for p in mpts])
                    else:
                        p = g.asPoint()
                        pts.append(QgsPointXY(p))
                except Exception:
                    continue

            if not pts:
                continue

            multi_geom = QgsGeometry.fromMultiPointXY(pts)

            # Create new feature preserving first feature attributes but set grouped field value
            src_feat = first_feature_by_group.get(key)
            new_feat = QgsFeature()
            new_feat.setGeometry(multi_geom)
            if src_feat is not None:
                attrs = src_feat.attributes()
                attrs[field_idx] = key
                new_feat.setAttributes(attrs)
            new_features.append(new_feat)

        try:
            provider = layer.dataProvider()

            # Prepare backups for originals (for undo)
            try:
                orig_backups = [self.create_feature_backup(feat, layer) for feat in original_features]
            except Exception:
                orig_backups = []

            success, added = provider.addFeatures(new_features)
            if not success:
                self.show_error('Error', 'Failed to add merged features')
                return

            # Prepare backups for newly created merged features (undo/redo)
            try:
                new_backups = [self.create_feature_backup(f, layer) for f in added]
            except Exception:
                new_backups = []

            provider.deleteFeatures(original_fids)
            layer.triggerRepaint()

            # Record composite undo: created features then deleted originals
            try:
                layer_desc = self.create_layer_descriptor(layer)
                sub_operations = [
                    {
                        'undo_type': 'create_feature',
                        'layers': [layer_desc],
                        'features': new_backups,
                        'undo_payload': {}
                    },
                    {
                        'undo_type': 'delete_feature',
                        'layers': [layer_desc],
                        'features': orig_backups,
                        'undo_payload': {}
                    }
                ]

                self.record_to_history(
                    description=f"Merged by field '{field}' on layer '{layer.name()}'",
                    undo_type='composite',
                    can_undo=True,
                    undo_payload={'sub_operations': sub_operations},
                    layers=[layer_desc],
                    features=orig_backups
                )
            except Exception:
                pass

            self.show_info('Success', f'Merged into {len(new_features)} features from {len(original_fids)} originals')
        except Exception as e:
            self.show_error('Error', f'Failed to merge features: {str(e)}')


# REQUIRED: Create global instance for automatic discovery
merge_points_by_field_layer_action = MergePointsByFieldLayerAction()
