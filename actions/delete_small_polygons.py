"""
Delete Small Polygons Action for Right-click Utilities and Shortcuts Hub

Deletes polygon features smaller than a specified area from polygon layers.
User can choose the minimum area threshold before deletion is performed.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsFeature, QgsGeometry, QgsWkbTypes
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
                                QGridLayout, QMessageBox, QProgressBar, QTextEdit)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont


class DeleteSmallPolygonsAction(BaseAction):
    """
    Action to delete polygon features smaller than a specified area.
    
    This action works on polygon layers and allows users to specify a minimum
    area threshold. All polygons smaller than this threshold will be deleted.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "delete_small_polygons"
        self.name = "Delete Small Polygons"
        self.category = "Editing"
        self.description = "Delete polygon features smaller than a specified area from the layer. User can choose the minimum area threshold and preview affected features before deletion. Automatically handles edit mode and provides detailed feedback."
        self.enabled = True
        
        # Action scoping - layer action that works on polygon layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    # Undo support: deleting features must create backups for undo
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'default_minimum_area': {
                'type': 'float',
                'default': 100.0,
                'label': 'Default Minimum Area',
                'description': 'Default minimum area threshold for polygon deletion',
                'min': 0.0,
                'max': 1000000.0,
                'step': 1.0,
            },
            'area_unit': {
                'type': 'choice',
                'default': 'map_units',
                'label': 'Area Unit',
                'description': 'Unit for area calculations and display',
                'options': ['map_units', 'square_meters', 'square_feet', 'hectares', 'acres'],
            },
            'show_preview': {
                'type': 'bool',
                'default': True,
                'label': 'Show Preview',
                'description': 'Show preview of features to be deleted before confirmation',
            },
            'confirm_deletion': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Deletion',
                'description': 'Show confirmation dialog before deleting features',
            },
            'show_progress': {
                'type': 'bool',
                'default': True,
                'label': 'Show Progress',
                'description': 'Show progress bar during deletion process',
            },
            'auto_commit': {
                'type': 'bool',
                'default': True,
                'label': 'Auto Commit Changes',
                'description': 'Automatically commit changes after deletion',
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """
        Get a setting value for this action.
        
        Args:
            setting_name (str): Name of the setting to retrieve
            default_value: Default value if setting not found
            
        Returns:
            Setting value or default_value
        """
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def execute(self, context):
        """
        Execute the delete small polygons action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            default_minimum_area = float(self.get_setting('default_minimum_area', 100.0))
            area_unit = str(self.get_setting('area_unit', 'map_units'))
            show_preview = bool(self.get_setting('show_preview', True))
            confirm_deletion = bool(self.get_setting('confirm_deletion', True))
            show_progress = bool(self.get_setting('show_progress', True))
            auto_commit = bool(self.get_setting('auto_commit', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        try:
            # Extract context elements
            detected_features = context.get('detected_features', [])
            
            if not detected_features:
                self.show_error("Error", "No polygon features found at this location")
                return
            
            # Get the layer from the first detected feature
            detected_feature = detected_features[0]
            layer = detected_feature.layer
            
            # Check if it's a polygon layer
            if layer.type() != layer.VectorLayer:
                self.show_error("Error", "Selected layer is not a vector layer")
                return
            
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                self.show_error("Error", "Selected layer is not a polygon layer")
                return
            
            # Get layer CRS for area calculations
            layer_crs = layer.crs()
            
            # Create and show the deletion dialog
            dialog = DeleteSmallPolygonsDialog(
                self, layer, layer_crs, default_minimum_area, area_unit,
                show_preview, confirm_deletion, show_progress, auto_commit
            )
            dialog.exec_()
            
        except Exception as e:
            self.show_error("Error", f"Failed to delete small polygons: {str(e)}")


class DeleteSmallPolygonsDialog(QDialog):
    """Dialog for deleting small polygon features."""
    
    def __init__(self, action, layer, layer_crs, default_minimum_area, area_unit, 
                 show_preview, confirm_deletion, show_progress, auto_commit):
        """
        Initialize the delete small polygons dialog.
        
        Args:
            layer: QGIS vector layer
            layer_crs: Layer CRS
            default_minimum_area: Default minimum area threshold
            area_unit: Unit for area calculations
            show_preview: Whether to show preview
            confirm_deletion: Whether to confirm deletion
            show_progress: Whether to show progress
            auto_commit: Whether to auto-commit changes
        """
        super().__init__()
        self.action = action
        self.layer = layer
        self.layer_crs = layer_crs
        self.area_unit = area_unit
        self.show_preview = show_preview
        self.confirm_deletion = confirm_deletion
        self.show_progress = show_progress
        self.auto_commit = auto_commit
        
        self.setWindowTitle(f"Delete Small Polygons - {layer.name()}")
        self.setModal(True)
        self.resize(500, 400)
        
        self.setup_ui(default_minimum_area)
    
    def setup_ui(self, default_minimum_area):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Delete Small Polygons")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Layer info
        layer_info = QLabel(f"Layer: {self.layer.name()}")
        layer_info.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(layer_info)
        
        # Area threshold group
        threshold_group = QGroupBox("Area Threshold")
        threshold_layout = QGridLayout()
        
        # Minimum area input
        threshold_layout.addWidget(QLabel("Minimum Area:"), 0, 0)
        self.area_spinbox = QDoubleSpinBox()
        self.area_spinbox.setMinimum(0.0)
        self.area_spinbox.setMaximum(1000000.0)
        self.area_spinbox.setDecimals(2)
        self.area_spinbox.setValue(default_minimum_area)
        self.area_spinbox.setSuffix(f" {self.get_unit_display()}")
        threshold_layout.addWidget(self.area_spinbox, 0, 1)
        
        # Unit selection
        threshold_layout.addWidget(QLabel("Unit:"), 1, 0)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(['map_units', 'square_meters', 'square_feet', 'hectares', 'acres'])
        self.unit_combo.setCurrentText(self.area_unit)
        self.unit_combo.currentTextChanged.connect(self.on_unit_changed)
        threshold_layout.addWidget(self.unit_combo, 1, 1)
        
        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)
        
        # Preview group
        if self.show_preview:
            preview_group = QGroupBox("Preview")
            preview_layout = QVBoxLayout()
            
            self.preview_text = QTextEdit()
            self.preview_text.setMaximumHeight(150)
            self.preview_text.setReadOnly(True)
            preview_layout.addWidget(self.preview_text)
            
            preview_button = QPushButton("Update Preview")
            preview_button.clicked.connect(self.update_preview)
            preview_layout.addWidget(preview_button)
            
            preview_group.setLayout(preview_layout)
            layout.addWidget(preview_group)
        
        # Progress bar
        if self.show_progress:
            self.progress_bar = QProgressBar()
            self.progress_bar.setVisible(False)
            layout.addWidget(self.progress_bar)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.delete_button = QPushButton("Delete Small Polygons")
        self.delete_button.clicked.connect(self.delete_small_polygons)
        self.delete_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Initial preview update
        if self.show_preview:
            self.update_preview()
    
    def get_unit_display(self):
        """Get display name for current unit."""
        unit_map = {
            'map_units': 'map units²',
            'square_meters': 'm²',
            'square_feet': 'ft²',
            'hectares': 'ha',
            'acres': 'ac'
        }
        if hasattr(self, 'unit_combo'):
            return unit_map.get(self.unit_combo.currentText(), 'units²')
        else:
            return unit_map.get(self.area_unit, 'units²')
    
    def on_unit_changed(self):
        """Handle unit change."""
        if hasattr(self, 'area_spinbox'):
            self.area_spinbox.setSuffix(f" {self.get_unit_display()}")
        if self.show_preview and hasattr(self, 'preview_text'):
            self.update_preview()
    
    def convert_area_to_map_units(self, area, from_unit):
        """Convert area from specified unit to map units."""
        if from_unit == 'map_units':
            return area
        
        # Get conversion factors (approximate)
        conversion_factors = {
            'square_meters': 1.0,  # Assuming map units are meters
            'square_feet': 0.092903,  # 1 sq ft = 0.092903 sq m
            'hectares': 10000.0,  # 1 ha = 10,000 sq m
            'acres': 4046.86,  # 1 acre = 4046.86 sq m
        }
        
        factor = conversion_factors.get(from_unit, 1.0)
        return area * factor
    
    def convert_area_from_map_units(self, area, to_unit):
        """Convert area from map units to specified unit."""
        if to_unit == 'map_units':
            return area
        
        # Get conversion factors (approximate)
        conversion_factors = {
            'square_meters': 1.0,  # Assuming map units are meters
            'square_feet': 10.764,  # 1 sq m = 10.764 sq ft
            'hectares': 0.0001,  # 1 sq m = 0.0001 ha
            'acres': 0.000247,  # 1 sq m = 0.000247 acres
        }
        
        factor = conversion_factors.get(to_unit, 1.0)
        return area * factor
    
    def update_preview(self):
        """Update the preview of features to be deleted."""
        if not self.show_preview:
            return
        
        try:
            minimum_area = self.area_spinbox.value()
            unit = self.unit_combo.currentText()
            
            # Convert to map units for comparison
            min_area_map_units = self.convert_area_to_map_units(minimum_area, unit)
            
            # Count features
            total_features = self.layer.featureCount()
            small_features = []

            # Iterate through features
            for feature in self.layer.getFeatures():
                geometry = feature.geometry()
                if geometry and not geometry.isEmpty():
                    area = geometry.area()
                    if area < min_area_map_units:
                        small_features.append({
                            'id': feature.id(),
                            'area': area,
                            'area_display': self.convert_area_from_map_units(area, unit)
                        })
            
            # Update preview text
            preview_text = f"Total features in layer: {total_features}\n"
            preview_text += f"Features smaller than {minimum_area:.2f} {self.get_unit_display()}: {len(small_features)}\n\n"
            
            if small_features:
                preview_text += "Features to be deleted:\n"
                for feat in small_features[:10]:  # Show first 10
                    preview_text += f"  ID {feat['id']}: {feat['area_display']:.2f} {self.get_unit_display()}\n"
                
                if len(small_features) > 10:
                    preview_text += f"  ... and {len(small_features) - 10} more\n"
            else:
                preview_text += "No features will be deleted."
            
            self.preview_text.setText(preview_text)
            
        except Exception as e:
            self.preview_text.setText(f"Error updating preview: {str(e)}")
    
    def delete_small_polygons(self):
        """Delete small polygon features."""
        try:
            minimum_area = self.area_spinbox.value()
            unit = self.unit_combo.currentText()
            
            # Convert to map units for comparison
            min_area_map_units = self.convert_area_to_map_units(minimum_area, unit)
            
            # Find small features (keep full feature objects for backups)
            small_features = []
            for feature in self.layer.getFeatures():
                geometry = feature.geometry()
                if geometry and not geometry.isEmpty():
                    area = geometry.area()
                    if area < min_area_map_units:
                        small_features.append(feature)
            
            if not small_features:
                QMessageBox.information(self, "No Features", "No features found smaller than the specified area.")
                return
            
            # Show confirmation if enabled
            if self.confirm_deletion:
                reply = QMessageBox.question(
                    self, 
                    "Confirm Deletion", 
                    f"Are you sure you want to delete {len(small_features)} polygon feature(s) smaller than {minimum_area:.2f} {self.get_unit_display()}?\n\nThis action will be recorded in History and can be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return
            
            # Handle edit mode via BaseAction helper
            was_in_edit_mode, edit_mode_entered = self.action.handle_edit_mode(self.layer, "delete small polygons")
            if was_in_edit_mode is None:
                return
            
            try:
                # Show progress if enabled
                if self.show_progress:
                    self.progress_bar.setVisible(True)
                    self.progress_bar.setMaximum(len(small_features))
                    self.progress_bar.setValue(0)
                
                # Create backups and delete features
                deleted_count = 0
                backups = []
                for i, feature in enumerate(small_features):
                    try:
                        backup = self.action.create_feature_backup(feature, self.layer)
                    except Exception:
                        backup = None

                    if backup is not None:
                        backups.append(backup)

                    fid = int(feature.id())
                    if self.layer.deleteFeature(fid):
                        deleted_count += 1
                    
                    # Update progress
                    if self.show_progress:
                        self.progress_bar.setValue(i + 1)
                        from qgis.PyQt.QtWidgets import QApplication
                        QApplication.processEvents()
                
                # Commit changes if auto-commit is enabled
                if self.auto_commit:
                    if not self.action.commit_changes(self.layer, "delete small polygons"):
                        # rollback already handled by helper
                        return
                
                # Hide progress bar
                if self.show_progress:
                    self.progress_bar.setVisible(False)
                # Record to history so undo can restore deleted features
                try:
                    if backups:
                        layers = [self.action.create_layer_descriptor(self.layer)]
                        self.action.record_to_history(
                            description=f"Deleted {deleted_count} small polygon feature(s) from layer '{self.layer.name()}'",
                            undo_type='delete_feature',
                            can_undo=True,
                            undo_payload=None,
                            layers=layers,
                            features=backups,
                            meta={'deleted_count': deleted_count}
                        )
                except Exception:
                    # History recording should not prevent successful deletion
                    pass

                # Show success message
                QMessageBox.information(
                    self, 
                    "Success", 
                    f"Successfully deleted {deleted_count} polygon feature(s) smaller than {minimum_area:.2f} {self.get_unit_display()}."
                )

                # Close dialog
                self.accept()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete features: {str(e)}")
                if self.action:
                    self.action.rollback_changes(self.layer)
                else:
                    try:
                        self.layer.rollBack()
                    except Exception:
                        pass
                
            finally:
                # Exit edit mode if we entered it
                if self.action:
                    self.action.exit_edit_mode(self.layer, edit_mode_entered)
                else:
                    try:
                        if edit_mode_entered and self.layer.isEditable():
                            self.layer.commitChanges()
                            self.layer.stopEditing()
                    except Exception:
                        pass
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete small polygons: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
delete_small_polygons = DeleteSmallPolygonsAction()
