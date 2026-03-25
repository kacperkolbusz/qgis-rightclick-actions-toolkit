"""
Rotate Polygon Layer Action for Right-click Utilities

Rotates all polygon features in a layer by a specified angle (degrees).
Supports rotating selected features only or the entire layer, creating a new
rotated copy layer or modifying the original in-place. Records undo payloads
with old/new geometries so operations can be undone/redone.
"""

import base64

from .base_action import BaseAction
from qgis.core import (
    QgsGeometry, QgsWkbTypes, QgsFeature, QgsVectorLayer,
    QgsProject
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QDoubleSpinBox, QCheckBox, QGroupBox
)


class RotatePolygonLayerDialog(QDialog):
    def __init__(self, parent=None, default_angle=0.0, feature_count=None, selected_count=None, ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Rotate Polygon Layer")
        self.setModal(True)
        self.resize(380, 200)

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # Layer info
        info_lines = []
        if feature_count is not None:
            info_lines.append(f"Total features: {feature_count}")
        if selected_count is not None and selected_count > 0:
            info_lines.append(f"Selected features: {selected_count}")

        if info_lines:
            info_label = QLabel("\n".join(info_lines))
            info_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("Layer info:", info_label)

        # Angle input
        self.angle_spinbox = QDoubleSpinBox()
        self.angle_spinbox.setRange(-360.0, 360.0)
        self.angle_spinbox.setValue(default_angle)
        self.angle_spinbox.setSuffix("°")
        self.angle_spinbox.setDecimals(1)
        form_layout.addRow("Rotation Angle:", self.angle_spinbox)

        angle_help = QLabel("Positive = counter-clockwise, Negative = clockwise")
        angle_help.setStyleSheet("color: gray; font-size: 10px;")
        form_layout.addRow("", angle_help)

        layout.addLayout(form_layout)

        # Selected features option
        if selected_count is not None and selected_count > 0:
            sel_group = QGroupBox("Feature Selection")
            sel_layout = QVBoxLayout()
            self.selected_only_checkbox = QCheckBox(f"Process selected features only ({selected_count} selected)")
            self.selected_only_checkbox.setChecked(True)
            sel_layout.addWidget(self.selected_only_checkbox)
            sel_group.setLayout(sel_layout)
            layout.addWidget(sel_group)
        else:
            self.selected_only_checkbox = None

        # Copy option
        if ask_copy:
            copy_group = QGroupBox("Output Options")
            copy_layout = QVBoxLayout()
            self.create_copy_checkbox = QCheckBox("Create a new layer (original layer stays unchanged)")
            self.create_copy_checkbox.setChecked(default_copy)
            copy_layout.addWidget(self.create_copy_checkbox)
            copy_group.setLayout(copy_layout)
            layout.addWidget(copy_group)
        else:
            self.create_copy_checkbox = None

        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Rotate")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.angle_spinbox.setFocus()
        self.angle_spinbox.selectAll()

    def get_values(self):
        return {
            'angle': self.angle_spinbox.value(),
            'selected_only': (self.selected_only_checkbox.isChecked() if self.selected_only_checkbox is not None else False),
            'create_copy': (self.create_copy_checkbox.isChecked() if self.create_copy_checkbox is not None else False)
        }


class RotatePolygonLayerAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = "rotate_polygon_layer"
        self.name = "Rotate Polygon Layer"
        self.category = "Editing"
        self.description = "Rotate all polygon features in a layer by a specified angle. Supports selected-only processing and creating a rotated copy layer. Records undo payloads for geometry updates."
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def get_settings_schema(self):
        return {
            'default_rotation_angle': {'type': 'float', 'default': 0.0, 'label': 'Default Rotation Angle', 'description': 'Default rotation angle in degrees', 'min': -360.0, 'max': 360.0, 'step': 1.0},
            'ask_create_copy': {'type': 'bool', 'default': True, 'label': 'Ask to Create Copy Layer', 'description': 'Ask whether to create new layer or modify original'},
            'default_copy_choice': {'type': 'choice', 'default': 'ask', 'label': 'Default Copy Choice', 'options': ['ask', 'copy', 'move']},
            'layer_storage_type': {'type': 'choice', 'default': 'temporary', 'label': 'New Layer Storage Type', 'options': ['temporary', 'permanent']},
            'confirm_before_rotate': {'type': 'bool', 'default': False, 'label': 'Confirm Before Rotating'},
            'show_success_message': {'type': 'bool', 'default': True, 'label': 'Show Success Message'},
            'auto_commit_changes': {'type': 'bool', 'default': True, 'label': 'Auto-commit Changes'},
            'handle_edit_mode_automatically': {'type': 'bool', 'default': True, 'label': 'Handle Edit Mode Automatically'},
            'rollback_on_error': {'type': 'bool', 'default': True, 'label': 'Rollback on Error'}
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    def execute(self, context):
        try:
            default_angle = float(self.get_setting('default_rotation_angle', 0.0))
            ask_create_copy = bool(self.get_setting('ask_create_copy', True))
            default_copy_choice = str(self.get_setting('default_copy_choice', 'ask'))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            confirm_before = bool(self.get_setting('confirm_before_rotate', False))
            show_success = bool(self.get_setting('show_success_message', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {e}")
            return

        detected_features = context.get('detected_features', [])
        layer = context.get('layer')
        if layer is None and detected_features:
            layer = detected_features[0].layer
        if layer is None:
            self.show_error("Error", "No polygon layer found")
            return
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return

        feature_count = layer.featureCount()
        selected_count = layer.selectedFeatureCount()

        default_copy = default_copy_choice == 'copy'
        show_copy_option = ask_create_copy

        dialog = RotatePolygonLayerDialog(None, default_angle=default_angle, feature_count=feature_count, selected_count=(selected_count if selected_count>0 else None), ask_copy=show_copy_option, default_copy=default_copy)
        from qgis.PyQt.QtWidgets import QDialog as _QDialog
        if dialog.exec_() != _QDialog.Accepted:
            return

        values = dialog.get_values()
        angle = values['angle']
        selected_only = values['selected_only']
        create_copy = values['create_copy'] if show_copy_option else (default_copy_choice == 'copy')

        # Determine features
        if selected_only and layer.selectedFeatureCount() > 0:
            features_to_process = list(layer.selectedFeatures())
        else:
            features_to_process = list(layer.getFeatures())

        if not features_to_process:
            self.show_error("Error", "No features to process in this layer")
            return

        processed = 0
        skipped = 0

        # PATH A: Create new rotated copy layer
        if create_copy:
            layer_crs = layer.crs().authid()
            new_layer = QgsVectorLayer(f"MultiPolygon?crs={layer_crs}", f"{layer.name()} (Rotated)", "memory")

            new_layer.startEditing()
            for field in layer.fields():
                new_layer.addAttribute(field)
            new_layer.updateFields()

            provider = new_layer.dataProvider()
            new_features = []

            for feature in features_to_process:
                geom = feature.geometry()
                if not geom or geom.isEmpty():
                    skipped += 1
                    continue

                centroid = geom.centroid().asPoint()
                rotated = QgsGeometry(geom)
                rotated.rotate(angle, centroid)
                if not rotated or rotated.isEmpty():
                    skipped += 1
                    continue

                new_feat = QgsFeature(new_layer.fields())
                new_feat.setGeometry(rotated)
                new_feat.setAttributes(feature.attributes())
                new_features.append(new_feat)
                processed += 1

            # Add features
            try:
                res = provider.addFeatures(new_features)
                added_ok = False
                added_layer = new_layer
                if isinstance(res, tuple) and len(res) >= 2:
                    ok, added_feats = res[0], res[1]
                    if ok:
                        added_ok = True
                elif isinstance(res, bool):
                    added_ok = res
            except Exception:
                added_ok = False

            new_layer.commitChanges()
            new_layer.updateExtents()

            # Handle saving
            if layer_storage_type == 'permanent':
                from qgis.PyQt.QtWidgets import QFileDialog
                from qgis.core import QgsVectorFileWriter
                save_path, _ = QFileDialog.getSaveFileName(None, "Save Rotated Layer", "", "GeoPackage (*.gpkg);;Shapefile (*.shp);;All Files (*)")
                if save_path:
                    error = QgsVectorFileWriter.writeAsVectorFormat(new_layer, save_path, "UTF-8", new_layer.crs())
                    if error[0] == QgsVectorFileWriter.NoError:
                        saved_layer = QgsVectorLayer(save_path, f"{layer.name()} (Rotated)", "ogr")
                        QgsProject.instance().addMapLayer(saved_layer)
                        added_layer = saved_layer
                    else:
                        self.show_error("Error", f"Failed to save layer: {error[1]}")
                        QgsProject.instance().addMapLayer(new_layer)
                        added_layer = new_layer
                else:
                    QgsProject.instance().addMapLayer(new_layer)
                    added_layer = new_layer
            else:
                QgsProject.instance().addMapLayer(new_layer)
                added_layer = new_layer

            # Record history for created layer
            try:
                self.record_to_history(
                    description=(f"Created rotated copy of layer '{layer.name()}' ({processed} features, angle {angle:.1f}°)"),
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload=None,
                    layers=[self.create_layer_descriptor(added_layer)],
                    meta={'angle': angle, 'source_layer': layer.id()},
                )
            except Exception:
                pass

        # PATH B: Modify original layer in-place
        else:
            edit_mode_entered = False
            if handle_edit_mode:
                edit_result = self.handle_edit_mode(layer, "polygon layer rotation")
                if edit_result[0] is None:
                    return
                _, edit_mode_entered = edit_result

            feature_backups = []

            try:
                for feature in features_to_process:
                    geom = feature.geometry()
                    if not geom or geom.isEmpty():
                        skipped += 1
                        continue

                    centroid = geom.centroid().asPoint()
                    rotated = QgsGeometry(geom)
                    rotated.rotate(angle, centroid)
                    if not rotated or rotated.isEmpty():
                        skipped += 1
                        continue

                    # capture old wkb
                    old_wkb = None
                    try:
                        old_wkb = base64.b64encode(geom.asWkb()).decode('utf-8')
                    except Exception:
                        pass

                    feature.setGeometry(rotated)
                    if not layer.updateFeature(feature):
                        skipped += 1
                        continue

                    # capture new wkb
                    new_wkb = None
                    try:
                        new_wkb = base64.b64encode(rotated.asWkb()).decode('utf-8')
                    except Exception:
                        pass

                    entry = {'fid': feature.id()}
                    if old_wkb:
                        entry['old_geometry'] = {'wkb_base64': old_wkb}
                    if new_wkb:
                        entry['new_geometry'] = {'wkb_base64': new_wkb}
                    feature_backups.append(entry)

                    processed += 1

                if auto_commit and handle_edit_mode:
                    if not self.commit_changes(layer, "polygon layer rotation"):
                        return

                # Record history
                try:
                    self.record_to_history(
                        description=(f"Rotated layer '{layer.name()}' ({processed} features, angle {angle:.1f}°)"),
                        undo_type='update_geometry',
                        can_undo=True,
                        undo_payload=None,
                        layers=[self.create_layer_descriptor(layer)],
                        features=feature_backups,
                        meta={'angle': angle},
                    )
                except Exception:
                    pass

            except Exception as e:
                self.show_error("Error", f"Failed to rotate layer: {e}")
                if rollback_on_error and handle_edit_mode:
                    self.rollback_changes(layer)
                return

            finally:
                if handle_edit_mode:
                    self.exit_edit_mode(layer, edit_mode_entered)

        # Success message
        if show_success and processed > 0:
            msg = (f"Layer '{layer.name()}' rotated successfully.\n\nFeatures processed: {processed}")
            if skipped > 0:
                msg += f"\nFeatures skipped: {skipped}"
            msg += f"\nAngle: {angle:.1f}°"
            if create_copy:
                msg += "\n\nOriginal layer remains unchanged."
            self.show_info("Success", msg)
        elif show_success and processed == 0:
            self.show_error("Warning", "No features were rotated.")

    def supports_undo(self):
        return True

    def get_undo_category(self):
        return 'payload'


# global instance for discovery
rotate_polygon_layer = RotatePolygonLayerAction()
