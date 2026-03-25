"""
Smooth Line Layer Action for Right-click Utilities and Shortcuts Hub

Applies smoothing (Chaikin by default) to all line features in the clicked
line layer. Supports creating a new smoothed layer or updating the original
layer in-place. Implements undo/redo according to ACTION_DEVELOPMENT_GUIDE.md.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsWkbTypes, QgsFeature, QgsProject
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox, QRadioButton
)


class SmoothLineLayerDialog(QDialog):
    """Dialog for smoothing parameters for layer-wide smoothing."""

    def __init__(self, parent=None, default_iterations=1, default_offset=0.25,
                 feature_count=None, default_choice='modify'):
        super().__init__(parent)
        self.setWindowTitle("Smooth Line Layer")
        self.setModal(True)
        self.resize(420, 300)

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        if feature_count is not None:
            count_label = QLabel(f"Features in layer: {feature_count}")
            count_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", count_label)

        self.iterations_spinbox = QSpinBox()
        self.iterations_spinbox.setRange(1, 10)
        self.iterations_spinbox.setValue(default_iterations)
        self.iterations_spinbox.setSuffix(" passes")
        form_layout.addRow("Smoothing Iterations:", self.iterations_spinbox)

        self.offset_spinbox = QDoubleSpinBox()
        self.offset_spinbox.setRange(0.0, 1.0)
        self.offset_spinbox.setDecimals(2)
        self.offset_spinbox.setSingleStep(0.05)
        self.offset_spinbox.setValue(default_offset)
        form_layout.addRow("Smoothing Offset:", self.offset_spinbox)

        layout.addLayout(form_layout)

        choice_group = QGroupBox("Operation")
        choice_layout = QVBoxLayout()
        self.modify_radio = QRadioButton("Modify original layer (in-place)")
        self.copy_radio = QRadioButton("Create new smoothed layer (copy)")
        if default_choice == 'copy':
            self.copy_radio.setChecked(True)
        else:
            self.modify_radio.setChecked(True)

        choice_layout.addWidget(self.modify_radio)
        choice_layout.addWidget(self.copy_radio)
        choice_group.setLayout(choice_layout)
        layout.addWidget(choice_group)

        # Option: process only selected features
        self.selected_only_checkbox = QCheckBox("Only process selected features (if any)")
        self.selected_only_checkbox.setChecked(False)
        layout.addWidget(self.selected_only_checkbox)

        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Smooth")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.iterations_spinbox.setFocus()
        self.iterations_spinbox.selectAll()

    def get_values(self):
        return {
            'iterations': self.iterations_spinbox.value(),
            'offset': self.offset_spinbox.value(),
            'create_new_layer': self.copy_radio.isChecked(),
            'selected_only': self.selected_only_checkbox.isChecked()
        }


class SmoothLineLayerAction(BaseAction):
    """Smooth all lines in a layer (layer-level action)."""

    def __init__(self):
        super().__init__()

        self.action_id = "smooth_line_layer"
        self.name = "Smooth Line Layer"
        self.category = "Editing"
        self.description = "Smooth all line features in the clicked line layer. Supports creating a new smoothed layer or modifying the original. Undo supported."
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

        # Undo state
        self._target_layer = None
        self._features_backup = None  # list of feature backups for in-place update
        self._new_layer = None
        self._created_features_backups = None

    def get_settings_schema(self):
        return {
            'default_iterations': {
                'type': 'int', 'default': 1, 'label': 'Default Smoothing Iterations',
                'description': 'Default number of smoothing passes (1-10 recommended)', 'min': 1, 'max': 10
            },
            'default_offset': {
                'type': 'float', 'default': 0.25, 'label': 'Default Smoothing Offset',
                'description': 'Default smoothing offset value (0.0-1.0)', 'min': 0.0, 'max': 1.0
            },
            'default_create_choice': {
                'type': 'choice', 'default': 'modify', 'label': 'Default Operation',
                'description': 'Default: modify original or create new layer', 'options': ['modify', 'copy']
            },
            'layer_storage_type': {
                'type': 'choice', 'default': 'temporary', 'label': 'Layer Storage Type',
                'description': 'Choose temporary (memory) or permanent when creating a new layer',
                'options': ['temporary', 'permanent']
            },
            'confirm_before_smooth': {
                'type': 'bool', 'default': True, 'label': 'Confirm Before Smoothing',
                'description': 'Show confirmation dialog before smoothing the whole layer'
            },
            'show_success_message': {
                'type': 'bool', 'default': True, 'label': 'Show Success Message',
                'description': 'Display a message when smoothing completes'
            },
            'auto_commit_changes': {
                'type': 'bool', 'default': True, 'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after modifying the layer'
            },
            'handle_edit_mode_automatically': {
                'type': 'bool', 'default': True, 'label': 'Handle Edit Mode Automatically',
                'description': 'Automatically enter/exit edit mode as needed'
            },
            'rollback_on_error': {
                'type': 'bool', 'default': True, 'label': 'Rollback on Error',
                'description': 'Rollback changes if an error occurs during processing'
            }
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    def smooth_geometry_chaikin(self, geometry, iterations, offset):
        sm = QgsGeometry(geometry)
        return sm.smooth(iterations, offset)

    # Undo support
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'

    def get_undo_payload(self, context: dict, execute_result=None) -> dict:
        # If we created a new layer, return create_layer payload
        if self._new_layer and self._created_features_backups:
            layer = self._new_layer
            features = self._created_features_backups

            # Build minimal layer definition for redo
            fields = []
            try:
                for field in layer.fields():
                    fields.append({
                        'name': field.name(),
                        'type': field.type(),
                        'type_name': field.typeName(),
                        'length': field.length(),
                        'precision': field.precision()
                    })
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
                'description': f"Created smoothed layer '{layer.name()}'",
                'undo_payload': {'layer_definitions': [layer_def]}
            }

        # If we modified original layer, return update_geometry payload
        if self._target_layer and self._features_backup:
            return {
                'undo_type': 'update_geometry',
                'layers': [self.create_layer_descriptor(self._target_layer)],
                'features': self._features_backup,
                'description': f"Smoothed {len(self._features_backup)} feature(s) in {self._target_layer.name()}"
            }

        return None

    def execute(self, context):
        try:
            default_iterations = int(self.get_setting('default_iterations', 1))
            default_offset = float(self.get_setting('default_offset', 0.25))
            default_choice = str(self.get_setting('default_create_choice', 'modify'))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            confirm_before_smooth = bool(self.get_setting('confirm_before_smooth', True))
            show_success = bool(self.get_setting('show_success_message', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No line features found in this context")
            return

        layer = detected_features[0].layer
        if layer is None:
            self.show_error("Error", "No layer found in context")
            return

        # Validate geometry type
        try:
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
                self.show_error("Error", "This action only works on line layers")
                return
        except Exception:
            pass

        # Determine features to process (selected only or all)
        feature_count = layer.featureCount()

        dialog = SmoothLineLayerDialog(
            None,
            default_iterations=default_iterations,
            default_offset=default_offset,
            feature_count=feature_count,
            default_choice=default_choice
        )

        if dialog.exec_() != QDialog.Accepted:
            return

        values = dialog.get_values()
        iterations = values['iterations']
        offset = values['offset']
        create_new_layer = values['create_new_layer']
        selected_only = values['selected_only']

        if confirm_before_smooth:
            if create_new_layer:
                msg = f"Create a new smoothed layer from layer '{layer.name()}' ({feature_count} features)?"
            else:
                msg = f"Smooth all line features in layer '{layer.name()}' ({feature_count} features) in-place?"
            if not self.confirm_action("Smooth Line Layer", msg):
                return

        # Handle edit mode for in-place modifications
        edit_mode_entered = False
        if not create_new_layer and handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "smoothing layer")
            if edit_result[0] is None:
                return
            was_in_edit_mode, edit_mode_entered = edit_result

        try:
            if create_new_layer:
                # Create new memory layer with same geometry and CRS
                name_suffix = ' - smoothed'
                new_name = f"{layer.name()}{name_suffix}"
                new_layer = QgsVectorLayer(f"MultiLineString?crs={layer.crs().authid()}", new_name, "memory")
                try:
                    new_layer.dataProvider().addAttributes(layer.fields())
                    new_layer.updateFields()
                except Exception:
                    pass

                created = []
                feats_to_add = []
                from qgis.core import QgsFeatureRequest

                # iterate selected or all
                iterator = layer.selectedFeatures() if (selected_only and layer.selectedFeatureCount() > 0) else layer.getFeatures()
                for feat in iterator:
                    geom = feat.geometry()
                    if not geom or geom.isEmpty():
                        continue
                    smoothed = self.smooth_geometry_chaikin(geom, iterations, offset)
                    if not smoothed or smoothed.isEmpty():
                        continue
                    new_feat = QgsFeature(new_layer.fields())
                    new_feat.setGeometry(smoothed)
                    # copy attributes if available
                    try:
                        new_feat.setAttributes(feat.attributes())
                    except Exception:
                        pass
                    feats_to_add.append(new_feat)

                success = False
                added = None
                try:
                    success, added = new_layer.dataProvider().addFeatures(feats_to_add)
                except Exception:
                    success = False

                if not success:
                    self.show_error("Error", "Failed to create smoothed layer or add features")
                    return

                # Add layer to project
                QgsProject.instance().addMapLayer(new_layer)

                # Build backups for created features
                created_backups = []
                try:
                    created_fid = None
                    for f in added:
                        fid = f.id()
                        created_backups.append(self.create_feature_backup(f, new_layer))

                except Exception:
                    pass

                self._new_layer = new_layer
                self._created_features_backups = created_backups if created_backups else [{'fid': f.id()} for f in added] if added else None

                # Record history (create_layer)
                try:
                    from ..history_manager import HistoryManager
                    self.record_to_history(
                        description=f"Created smoothed layer '{new_layer.name()}' from {layer.name()}",
                        undo_type=HistoryManager.UNDO_TYPE_CREATE_LAYER,
                        can_undo=True,
                        layers=[self.create_layer_descriptor(new_layer)],
                        features=self._created_features_backups
                    )
                except Exception:
                    pass

                if show_success:
                    self.show_info("Success", f"Smoothed layer '{new_layer.name()}' created with {len(feats_to_add)} features")

            else:
                # Modify original layer in-place
                features_payload = []
                # We'll store full backups for undo
                backups = []

                iterator = layer.selectedFeatures() if (selected_only and layer.selectedFeatureCount() > 0) else layer.getFeatures()
                for feat in iterator:
                    geom = feat.geometry()
                    if not geom or geom.isEmpty():
                        continue

                    # backup original geometry
                    try:
                        import base64
                        old_wkb = QgsGeometry(geom).asWkb()
                        old_geom = {'wkb_base64': base64.b64encode(old_wkb).decode('utf-8')}
                    except Exception:
                        old_geom = None

                    smoothed = self.smooth_geometry_chaikin(geom, iterations, offset)
                    if not smoothed or smoothed.isEmpty():
                        continue

                    # update feature
                    feat.setGeometry(smoothed)
                    if not layer.updateFeature(feat):
                        # try to continue
                        continue

                    # record new geometry
                    try:
                        import base64
                        new_wkb = smoothed.asWkb()
                        new_geom = {'wkb_base64': base64.b64encode(new_wkb).decode('utf-8')}
                    except Exception:
                        new_geom = None

                    features_payload.append({
                        'fid': int(feat.id()),
                        'old_geometry': old_geom,
                        'new_geometry': new_geom
                    })

                    backups.append(self.create_feature_backup(feat, layer))

                # Save undo state
                self._target_layer = layer
                self._features_backup = features_payload

                # Commit changes if enabled
                if auto_commit and handle_edit_mode:
                    if not self.commit_changes(layer, "smooth line layer"):
                        return

                # Record history
                try:
                    from ..history_manager import HistoryManager
                    if features_payload:
                        self.record_to_history(
                            description=f"Smoothed {len(features_payload)} feature(s) in layer {layer.name()}",
                            undo_type=HistoryManager.UNDO_TYPE_UPDATE_GEOMETRY,
                            can_undo=True,
                            layers=[self.create_layer_descriptor(layer)],
                            features=features_payload
                        )
                except Exception:
                    pass

                if show_success:
                    self.show_info("Success", f"Smoothed {len(features_payload)} feature(s) in layer '{layer.name()}'")

        except Exception as e:
            self.show_error("Error", f"Failed to smooth line layer: {str(e)}")
            if rollback_on_error and not create_new_layer and handle_edit_mode:
                try:
                    self.rollback_changes(layer)
                except Exception:
                    pass

        finally:
            if not create_new_layer and handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)


# Global instance for discovery
smooth_line_layer = SmoothLineLayerAction()
