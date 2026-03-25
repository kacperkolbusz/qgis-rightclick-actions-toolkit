"""
Generalize Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Generalizes all polygon features in the selected layer using the Douglas-Peucker algorithm.
Reduces the number of vertices across all features while preserving overall shapes.
Supports processing only selected features and creating a generalized copy layer.
"""

import base64

from .base_action import BaseAction
from qgis.core import (
    QgsGeometry, QgsWkbTypes, QgsFeature, QgsVectorLayer,
    QgsProject, QgsFeatureRequest, QgsField
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QDoubleSpinBox, QCheckBox, QGroupBox
)
from qgis.PyQt.QtCore import QVariant, QMetaType


class GeneralizePolygonLayerDialog(QDialog):
    """Dialog for configuring layer-level polygon generalization."""

    def __init__(self, parent=None, default_tolerance=1.0,
                 feature_count=None, selected_count=None,
                 ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Generalize Polygon Layer")
        self.setModal(True)
        self.resize(420, 320)

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

        # Tolerance input
        self.tolerance_spinbox = QDoubleSpinBox()
        self.tolerance_spinbox.setRange(0.0, 1000000.0)
        self.tolerance_spinbox.setValue(default_tolerance)
        self.tolerance_spinbox.setSuffix(" map units")
        self.tolerance_spinbox.setDecimals(2)
        self.tolerance_spinbox.setSingleStep(0.1)
        form_layout.addRow("Tolerance (Distance):", self.tolerance_spinbox)

        tolerance_help = QLabel(
            "Higher tolerance = more simplification (fewer vertices). "
            "Points within this distance from the simplified polygon boundary are removed."
        )
        tolerance_help.setStyleSheet("color: gray; font-size: 10px;")
        tolerance_help.setWordWrap(True)
        form_layout.addRow("", tolerance_help)

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
        self.ok_button = QPushButton("Generalize")
        self.cancel_button = QPushButton("Cancel")

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.tolerance_spinbox.setFocus()
        self.tolerance_spinbox.selectAll()

    def get_values(self):
        """Get the dialog input values."""
        return {
            'tolerance': self.tolerance_spinbox.value(),
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


class GeneralizePolygonLayerAction(BaseAction):
    """
    Action to generalize all polygon features in a layer using the Douglas-Peucker algorithm.

    This action simplifies every polygon feature in the layer by reducing the number of
    vertices while preserving overall shapes. Uses Douglas-Peucker algorithm (via QGIS
    simplify method). Supports processing only selected features and creating a
    generalized copy layer while keeping the original unchanged.
    """

    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()

        # Required properties
        self.action_id = "generalize_polygon_layer"
        self.name = "Generalize Polygon Layer"
        self.category = "Editing"
        self.description = (
            "Generalize all polygon features in the layer using the Douglas-Peucker algorithm. "
            "Reduces the number of vertices across all features while preserving overall shapes. "
            "Supports processing only selected features and creating a generalized copy layer."
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
            # GENERALIZATION SETTINGS
            'default_tolerance': {
                'type': 'float',
                'default': 1.0,
                'label': 'Default Tolerance',
                'description': (
                    'Default tolerance value in map units '
                    '(distance threshold for Douglas-Peucker algorithm)'
                ),
                'min': 0.0,
                'max': 1000000.0,
                'step': 0.1,
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
                'description': 'Display a summary message after completing generalization',
            },
            'show_layer_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Information',
                'description': 'Display feature count and vertex statistics in dialogs',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after generalizing (recommended)',
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
                'description': 'Rollback all changes if any generalization operation fails',
            },
        }

    def get_setting(self, setting_name, default_value=None):
        """Get a setting value for this action."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    @staticmethod
    def _generalize_geometry(geometry, tolerance):
        """Apply Douglas-Peucker simplification to a geometry."""
        return QgsGeometry(geometry).simplify(tolerance)

    @staticmethod
    def _count_vertices(geometry):
        """Count the vertices in a geometry."""
        try:
            return len(list(geometry.vertices()))
        except Exception:
            return 0

    def execute(self, context):
        """Execute the generalize polygon layer action."""
        # --- Read settings ---
        try:
            default_tolerance = float(self.get_setting('default_tolerance', 1.0))
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

        dialog = GeneralizePolygonLayerDialog(
            None,
            default_tolerance=default_tolerance,
            feature_count=feature_count,
            selected_count=selected_count if selected_count > 0 else None,
            ask_copy=show_copy_option,
            default_copy=default_copy,
        )

        from qgis.PyQt.QtWidgets import QDialog as _QDialog
        if dialog.exec_() != _QDialog.Accepted:
            return  # User cancelled

        values = dialog.get_values()
        tolerance = values['tolerance']
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

        total_old_vertices = 0
        total_new_vertices = 0
        processed = 0
        skipped = 0

        # =====================================================================
        # PATH A: Create a new (copy) layer
        # =====================================================================
        if create_copy:
            layer_crs = layer.crs().authid()

            new_layer = QgsVectorLayer(
                f"MultiPolygon?crs={layer_crs}",
                f"{layer.name()} (Generalized)",
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

                old_v = self._count_vertices(geom)
                generalized_geom = self._generalize_geometry(geom, tolerance)

                if not generalized_geom or generalized_geom.isEmpty():
                    skipped += 1
                    continue

                new_v = self._count_vertices(generalized_geom)
                total_old_vertices += old_v
                total_new_vertices += new_v
                processed += 1

                new_feat = QgsFeature(new_layer.fields())
                new_feat.setGeometry(generalized_geom)
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
                    "Save Generalized Layer",
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
                        saved_layer = QgsVectorLayer(save_path, f"{layer.name()} (Generalized)", "ogr")
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
                        f"Created generalized copy of layer '{layer.name()}' "
                        f"({processed} features, tolerance {tolerance:.2f})"
                    ),
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload=None,
                    layers=[self.create_layer_descriptor(added_layer)],
                    meta={'tolerance': tolerance, 'source_layer': layer.id()},
                )
            except Exception:
                pass

        # =====================================================================
        # PATH B: Modify the original layer in place
        # =====================================================================
        else:
            edit_result = None
            edit_mode_entered = False

            if handle_edit_mode:
                edit_result = self.handle_edit_mode(layer, "polygon layer generalization")
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

                    old_v = self._count_vertices(geom)
                    generalized_geom = self._generalize_geometry(geom, tolerance)

                    if not generalized_geom or generalized_geom.isEmpty():
                        skipped += 1
                        continue

                    new_v = self._count_vertices(generalized_geom)
                    total_old_vertices += old_v
                    total_new_vertices += new_v

                    # Capture old geometry WKB before modifying
                    old_wkb = None
                    try:
                        old_wkb = base64.b64encode(geom.asWkb()).decode('utf-8')
                    except Exception:
                        pass

                    feature.setGeometry(generalized_geom)
                    if not layer.updateFeature(feature):
                        skipped += 1
                        total_old_vertices -= old_v
                        total_new_vertices -= new_v
                        continue

                    # Capture new geometry WKB after successful update
                    new_wkb = None
                    try:
                        new_wkb = base64.b64encode(generalized_geom.asWkb()).decode('utf-8')
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
                    if not self.commit_changes(layer, "polygon layer generalization"):
                        return

                # Record history
                try:
                    self.record_to_history(
                        description=(
                            f"Generalized layer '{layer.name()}' "
                            f"({processed} features, tolerance {tolerance:.2f})"
                        ),
                        undo_type='update_geometry',
                        can_undo=True,
                        undo_payload=None,
                        layers=[self.create_layer_descriptor(layer)],
                        features=feature_backups,
                        meta={'tolerance': tolerance},
                    )
                except Exception:
                    pass

            except Exception as e:
                self.show_error("Error", f"Failed to generalize layer: {str(e)}")
                if rollback_on_error and handle_edit_mode:
                    self.rollback_changes(layer)
                return

            finally:
                if handle_edit_mode:
                    self.exit_edit_mode(layer, edit_mode_entered)

        # --- Success message ---
        if show_success and processed > 0:
            msg = (
                f"Layer '{layer.name()}' generalized successfully.\n\n"
                f"Features processed: {processed}"
            )
            if skipped > 0:
                msg += f"\nFeatures skipped: {skipped}"
            msg += f"\nTolerance: {tolerance:.2f} map units"

            if total_old_vertices > 0:
                reduction = total_old_vertices - total_new_vertices
                pct = (reduction / total_old_vertices * 100) if total_old_vertices > 0 else 0
                msg += (
                    f"\n\nTotal vertices: {total_old_vertices} → {total_new_vertices} "
                    f"(reduced by {reduction}, {pct:.1f}%)"
                )

            if create_copy:
                msg += "\n\nOriginal layer remains unchanged."

            self.show_info("Success", msg)
        elif show_success and processed == 0:
            self.show_error("Warning", "No features were generalized.")

    def supports_undo(self):
        """This action supports undo via stored geometry backups."""
        return True

    def get_undo_category(self):
        """Return undo category for history grouping."""
        return 'payload'


# REQUIRED: Create global instance for automatic discovery
generalize_polygon_layer = GeneralizePolygonLayerAction()
