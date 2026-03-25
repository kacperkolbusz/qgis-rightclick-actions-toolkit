"""
Smooth Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Smooths the borders/edges of all polygon features in the selected layer using
configurable smoothing algorithms. Uses Chaikin's corner cutting algorithm by
default. Supports processing only selected features and creating a smoothed
copy layer while keeping the original unchanged.
"""

import base64

from .base_action import BaseAction
from qgis.core import (
    QgsGeometry, QgsWkbTypes, QgsFeature, QgsVectorLayer,
    QgsProject, QgsFeatureRequest, QgsField
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox
)
from qgis.PyQt.QtCore import QVariant, QMetaType


class SmoothPolygonLayerDialog(QDialog):
    """Dialog for configuring layer-level polygon smoothing."""

    def __init__(self, parent=None, default_iterations=1, default_offset=0.25,
                 feature_count=None, selected_count=None,
                 ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Smooth Polygon Layer")
        self.setModal(True)
        self.resize(420, 340)

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

        # Iterations input
        self.iterations_spinbox = QSpinBox()
        self.iterations_spinbox.setRange(1, 10)
        self.iterations_spinbox.setValue(default_iterations)
        self.iterations_spinbox.setSuffix(" passes")
        form_layout.addRow("Smoothing Iterations:", self.iterations_spinbox)

        iterations_help = QLabel("More iterations = smoother borders (1-10 recommended)")
        iterations_help.setStyleSheet("color: gray; font-size: 10px;")
        iterations_help.setWordWrap(True)
        form_layout.addRow("", iterations_help)

        # Offset input
        self.offset_spinbox = QDoubleSpinBox()
        self.offset_spinbox.setRange(0.0, 1.0)
        self.offset_spinbox.setValue(default_offset)
        self.offset_spinbox.setDecimals(2)
        self.offset_spinbox.setSingleStep(0.05)
        form_layout.addRow("Smoothing Offset:", self.offset_spinbox)

        offset_help = QLabel("Offset controls smoothing strength (0.0-1.0, default: 0.25)")
        offset_help.setStyleSheet("color: gray; font-size: 10px;")
        offset_help.setWordWrap(True)
        form_layout.addRow("", offset_help)

        layout.addLayout(form_layout)

        # Selected features option (only shown when there are selected features)
        if selected_count is not None and selected_count > 0:
            selection_group = QGroupBox("Feature Selection")
            selection_layout = QVBoxLayout()

            self.selected_only_checkbox = QCheckBox(
                f"Process selected features only ({selected_count} selected)"
            )
            self.selected_only_checkbox.setChecked(True)
            selection_layout.addWidget(self.selected_only_checkbox)

            selection_group.setLayout(selection_layout)
            layout.addWidget(selection_group)
        else:
            self.selected_only_checkbox = None

        # Copy option group
        if ask_copy:
            copy_group = QGroupBox("Output Options")
            copy_layout = QVBoxLayout()

            self.create_copy_checkbox = QCheckBox(
                "Create a new layer (original layer stays unchanged)"
            )
            self.create_copy_checkbox.setChecked(default_copy)
            copy_layout.addWidget(self.create_copy_checkbox)

            copy_group.setLayout(copy_layout)
            layout.addWidget(copy_group)
        else:
            self.create_copy_checkbox = None

        # Buttons
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
        """Get the dialog input values."""
        return {
            'iterations': self.iterations_spinbox.value(),
            'offset': self.offset_spinbox.value(),
            'selected_only': (
                self.selected_only_checkbox.isChecked()
                if self.selected_only_checkbox is not None
                else False
            ),
            'create_copy': (
                self.create_copy_checkbox.isChecked()
                if self.create_copy_checkbox is not None
                else False
            ),
        }


class SmoothPolygonLayerAction(BaseAction):
    """
    Action to smooth the borders/edges of all polygon features in a layer.

    Smooths every polygon feature in the layer using Chaikin's corner cutting
    algorithm (via QGIS smooth() method). Configurable iterations and offset
    parameters control smoothing strength. Supports processing only selected
    features and creating a smoothed copy layer while keeping the original
    layer unchanged.
    """

    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()

        # Required properties
        self.action_id = "smooth_polygon_layer"
        self.name = "Smooth Polygon Layer"
        self.category = "Editing"
        self.description = (
            "Smooth the borders/edges of all polygon features in the layer using "
            "Chaikin's corner cutting algorithm. Configurable iterations and offset "
            "control smoothing strength. Supports processing only selected features "
            "and creating a smoothed copy layer."
        )
        self.enabled = True

        # Action scoping - works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        # Feature type support - works with all polygon types
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # SMOOTHING SETTINGS
            'default_iterations': {
                'type': 'int',
                'default': 1,
                'label': 'Default Smoothing Iterations',
                'description': 'Default number of smoothing passes (1-10 recommended)',
                'min': 1,
                'max': 10,
                'step': 1,
            },
            'default_offset': {
                'type': 'float',
                'default': 0.25,
                'label': 'Default Smoothing Offset',
                'description': 'Default smoothing offset value (0.0-1.0, controls smoothing strength)',
                'min': 0.0,
                'max': 1.0,
                'step': 0.05,
            },

            # COPY / OUTPUT SETTINGS
            'ask_create_copy': {
                'type': 'bool',
                'default': True,
                'label': 'Ask to Create Copy Layer',
                'description': (
                    'Ask user each time whether to create a new layer '
                    'instead of modifying the original layer'
                ),
            },
            'default_copy_choice': {
                'type': 'choice',
                'default': 'ask',
                'label': 'Default Copy Choice',
                'description': (
                    '"ask" prompts the user each time, '
                    '"copy" always creates a new layer, '
                    '"move" always modifies the original layer.'
                ),
                'options': ['ask', 'copy', 'move'],
            },
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'New Layer Storage Type',
                'description': (
                    'When creating a copy layer, store it as temporary (in memory) '
                    'or permanent (saved to disk).'
                ),
                'options': ['temporary', 'permanent'],
            },

            # BEHAVIOR SETTINGS
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a summary message after completing smoothing',
            },
            'show_layer_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Information',
                'description': 'Display feature count in the dialog',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after smoothing (recommended)',
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
                'description': 'Rollback all changes if any smoothing operation fails',
            },
        }

    def get_setting(self, setting_name, default_value=None):
        """Get a setting value for this action."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    @staticmethod
    def _smooth_geometry(geometry, iterations, offset):
        """Apply Chaikin smoothing to a geometry."""
        return QgsGeometry(geometry).smooth(iterations, offset)

    def execute(self, context):
        """Execute the smooth polygon layer action."""
        # --- Read settings ---
        try:
            default_iterations = int(self.get_setting('default_iterations', 1))
            default_offset = float(self.get_setting('default_offset', 0.25))
            ask_create_copy = bool(self.get_setting('ask_create_copy', True))
            default_copy_choice = str(self.get_setting('default_copy_choice', 'ask'))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            show_success = bool(self.get_setting('show_success_message', True))
            show_layer_info = bool(self.get_setting('show_layer_info', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        # --- Resolve layer from context ---
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

        # --- Gather layer stats for dialog ---
        feature_count = layer.featureCount() if show_layer_info else None
        selected_count = layer.selectedFeatureCount() if show_layer_info else 0

        # --- Show unified dialog ---
        default_copy = default_copy_choice == 'copy'
        show_copy_option = ask_create_copy

        dialog = SmoothPolygonLayerDialog(
            None,
            default_iterations=default_iterations,
            default_offset=default_offset,
            feature_count=feature_count,
            selected_count=selected_count if selected_count > 0 else None,
            ask_copy=show_copy_option,
            default_copy=default_copy,
        )

        from qgis.PyQt.QtWidgets import QDialog as _QDialog
        if dialog.exec_() != _QDialog.Accepted:
            return  # User cancelled

        values = dialog.get_values()
        iterations = values['iterations']
        offset = values['offset']
        selected_only = values['selected_only']
        create_copy = values['create_copy'] if show_copy_option else (default_copy_choice == 'copy')

        # --- Determine features to process ---
        if selected_only and layer.selectedFeatureCount() > 0:
            features_to_process = list(layer.selectedFeatures())
        else:
            features_to_process = list(layer.getFeatures())

        if not features_to_process:
            self.show_error("Error", "No features to process in this layer")
            return

        processed = 0
        skipped = 0

        # =====================================================================
        # PATH A: Create a new (copy) layer
        # =====================================================================
        if create_copy:
            layer_crs = layer.crs().authid()

            new_layer = QgsVectorLayer(
                f"MultiPolygon?crs={layer_crs}",
                f"{layer.name()} (Smoothed)",
                "memory"
            )

            # Copy fields
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

                smoothed_geom = self._smooth_geometry(geom, iterations, offset)

                if not smoothed_geom or smoothed_geom.isEmpty():
                    skipped += 1
                    continue

                processed += 1

                new_feat = QgsFeature(new_layer.fields())
                new_feat.setGeometry(smoothed_geom)
                new_feat.setAttributes(feature.attributes())
                new_features.append(new_feat)

            provider.addFeatures(new_features)
            new_layer.commitChanges()
            new_layer.updateExtents()

            # Handle permanent storage
            if layer_storage_type == 'permanent':
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Smoothed Layer",
                    "",
                    "GeoPackage (*.gpkg);;Shapefile (*.shp);;All Files (*)"
                )
                if save_path:
                    from qgis.core import QgsVectorFileWriter
                    error = QgsVectorFileWriter.writeAsVectorFormat(
                        new_layer,
                        save_path,
                        "UTF-8",
                        new_layer.crs(),
                    )
                    if error[0] == QgsVectorFileWriter.NoError:
                        saved_layer = QgsVectorLayer(save_path, f"{layer.name()} (Smoothed)", "ogr")
                        QgsProject.instance().addMapLayer(saved_layer)
                        added_layer = saved_layer
                    else:
                        self.show_error("Error", f"Failed to save layer: {error[1]}")
                        QgsProject.instance().addMapLayer(new_layer)
                        added_layer = new_layer
                else:
                    # User cancelled save → fall back to temporary
                    QgsProject.instance().addMapLayer(new_layer)
                    added_layer = new_layer
            else:
                QgsProject.instance().addMapLayer(new_layer)
                added_layer = new_layer

            # Record history
            try:
                self.record_to_history(
                    description=(
                        f"Created smoothed copy of layer '{layer.name()}' "
                        f"({processed} features, {iterations} iterations, offset {offset:.2f})"
                    ),
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload=None,
                    layers=[self.create_layer_descriptor(added_layer)],
                    meta={
                        'iterations': iterations,
                        'offset': offset,
                        'source_layer': layer.id(),
                    },
                )
            except Exception:
                pass

        # =====================================================================
        # PATH B: Modify the original layer in place
        # =====================================================================
        else:
            edit_mode_entered = False

            if handle_edit_mode:
                edit_result = self.handle_edit_mode(layer, "polygon layer smoothing")
                if edit_result[0] is None:
                    return
                _, edit_mode_entered = edit_result

            # Stores per-feature {fid, old_geometry, new_geometry} for undo
            feature_backups = []

            try:
                for feature in features_to_process:
                    geom = feature.geometry()
                    if not geom or geom.isEmpty():
                        skipped += 1
                        continue

                    smoothed_geom = self._smooth_geometry(geom, iterations, offset)

                    if not smoothed_geom or smoothed_geom.isEmpty():
                        skipped += 1
                        continue

                    # Capture old geometry WKB before modifying
                    old_wkb = None
                    try:
                        old_wkb = base64.b64encode(geom.asWkb()).decode('utf-8')
                    except Exception:
                        pass

                    feature.setGeometry(smoothed_geom)
                    if not layer.updateFeature(feature):
                        skipped += 1
                        continue

                    # Capture new geometry WKB after successful update
                    new_wkb = None
                    try:
                        new_wkb = base64.b64encode(smoothed_geom.asWkb()).decode('utf-8')
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
                    if not self.commit_changes(layer, "polygon layer smoothing"):
                        return

                # Record history
                try:
                    self.record_to_history(
                        description=(
                            f"Smoothed layer '{layer.name()}' "
                            f"({processed} features, {iterations} iterations, offset {offset:.2f})"
                        ),
                        undo_type='update_geometry',
                        can_undo=True,
                        undo_payload=None,
                        layers=[self.create_layer_descriptor(layer)],
                        features=feature_backups,
                        meta={'iterations': iterations, 'offset': offset},
                    )
                except Exception:
                    pass

            except Exception as e:
                self.show_error("Error", f"Failed to smooth layer: {str(e)}")
                if rollback_on_error and handle_edit_mode:
                    self.rollback_changes(layer)
                return

            finally:
                if handle_edit_mode:
                    self.exit_edit_mode(layer, edit_mode_entered)

        # --- Success message ---
        if show_success and processed > 0:
            msg = (
                f"Layer '{layer.name()}' smoothed successfully.\n\n"
                f"Features processed: {processed}"
            )
            if skipped > 0:
                msg += f"\nFeatures skipped: {skipped}"
            msg += f"\nIterations: {iterations}\nOffset: {offset:.2f}"

            if create_copy:
                msg += "\n\nOriginal layer remains unchanged."

            self.show_info("Success", msg)
        elif show_success and processed == 0:
            self.show_error("Warning", "No features were smoothed.")

    def supports_undo(self):
        """This action supports undo via stored geometry backups."""
        return True

    def get_undo_category(self):
        """Return undo category for history grouping."""
        return 'payload'


# REQUIRED: Create global instance for automatic discovery
smooth_polygon_layer = SmoothPolygonLayerAction()
