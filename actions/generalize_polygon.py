"""
Generalize Polygon Action for Right-click Utilities and Shortcuts Hub

Generalizes the selected polygon feature using Douglas-Peucker algorithm.
Reduces the number of vertices while preserving the overall shape of the polygon.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsWkbTypes, QgsFeature
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFormLayout, QDoubleSpinBox, QCheckBox, QGroupBox
)


class GeneralizePolygonDialog(QDialog):
    """Unified dialog for generalizing polygon with copy option."""
    
    def __init__(self, parent=None, default_tolerance=1.0, 
                 polygon_area=None, vertex_count=None, ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Generalize Polygon")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Polygon info
        info_lines = []
        if polygon_area is not None:
            info_lines.append(f"Polygon area: {polygon_area:.2f} square map units")
        if vertex_count is not None:
            info_lines.append(f"Current vertices: {vertex_count}")
        
        if info_lines:
            info_label = QLabel("\n".join(info_lines))
            info_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", info_label)
        
        # Tolerance input
        self.tolerance_spinbox = QDoubleSpinBox()
        self.tolerance_spinbox.setRange(0.0, 1000000.0)
        self.tolerance_spinbox.setValue(default_tolerance)
        self.tolerance_spinbox.setSuffix(" map units")
        self.tolerance_spinbox.setDecimals(2)
        self.tolerance_spinbox.setSingleStep(0.1)
        form_layout.addRow("Tolerance (Distance):", self.tolerance_spinbox)
        
        tolerance_help = QLabel("Higher tolerance = more simplification (fewer vertices). Points within this distance from simplified polygon boundary are removed.")
        tolerance_help.setStyleSheet("color: gray; font-size: 10px;")
        tolerance_help.setWordWrap(True)
        form_layout.addRow("", tolerance_help)
        
        layout.addLayout(form_layout)
        
        # Copy option group
        if ask_copy:
            copy_group = QGroupBox("Copy Options")
            copy_layout = QVBoxLayout()
            
            self.create_copy_checkbox = QCheckBox("Create a copy (original stays unchanged)")
            self.create_copy_checkbox.setChecked(default_copy)
            copy_layout.addWidget(self.create_copy_checkbox)
            
            copy_group.setLayout(copy_layout)
            layout.addWidget(copy_group)
        
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
        
        # Set focus to tolerance input
        self.tolerance_spinbox.setFocus()
        self.tolerance_spinbox.selectAll()
    
    def get_values(self):
        """Get the input values."""
        return {
            'tolerance': self.tolerance_spinbox.value(),
            'create_copy': self.create_copy_checkbox.isChecked() if hasattr(self, 'create_copy_checkbox') else False
        }


class GeneralizePolygonAction(BaseAction):
    """
    Action to generalize polygon features using Douglas-Peucker algorithm.
    
    This action simplifies the selected polygon feature by reducing the number of vertices
    while preserving the overall shape. Uses Douglas-Peucker algorithm (via QGIS simplify method).
    Supports creating a generalized copy while keeping the original unchanged.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "generalize_polygon"
        self.name = "Generalize Polygon"
        self.category = "Editing"
        self.description = "Generalize the selected polygon feature using Douglas-Peucker algorithm. Reduces the number of vertices while preserving the overall shape. Uses tolerance parameter to control simplification strength. Supports creating a generalized copy while keeping the original unchanged."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - works with all polygon types
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # GENERALIZATION SETTINGS
            'default_tolerance': {
                'type': 'float',
                'default': 1.0,
                'label': 'Default Tolerance',
                'description': 'Default tolerance value in map units (distance threshold for Douglas-Peucker algorithm)',
                'min': 0.0,
                'max': 1000000.0,
                'step': 0.1,
            },
            
            # COPY SETTINGS
            'ask_create_copy': {
                'type': 'bool',
                'default': True,
                'label': 'Ask to Create Copy',
                'description': 'Ask user each time if they want to create a copy instead of modifying the original',
            },
            'default_copy_choice': {
                'type': 'choice',
                'default': 'ask',
                'label': 'Default Copy Choice',
                'description': 'Default choice when asking about creating copy. "ask" means prompt user each time, "copy" means always create copy, "move" means always modify original.',
                'options': ['ask', 'copy', 'move'],
            },
            'show_copy_info_in_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Copy Info in Messages',
                'description': 'Include information about copy creation in success messages',
            },
            
            # DIALOG SETTINGS
            'use_unified_dialog': {
                'type': 'bool',
                'default': True,
                'label': 'Use Unified Dialog',
                'description': 'Use a single dialog for all inputs (tolerance, copy). If disabled, shows separate popups for each input.',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_before_generalize': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Generalizing',
                'description': 'Show confirmation dialog before generalizing the polygon',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when polygon is generalized successfully',
            },
            'show_polygon_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Polygon Information',
                'description': 'Display polygon area and vertex count information in dialogs and success messages',
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
                'description': 'Rollback changes if generalization operation fails',
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
    
    def generalize_geometry_douglas_peucker(self, geometry, tolerance):
        """
        Generalize geometry using Douglas-Peucker algorithm.
        
        This uses QGIS's built-in simplify() method which implements Douglas-Peucker algorithm.
        
        Args:
            geometry (QgsGeometry): Geometry to generalize
            tolerance (float): Distance tolerance in map units
            
        Returns:
            QgsGeometry: Generalized geometry
        """
        # Create a copy of the geometry
        generalized_geometry = QgsGeometry(geometry)
        
        # Apply simplification using QGIS built-in method (Douglas-Peucker)
        generalized_geometry = generalized_geometry.simplify(tolerance)
        
        return generalized_geometry
    
    def count_vertices(self, geometry):
        """
        Count the number of vertices in a geometry.
        
        Args:
            geometry (QgsGeometry): Geometry to count vertices for
            
        Returns:
            int: Number of vertices
        """
        try:
            vertices = geometry.vertices()
            return len(list(vertices))
        except Exception:
            return 0
    
    def execute(self, context):
        """
        Execute the generalize polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            default_tolerance = float(self.get_setting('default_tolerance', 1.0))
            ask_create_copy = bool(self.get_setting('ask_create_copy', True))
            default_copy_choice = str(self.get_setting('default_copy_choice', 'ask'))
            show_copy_info = bool(self.get_setting('show_copy_info_in_messages', True))
            use_unified_dialog = bool(self.get_setting('use_unified_dialog', True))
            confirm_before_generalize = bool(self.get_setting('confirm_before_generalize', False))
            show_success = bool(self.get_setting('show_success_message', True))
            show_polygon_info = bool(self.get_setting('show_polygon_info', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Get feature geometry
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            self.show_error("Error", "Feature has no valid geometry")
            return
        
        # Validate that this is a polygon feature
        if geometry.type() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon features")
            return
        
        # Calculate polygon info if requested
        polygon_area = None
        vertex_count = None
        if show_polygon_info:
            try:
                polygon_area = geometry.area()
                vertex_count = self.count_vertices(geometry)
            except Exception:
                pass
        
        # Get user input - use unified dialog or separate popups
        if use_unified_dialog:
            # Determine default copy choice
            default_copy = False
            show_copy_option = False
            if ask_create_copy:
                if default_copy_choice == 'copy':
                    default_copy = True
                    show_copy_option = True
                elif default_copy_choice == 'move':
                    default_copy = False
                    show_copy_option = True
                else:  # 'ask'
                    default_copy = False
                    show_copy_option = True
            
            dialog = GeneralizePolygonDialog(
                None,
                default_tolerance=default_tolerance,
                polygon_area=polygon_area,
                vertex_count=vertex_count,
                ask_copy=show_copy_option,
                default_copy=default_copy
            )
            
            if dialog.exec_() != QDialog.Accepted:
                return  # User cancelled
            
            values = dialog.get_values()
            tolerance = values['tolerance']
            create_copy = values['create_copy'] if show_copy_option else (default_copy_choice == 'copy')
        else:
            # Use separate popups (legacy behavior)
            from qgis.PyQt.QtWidgets import QInputDialog
            
            tolerance, ok1 = QInputDialog.getDouble(
                None,
                "Generalize Polygon",
                "Enter tolerance (distance in map units):",
                default_tolerance,
                0.0,
                1000000.0,
                2
            )
            
            if not ok1:
                return  # User cancelled
            
            create_copy = False
            if ask_create_copy:
                if default_copy_choice == 'ask':
                    from qgis.PyQt.QtWidgets import QMessageBox
                    reply = QMessageBox.question(
                        None,
                        "Create Copy?",
                        "Would you like to create a copy of the polygon?\n\n"
                        "Yes: Create a generalized copy (original stays unchanged)\n"
                        "No: Generalize the original polygon",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if reply == QMessageBox.Cancel:
                        return
                    create_copy = (reply == QMessageBox.Yes)
                elif default_copy_choice == 'copy':
                    create_copy = True
                else:
                    create_copy = False
        
        # Confirm generalization if enabled
        if confirm_before_generalize:
            confirmation_message = f"Generalize polygon feature ID {feature.id()} from layer '{layer.name()}'?\n\n"
            confirmation_message += f"Tolerance: {tolerance:.2f} map units\n"
            if show_polygon_info:
                if polygon_area is not None:
                    confirmation_message += f"Polygon area: {polygon_area:.2f} square map units\n"
                if vertex_count is not None:
                    confirmation_message += f"Current vertices: {vertex_count}"
            
            if not self.confirm_action("Generalize Polygon", confirmation_message):
                return
        
        # Handle edit mode
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "polygon generalization")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Generalize the geometry
            generalized_geometry = self.generalize_geometry_douglas_peucker(geometry, tolerance)
            
            if not generalized_geometry or generalized_geometry.isEmpty():
                self.show_error("Error", "Generalization resulted in invalid geometry")
                return
            
            # Count vertices after generalization
            new_vertex_count = self.count_vertices(generalized_geometry)
            
            # Determine operation type
            if create_copy:
                # Create a new feature with generalized geometry
                new_feature = QgsFeature(feature)
                new_feature.setId(-1)  # Let QGIS assign new ID
                new_feature.setGeometry(generalized_geometry)

                # Try to add using the provider so we can capture assigned FID
                added_ok = False
                added_feature_obj = None
                try:
                    provider = layer.dataProvider()
                    if provider:
                        res = provider.addFeatures([new_feature])
                        if isinstance(res, tuple) and len(res) >= 2:
                            success, added_feats = res[0], res[1]
                            if success and added_feats:
                                added_ok = True
                                added_feature_obj = added_feats[0]
                        elif isinstance(res, bool):
                            added_ok = res
                except Exception:
                    added_ok = False

                # Fallback to layer.addFeature if provider.addFeatures not available
                if not added_ok:
                    try:
                        added_ok = layer.addFeature(new_feature)
                        if added_ok:
                            # try to find the added feature by geometry
                            try:
                                geom_wkb = new_feature.geometry().asWkb()
                                for f in layer.getFeatures():
                                    try:
                                        if f.geometry() and f.geometry().asWkb() == geom_wkb:
                                            added_feature_obj = f
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                    except Exception:
                        added_ok = False

                if not added_ok:
                    self.show_error("Error", "Failed to create generalized copy of feature")
                    return

                try:
                    layer.updateExtents()
                except Exception:
                    pass

                feature_to_update = added_feature_obj if added_feature_obj is not None else new_feature
                operation_type = "copy"
            else:
                # Backup original feature before modifying
                try:
                    original_backup = self.create_feature_backup(feature, layer)
                except Exception:
                    original_backup = None

                # Update the original feature
                feature.setGeometry(generalized_geometry)
                if not layer.updateFeature(feature):
                    self.show_error("Error", "Failed to update polygon geometry")
                    return

                feature_to_update = feature
                operation_type = "generalize"
            
            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, "polygon generalization"):
                    return

            # Record history after successful commit
            try:
                layers = [self.create_layer_descriptor(layer)]
                if operation_type == "copy":
                    try:
                        created_backup = self.create_feature_backup(feature_to_update, layer)
                    except Exception:
                        created_backup = {'fid': feature_to_update.id()}

                    self.record_to_history(
                        description=f"Created generalized copy of polygon feature {feature.id()} on layer '{layer.name()}'",
                        undo_type='create_feature',
                        can_undo=True,
                        undo_payload=None,
                        layers=layers,
                        features=[created_backup],
                        meta={'tolerance': tolerance}
                    )
                else:
                    try:
                        old_geom = None
                        if 'original_backup' in locals() and original_backup:
                            old_geom = original_backup.get('geometry')
                        else:
                            try:
                                old_geom = self.create_feature_backup(feature_to_update, layer).get('geometry')
                            except Exception:
                                old_geom = None

                        import base64
                        new_geom_wkb = None
                        try:
                            new_geom_wkb = generalized_geometry.asWkb()
                        except Exception:
                            try:
                                new_geom_wkb = feature_to_update.geometry().asWkb()
                            except Exception:
                                new_geom_wkb = None

                        new_geom = None
                        if new_geom_wkb:
                            new_geom = {'wkb_base64': base64.b64encode(new_geom_wkb).decode('utf-8')}

                        feat_payload = {'fid': feature_to_update.id()}
                        if old_geom:
                            feat_payload['old_geometry'] = old_geom
                        if new_geom:
                            feat_payload['new_geometry'] = new_geom
                    except Exception:
                        feat_payload = {'fid': feature_to_update.id()}

                    self.record_to_history(
                        description=f"Generalized polygon feature {feature.id()} on layer '{layer.name()}'",
                        undo_type='update_geometry',
                        can_undo=True,
                        undo_payload=None,
                        layers=layers,
                        features=[feat_payload],
                        meta={'tolerance': tolerance}
                    )
            except Exception:
                pass
            
            # Show success message if enabled
            if show_success:
                if operation_type == "copy":
                    success_message = f"Generalized copy of polygon feature ID {feature.id()} created successfully (ID: {feature_to_update.id()})"
                else:
                    success_message = f"Polygon feature ID {feature.id()} generalized successfully"
                
                success_message += f"\n\nTolerance: {tolerance:.2f} map units"
                
                if show_polygon_info and vertex_count is not None:
                    reduction = vertex_count - new_vertex_count
                    reduction_percent = (reduction / vertex_count * 100) if vertex_count > 0 else 0
                    success_message += f"\n\nVertices: {vertex_count} → {new_vertex_count} (reduced by {reduction}, {reduction_percent:.1f}%)"
                    
                    try:
                        new_area = generalized_geometry.area()
                        if polygon_area is not None:
                            area_change = abs(new_area - polygon_area)
                            area_change_percent = (area_change / polygon_area * 100) if polygon_area > 0 else 0
                            success_message += f"\nArea: {polygon_area:.2f} → {new_area:.2f} square map units (change: {area_change_percent:.2f}%)"
                    except Exception:
                        pass
                
                if show_copy_info and operation_type == "copy":
                    success_message += "\n\nOriginal feature remains unchanged."
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to generalize polygon: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
        
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)

    def supports_undo(self):
        """This action supports undo via stored geometry backups."""
        return True

    def get_undo_category(self):
        """Return undo category for history grouping."""
        return 'payload'


# REQUIRED: Create global instance for automatic discovery
generalize_polygon = GeneralizePolygonAction()

