"""
Merge Lines Layer Action

Takes all features from the clicked line layer, merges their geometries
into a single (multi-)line feature, and places that feature into a new
memory layer. Implements undo/redo per ACTION_DEVELOPMENT_GUIDE.md (records
full layer definition and feature backup for redo).
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsFeatureRequest,
    QgsWkbTypes
)


class MergeLinesLayerAction(BaseAction):
    """Create a new layer containing a single merged feature from all lines."""

    def __init__(self):
        super().__init__()

        self.action_id = "merge_lines_layer"
        self.name = "Merge Lines (Layer)"
        self.category = "Editing"
        self.description = (
            "Merge all features in the clicked line layer into one feature "
            "and place it into a new memory layer. Supports undo/redo."
        )
        self.enabled = True

        # This is a layer-level action
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        # Works on line layers
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

        # Undo state
        self._new_layer = None
        self._created_feature_backup = None

    def get_settings_schema(self):
        return {
            'new_layer_suffix': {
                'type': 'str',
                'default': ' - merged',
                'label': 'New layer name suffix',
                'description': 'Suffix appended to source layer name for the merged layer',
            }
        }

    # Undo support
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'  # We need to store layer/feature data for redo

    def get_undo_payload(self, context: dict, execute_result=None) -> dict:
        if not self._new_layer or not self._created_feature_backup:
            return None

        # Build a minimal layer definition for redo
        layer = self._new_layer

        # Collect fields
        fields = []
        for field in layer.fields():
            fields.append({
                'name': field.name(),
                'type': field.type(),
                'type_name': field.typeName(),
                'length': field.length(),
                'precision': field.precision()
            })

        # Collect features (we only created one feature)
        features = [self._created_feature_backup]

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
            'description': f"Created merged layer '{layer.name()}'",
            'undo_payload': {
                'layer_definitions': [layer_def]
            }
        }

    def execute(self, context):
        layer = context.get('layer')
        if layer is None:
            self.show_error("Error", "No layer in context")
            return

        # Validate geometry type
        try:
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
                self.show_error("Error", "This action only works on line layers")
                return
        except Exception:
            # If wkbType unavailable, allow attempt and fail later
            pass

        # Collect all polylines from layer
        multi_polylines = []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            try:
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    if parts:
                        multi_polylines.extend(parts)
                else:
                    pts = geom.asPolyline()
                    if pts:
                        multi_polylines.append(pts)
            except Exception:
                # Fallback: try asMultiPolyline or asPolyline again
                try:
                    parts = geom.asMultiPolyline()
                    if parts:
                        multi_polylines.extend(parts)
                except Exception:
                    try:
                        pts = geom.asPolyline()
                        if pts:
                            multi_polylines.append(pts)
                    except Exception:
                        continue

        if not multi_polylines:
            self.show_error("Error", "No valid line geometries found in layer")
            return

        # Build merged geometry as a multi-polyline
        merged_geometry = QgsGeometry.fromMultiPolylineXY(multi_polylines)

        # Create new memory layer
        suffix = str(self.get_setting('new_layer_suffix', ' - merged'))
        new_name = f"{layer.name()}{suffix}"
        new_layer = QgsVectorLayer(f"MultiLineString?crs={layer.crs().authid()}", new_name, "memory")

        # Copy fields (optional) to preserve schema
        try:
            new_layer.dataProvider().addAttributes(layer.fields())
            new_layer.updateFields()
        except Exception:
            # If copying fields fails, continue with no attributes
            pass

        # Create feature in new layer
        new_feat = QgsFeature(new_layer.fields())
        new_feat.setGeometry(merged_geometry)

        success = False
        created_feature = None
        try:
            success, added = new_layer.dataProvider().addFeatures([new_feat])
            if success and added:
                created_fid = added[0].id()
                # Ensure the layer is added to project before we try to read it
                QgsProject.instance().addMapLayer(new_layer)

                for f in new_layer.getFeatures(QgsFeatureRequest().setFilterFid(created_fid)):
                    created_feature = f
                    break
        except Exception as e:
            self.show_error("Error", f"Failed to create merged layer: {str(e)}")
            return

        if not success:
            self.show_error("Error", "Failed to add merged feature to new layer")
            return

        # Save state for undo/redo
        self._new_layer = new_layer
        # Use create_feature_backup from BaseAction for full backup
        self._created_feature_backup = self.create_feature_backup(created_feature, new_layer) if created_feature else {'fid': added[0].id()}

        # Build minimal layer_def for redo (the full handler may expect more; keep it compact)
        try:
            # Record to history using BaseAction helper
            self.record_to_history(
                description=f"Created merged layer '{new_layer.name()}' from {layer.name()}",
                undo_type='create_layer',
                can_undo=True,
                layers=[self.create_layer_descriptor(new_layer)],
                features=[self._created_feature_backup],
                undo_payload={'layer_definitions': []}  # History manager may build full def from layer descriptor + feature backups
            )
        except Exception:
            # Non-fatal
            pass

        self.show_info("Success", f"Merged {layer.featureCount()} features into new layer '{new_layer.name()}'")


# Required: global instance for discovery
merge_lines_layer = MergeLinesLayerAction()
