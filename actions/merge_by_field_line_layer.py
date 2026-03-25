"""
Merge Lines By Field (Layer Action)

Group line features by a chosen field value and merge their geometries into a
single (possibly multi-part) geometry per distinct field value. Original
features are removed and merged features are added to the same layer.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
)


class MergeLinesByFieldLayerAction(BaseAction):
    """Merge line features by a chosen attribute field on the entire layer."""

    def __init__(self):
        super().__init__()
        self.action_id = "merge_lines_by_field_layer"
        self.name = "Merge Lines By Field"
        self.category = "Editing"
        self.description = "Merge line features in the layer by an attribute field. Features with the same value are combined into a single geometry per value."
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

    def execute(self, context):
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error('Error', 'No layer context available')
            return

        layer = detected_features[0].layer

        # Validate geometry
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.show_error('Error', 'This action only works with line layers')
            return

        field_names = [f.name() for f in layer.fields()]
        if not field_names:
            self.show_error('Error', 'Layer has no fields to group by')
            return

        field, ok = QInputDialog.getItem(None, 'Choose Field', 'Select field to merge by:', field_names, 0, False)
        if not ok or not field:
            return

        field_idx = layer.fields().indexOf(field)

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
            # Merge geometries via iterative combine
            union_geom = None
            for g in geom_list:
                try:
                    if union_geom is None:
                        union_geom = g
                    else:
                        union_geom = union_geom.combine(g)
                except Exception:
                    continue

            if union_geom is None or union_geom.isEmpty():
                continue

            src_feat = first_feature_by_group.get(key)
            new_feat = QgsFeature()
            new_feat.setGeometry(union_geom)
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

                # Top-level features should match the last sub-operation (deleted originals)
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
merge_lines_by_field_layer_action = MergeLinesByFieldLayerAction()
