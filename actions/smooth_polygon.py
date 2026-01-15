"""
Smooth Polygon Action for Right-click Utilities and Shortcuts Hub

Smooths the borders/edges of the selected polygon feature using configurable smoothing algorithms.
Uses Chaikin's corner cutting algorithm by default, with architecture for future methods.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsWkbTypes, QgsFeature
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox
)


class SmoothPolygonDialog(QDialog):
    """Unified dialog for smoothing polygon with copy option."""
    
    def __init__(self, parent=None, default_iterations=1, default_offset=0.25, 
                 polygon_area=None, ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Smooth Polygon")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Polygon area info
        if polygon_area is not None:
            area_label = QLabel(f"Polygon area: {polygon_area:.2f} square map units")
            area_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", area_label)
        
        # Iterations input
        self.iterations_spinbox = QSpinBox()
        self.iterations_spinbox.setRange(1, 10)
        self.iterations_spinbox.setValue(default_iterations)
        self.iterations_spinbox.setSuffix(" passes")
        form_layout.addRow("Smoothing Iterations:", self.iterations_spinbox)
        
        iterations_help = QLabel("More iterations = smoother borders (1-10 recommended)")
        iterations_help.setStyleSheet("color: gray; font-size: 10px;")
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
        form_layout.addRow("", offset_help)
        
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
        self.ok_button = QPushButton("Smooth")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to iterations input
        self.iterations_spinbox.setFocus()
        self.iterations_spinbox.selectAll()
    
    def get_values(self):
        """Get the input values."""
        return {
            'iterations': self.iterations_spinbox.value(),
            'offset': self.offset_spinbox.value(),
            'create_copy': self.create_copy_checkbox.isChecked() if hasattr(self, 'create_copy_checkbox') else False
        }


class SmoothPolygonAction(BaseAction):
    """
    Action to smooth polygon borders/edges using configurable smoothing algorithms.
    
    This action smooths the borders of the selected polygon feature using Chaikin's corner
    cutting algorithm by default. The architecture allows for easy addition of other smoothing
    methods in the future. Supports creating a smoothed copy while keeping the original unchanged.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "smooth_polygon"
        self.name = "Smooth Polygon"
        self.category = "Editing"
        self.description = "Smooth the borders/edges of the selected polygon feature using configurable smoothing algorithms. Uses Chaikin's corner cutting algorithm by default. Supports creating a smoothed copy while keeping the original unchanged. Configurable iterations and offset parameters control smoothing strength."
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
            'smoothing_method': {
                'type': 'choice',
                'default': 'chaikin',
                'label': 'Smoothing Method',
                'description': 'Smoothing algorithm to use (Chaikin is the default, others can be added in future)',
                'options': ['chaikin'],
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
                'description': 'Use a single dialog for all inputs (iterations, offset, copy). If disabled, shows separate popups for each input.',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_before_smooth': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Smoothing',
                'description': 'Show confirmation dialog before smoothing the polygon',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when polygon is smoothed successfully',
            },
            'show_polygon_area_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Polygon Area Info',
                'description': 'Display polygon area information in the input dialog and success messages',
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
                'description': 'Rollback changes if smoothing operation fails',
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
    
    def smooth_geometry_chaikin(self, geometry, iterations, offset):
        """
        Smooth geometry using Chaikin's corner cutting algorithm.
        
        This is the default smoothing method. Future methods can be added as separate functions.
        
        Args:
            geometry (QgsGeometry): Geometry to smooth
            iterations (int): Number of smoothing passes
            offset (float): Smoothing offset (0.0-1.0)
            
        Returns:
            QgsGeometry: Smoothed geometry
        """
        # Create a copy of the geometry
        smoothed_geometry = QgsGeometry(geometry)
        
        # Apply smoothing using QGIS built-in method
        smoothed_geometry = smoothed_geometry.smooth(iterations, offset)
        
        return smoothed_geometry
    
    def smooth_geometry(self, geometry, method, iterations, offset):
        """
        Smooth geometry using the specified method.
        
        This method acts as a router for different smoothing algorithms.
        New methods can be added here in the future.
        
        Args:
            geometry (QgsGeometry): Geometry to smooth
            method (str): Smoothing method name ('chaikin', etc.)
            iterations (int): Number of smoothing passes
            offset (float): Smoothing offset (method-specific)
            
        Returns:
            QgsGeometry: Smoothed geometry
        """
        if method == 'chaikin':
            return self.smooth_geometry_chaikin(geometry, iterations, offset)
        else:
            # Default to Chaikin if unknown method
            return self.smooth_geometry_chaikin(geometry, iterations, offset)
    
    def execute(self, context):
        """
        Execute the smooth polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            default_iterations = int(self.get_setting('default_iterations', 1))
            default_offset = float(self.get_setting('default_offset', 0.25))
            smoothing_method = str(self.get_setting('smoothing_method', 'chaikin'))
            ask_create_copy = bool(self.get_setting('ask_create_copy', True))
            default_copy_choice = str(self.get_setting('default_copy_choice', 'ask'))
            show_copy_info = bool(self.get_setting('show_copy_info_in_messages', True))
            use_unified_dialog = bool(self.get_setting('use_unified_dialog', True))
            confirm_before_smooth = bool(self.get_setting('confirm_before_smooth', False))
            show_success = bool(self.get_setting('show_success_message', True))
            show_polygon_area = bool(self.get_setting('show_polygon_area_info', True))
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
        
        # Calculate polygon area if requested
        polygon_area = None
        if show_polygon_area:
            try:
                polygon_area = geometry.area()
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
            
            dialog = SmoothPolygonDialog(
                None,
                default_iterations=default_iterations,
                default_offset=default_offset,
                polygon_area=polygon_area,
                ask_copy=show_copy_option,
                default_copy=default_copy
            )
            
            if dialog.exec_() != QDialog.Accepted:
                return  # User cancelled
            
            values = dialog.get_values()
            iterations = values['iterations']
            offset = values['offset']
            create_copy = values['create_copy'] if show_copy_option else (default_copy_choice == 'copy')
        else:
            # Use separate popups (legacy behavior) - simplified for now
            from qgis.PyQt.QtWidgets import QInputDialog
            
            iterations, ok1 = QInputDialog.getInt(
                None,
                "Smooth Polygon",
                "Enter number of smoothing iterations (1-10):",
                default_iterations,
                1,
                10,
                1
            )
            
            if not ok1:
                return  # User cancelled
            
            offset, ok2 = QInputDialog.getDouble(
                None,
                "Smooth Polygon",
                "Enter smoothing offset (0.0-1.0):",
                default_offset,
                0.0,
                1.0,
                2
            )
            
            if not ok2:
                return  # User cancelled
            
            create_copy = False
            if ask_create_copy:
                if default_copy_choice == 'ask':
                    from qgis.PyQt.QtWidgets import QMessageBox
                    reply = QMessageBox.question(
                        None,
                        "Create Copy?",
                        "Would you like to create a copy of the polygon?\n\n"
                        "Yes: Create a smoothed copy (original stays unchanged)\n"
                        "No: Smooth the original polygon",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if reply == QMessageBox.Cancel:
                        return
                    create_copy = (reply == QMessageBox.Yes)
                elif default_copy_choice == 'copy':
                    create_copy = True
                else:
                    create_copy = False
        
        # Confirm smoothing if enabled
        if confirm_before_smooth:
            confirmation_message = f"Smooth polygon feature ID {feature.id()} from layer '{layer.name()}'?\n\n"
            confirmation_message += f"Iterations: {iterations}\n"
            confirmation_message += f"Offset: {offset:.2f}\n"
            if show_polygon_area and polygon_area is not None:
                confirmation_message += f"\nPolygon area: {polygon_area:.2f} square map units"
            
            if not self.confirm_action("Smooth Polygon", confirmation_message):
                return
        
        # Handle edit mode
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "polygon smoothing")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Smooth the geometry
            smoothed_geometry = self.smooth_geometry(geometry, smoothing_method, iterations, offset)
            
            if not smoothed_geometry or smoothed_geometry.isEmpty():
                self.show_error("Error", "Smoothing resulted in invalid geometry")
                return
            
            # Determine operation type
            if create_copy:
                # Create a new feature with smoothed geometry
                new_feature = QgsFeature(feature)
                new_feature.setId(-1)  # Let QGIS assign new ID
                new_feature.setGeometry(smoothed_geometry)
                
                if not layer.addFeature(new_feature):
                    self.show_error("Error", "Failed to create smoothed copy of feature")
                    return
                
                feature_to_update = new_feature
                operation_type = "copy"
            else:
                # Update the original feature
                feature.setGeometry(smoothed_geometry)
                if not layer.updateFeature(feature):
                    self.show_error("Error", "Failed to update polygon geometry")
                    return
                
                feature_to_update = feature
                operation_type = "smooth"
            
            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, "polygon smoothing"):
                    return
            
            # Show success message if enabled
            if show_success:
                if operation_type == "copy":
                    success_message = f"Smoothed copy of polygon feature ID {feature.id()} created successfully (ID: {feature_to_update.id()})"
                else:
                    success_message = f"Polygon feature ID {feature.id()} smoothed successfully"
                
                success_message += f"\n\nIterations: {iterations}\nOffset: {offset:.2f}"
                
                if show_polygon_area and polygon_area is not None:
                    try:
                        new_area = smoothed_geometry.area()
                        success_message += f"\n\nOriginal area: {polygon_area:.2f} square map units"
                        success_message += f"\nNew area: {new_area:.2f} square map units"
                    except Exception:
                        pass
                
                if show_copy_info and operation_type == "copy":
                    success_message += "\n\nOriginal feature remains unchanged."
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to smooth polygon: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
        
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
smooth_polygon = SmoothPolygonAction()

