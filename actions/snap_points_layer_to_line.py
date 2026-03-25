"""
Snap Points in Layer to Line Action

Snaps all point features in the selected point layer to the closest visible line feature.
Works like the single-feature `Snap Point to Line` action but iterates over every feature
in the target layer and moves each point to the nearest line (within a configurable
maximum distance).
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer, QgsWkbTypes, QgsMapLayer
from qgis.PyQt.QtWidgets import QProgressDialog
from qgis.PyQt.QtCore import QCoreApplication


class SnapPointsLayerToLineAction(BaseAction):
    """
    Action to snap all point features in a layer to the closest visible line.
    """

    def __init__(self):
        super().__init__()

        # Metadata
        self.action_id = "snap_points_layer_to_line"
        self.name = "Snap Points in Layer to Line"
        self.category = "Editing"
        self.description = "Snap all point features in the selected layer to the closest visible line layers."
        self.enabled = True

        # Scope: layer
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        # Works on point layers
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    def get_settings_schema(self):
        return {
            'confirm_snap': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Snapping',
                'description': 'Show confirmation dialog before snapping the layer',
            },
            'confirmation_message_template': {
                'type': 'str',
                'default': "Snap all points in layer '{layer_name}' to the closest lines?",
                'label': 'Confirmation Message Template',
                'description': 'Template for confirmation message. Available variables: {layer_name}, {feature_count}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a summary message after snapping',
            },
            'success_message_template': {
                'type': 'str',
                'default': "Snapped {snapped_count}/{feature_count} points in layer '{layer_name}'. Total distance moved: {total_distance} map units",
                'label': 'Success Message Template',
                'description': 'Template for success summary. Variables: {snapped_count}, {feature_count}, {total_distance}, {layer_name}',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after snapping',
            },
            'handle_edit_mode_automatically': {
                'type': 'bool',
                'default': True,
                'label': 'Handle Edit Mode Automatically',
                'description': 'Automatically enter/exit edit mode as needed',
            },
            'rollback_on_error': {
                'type': 'bool',
                'default': True,
                'label': 'Rollback on Error',
                'description': 'Rollback changes if snap operation fails',
            },
            'include_invisible_line_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Include Invisible Line Layers',
                'description': 'Also consider line layers that are not visible in the layer tree',
            },
            'exclude_current_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Exclude Current Layer',
                'description': 'Exclude the current point layer from line layer search (prevents self-snapping)',
            },
            'line_layer_name_filter': {
                'type': 'str',
                'default': '',
                'label': 'Line Layer Name Filter',
                'description': 'Only consider line layers whose names contain this text (leave empty to consider all)',
            },
            'maximum_snap_distance': {
                'type': 'float',
                'default': 1000.0,
                'label': 'Maximum Snap Distance',
                'description': 'Maximum distance to snap (in map units). Points farther than this will not be snapped.',
                'min': 0.0,
                'max': 100000.0,
                'step': 1.0,
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in distance calculations',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_coordinate_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Coordinate Info',
                'description': 'Display coordinate information in messages',
            },
        }

    def execute(self, context):
        try:
            confirm_snap = bool(self.get_setting('confirm_snap', True))
            confirmation_template = str(self.get_setting('confirmation_message_template', "Snap all points in layer '{layer_name}' to the closest lines?"))
            show_success = bool(self.get_setting('show_success_message', True))
            success_template = str(self.get_setting('success_message_template', "Snapped {snapped_count}/{feature_count} points in layer '{layer_name}'. Total distance moved: {total_distance} map units"))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            include_invisible = bool(self.get_setting('include_invisible_line_layers', False))
            exclude_current = bool(self.get_setting('exclude_current_layer', True))
            layer_filter = str(self.get_setting('line_layer_name_filter', ''))
            max_distance = float(self.get_setting('maximum_snap_distance', 1000.0))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_coordinate_info = bool(self.get_setting('show_coordinate_info', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        # Determine target layer from context
        target_layer = context.get('layer')
        detected_features = context.get('detected_features', [])
        if not target_layer and detected_features:
            target_layer = detected_features[0].layer

        if not target_layer:
            self.show_error("Error", "No target layer found in context")
            return

        # Ensure it's a vector point layer
        if not target_layer.isValid() or target_layer.type() != QgsMapLayer.VectorLayer:
            self.show_error("Error", "Selected layer is not a valid vector layer")
            return

        if target_layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "Selected layer does not contain point geometries")
            return

        # Find candidate line layers
        line_layers = self._get_visible_line_layers(include_invisible, exclude_current, target_layer, layer_filter)
        if not line_layers:
            self.show_warning("No Line Layers", "No visible line layers found in the project.")
            return

        # Optionally confirm
        total_features = sum(1 for _ in target_layer.getFeatures())
        if confirm_snap:
            confirmation_message = self.format_message_template(
                confirmation_template,
                layer_name=target_layer.name(),
                feature_count=total_features
            )
            if not self.confirm_action("Snap Points in Layer to Line", confirmation_message):
                return

        # Handle edit mode once
        edit_result = None
        edit_mode_entered = False
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(target_layer, "layer point snapping")
            if edit_result[0] is None:
                return
            _, edit_mode_entered = edit_result

        snapped_count = 0
        total_distance = 0.0
        failed_updates = 0
        canceled = False
        features_payload = []

        try:
            # Create progress dialog for long-running operations
            progress = QProgressDialog(f"Snapping points in layer '{target_layer.name()}'...", "Cancel", 0, total_features)
            progress.setWindowTitle("Snapping Points")
            progress.setModal(True)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            for idx, feature in enumerate(target_layer.getFeatures()):
                # Handle user cancel
                if progress.wasCanceled():
                    canceled = True
                    break
                try:
                    geom = feature.geometry()
                    if not geom or geom.isEmpty():
                        continue

                    # Extract representative point
                    try:
                        pt = geom.asPoint()
                    except Exception:
                        # If multipoint, take first
                        pts = geom.asMultiPoint()
                        if not pts:
                            continue
                        pt = pts[0]

                    # Find closest line for this point
                    closest_result = self._find_closest_line(pt, line_layers, max_distance)
                    if not closest_result:
                        continue

                    closest_line_feature, closest_line_layer, closest_point_on_line, distance = closest_result

                    # Create new geometry and update
                    original_geom = QgsGeometry(geom)
                    new_geometry = QgsGeometry.fromPointXY(closest_point_on_line)
                    feature.setGeometry(new_geometry)
                    if not target_layer.updateFeature(feature):
                        failed_updates += 1
                        # update progress and continue
                        progress.setValue(idx + 1)
                        QCoreApplication.processEvents()
                        continue

                    snapped_count += 1
                    total_distance += distance

                    # Collect geometry change for history
                    try:
                        import base64
                        old_wkb = original_geom.asWkb()
                        new_wkb = new_geometry.asWkb()
                        features_payload.append({
                            'fid': int(feature.id()),
                            'old_geometry': {'wkb_base64': base64.b64encode(old_wkb).decode('utf-8')},
                            'new_geometry': {'wkb_base64': base64.b64encode(new_wkb).decode('utf-8')},
                        })
                    except Exception:
                        pass

                    # Update progress
                    progress.setValue(idx + 1)
                    QCoreApplication.processEvents()
                except Exception:
                    failed_updates += 1
                    continue

            # Close progress dialog
            try:
                progress.close()
            except Exception:
                pass

            # Commit if desired
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(target_layer, "layer point snapping"):
                    return

            # Record undo history for all snapped features
            if features_payload:
                try:
                    from ..history_manager import HistoryManager
                    self.record_to_history(
                        description=f"Snapped {snapped_count} point(s) in layer '{target_layer.name()}' to nearest lines",
                        undo_type=HistoryManager.UNDO_TYPE_UPDATE_GEOMETRY,
                        can_undo=True,
                        undo_payload=None,
                        layers=[self.create_layer_descriptor(target_layer)],
                        features=features_payload,
                        meta={'from_crs': target_layer.crs().authid() if target_layer.crs().isValid() else '',
                              'to_crs': target_layer.crs().authid() if target_layer.crs().isValid() else ''}
                    )
                except Exception:
                    pass

            # Show summary
            if show_success:
                formatted_total = f"{total_distance:.{decimal_places}f}"
                success_message = self.format_message_template(
                    success_template,
                    snapped_count=snapped_count,
                    feature_count=total_features,
                    total_distance=formatted_total,
                    layer_name=target_layer.name()
                )
                if show_coordinate_info:
                    success_message += f"\n\nSnapped features: {snapped_count}. Failed updates: {failed_updates}."

                if canceled:
                    success_message = f"Operation canceled by user. {success_message}"

                self.show_info("Snap Points Summary", success_message)

        except Exception as e:
            self.show_error("Error", f"Failed to snap points in layer: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(target_layer)

        finally:
            if handle_edit_mode:
                self.exit_edit_mode(target_layer, edit_mode_entered)

    def _get_visible_line_layers(self, include_invisible, exclude_current, current_layer, layer_filter):
        project = QgsProject.instance()
        layer_tree_root = project.layerTreeRoot()
        all_layers = project.mapLayers().values()

        line_layers = []

        for layer in all_layers:
            if not layer.isValid():
                continue

            if layer.type() != QgsMapLayer.VectorLayer:
                continue

            if layer.geometryType() != QgsWkbTypes.LineGeometry:
                continue

            if layer_filter and layer_filter.lower() not in layer.name().lower():
                continue

            if exclude_current and current_layer is not None and layer.id() == current_layer.id():
                continue

            if not include_invisible:
                layer_tree_layer = layer_tree_root.findLayer(layer.id())
                if not layer_tree_layer or not layer_tree_layer.isVisible():
                    continue

            line_layers.append(layer)

        return line_layers

    def _find_closest_line(self, point, line_layers, max_distance):
        closest_feature = None
        closest_layer = None
        closest_point = None
        closest_distance = float('inf')

        point_geom = QgsGeometry.fromPointXY(point)

        for layer in line_layers:
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if not geometry or geometry.isEmpty():
                    continue

                distance = geometry.distance(point_geom)

                if distance > max_distance:
                    continue

                if distance < closest_distance:
                    nearest_geom = geometry.nearestPoint(point_geom)
                    if nearest_geom.isEmpty():
                        continue
                    closest_distance = distance
                    closest_feature = feature
                    closest_layer = layer
                    closest_point = nearest_geom.asPoint()

        if closest_feature is None:
            return None

        return (closest_feature, closest_layer, closest_point, closest_distance)

    def format_message_template(self, template, **kwargs):
        """
        Format a message template with provided variables.
        """
        try:
            if 'distance_moved' in kwargs and isinstance(kwargs['distance_moved'], (int, float)):
                decimal_places = int(self.get_setting('decimal_places', 2))
                kwargs['distance_moved'] = f"{kwargs['distance_moved']:.{decimal_places}f}"

            if 'total_distance' in kwargs and isinstance(kwargs['total_distance'], (int, float)):
                decimal_places = int(self.get_setting('decimal_places', 2))
                kwargs['total_distance'] = f"{kwargs['total_distance']:.{decimal_places}f}"

            return template.format(**kwargs)
        except Exception:
            return template


# REQUIRED: Create global instance for automatic discovery
snap_points_layer_to_line_action = SnapPointsLayerToLineAction()
