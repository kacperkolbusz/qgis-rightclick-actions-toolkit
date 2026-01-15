"""
Move Point to Coordinates Action for Right-click Utilities and Shortcuts Hub

Moves the selected point feature to exact coordinates specified by the user.
Opens a dialog window for user to input X and Y coordinates, then moves the point after confirmation.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsPointXY, QgsGeometry, QgsCoordinateTransform, QgsProject,
    QgsWkbTypes
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFormLayout, QDoubleSpinBox, QMessageBox, QCheckBox, QGroupBox
)
from qgis.core import QgsFeature


class CoordinateInputDialog(QDialog):
    """Dialog for user input of X and Y coordinates with copy option."""
    
    def __init__(self, parent=None, default_x=0.0, default_y=0.0, 
                 min_x=-999999999.0, max_x=999999999.0,
                 min_y=-999999999.0, max_y=999999999.0,
                 decimals=6, ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Move Point to Coordinates")
        self.setModal(True)
        self.resize(400, 250)
        
        # Create layout
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # X coordinate input
        self.x_spinbox = QDoubleSpinBox()
        self.x_spinbox.setRange(min_x, max_x)
        self.x_spinbox.setValue(default_x)
        self.x_spinbox.setDecimals(decimals)
        self.x_spinbox.setSuffix("")
        form_layout.addRow("X Coordinate:", self.x_spinbox)
        
        # Y coordinate input
        self.y_spinbox = QDoubleSpinBox()
        self.y_spinbox.setRange(min_y, max_y)
        self.y_spinbox.setValue(default_y)
        self.y_spinbox.setDecimals(decimals)
        self.y_spinbox.setSuffix("")
        form_layout.addRow("Y Coordinate:", self.y_spinbox)
        
        layout.addLayout(form_layout)
        
        # Copy option group
        if ask_copy:
            copy_group = QGroupBox("Copy Options")
            copy_layout = QVBoxLayout()
            
            self.create_copy_checkbox = QCheckBox("Create a copy (original stays in place)")
            self.create_copy_checkbox.setChecked(default_copy)
            copy_layout.addWidget(self.create_copy_checkbox)
            
            copy_group.setLayout(copy_layout)
            layout.addWidget(copy_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Move Point")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to X input
        self.x_spinbox.setFocus()
        self.x_spinbox.selectAll()
    
    def get_coordinates(self):
        """Get the input coordinate values."""
        return self.x_spinbox.value(), self.y_spinbox.value()
    
    def get_create_copy(self):
        """Get whether to create a copy."""
        return self.create_copy_checkbox.isChecked() if hasattr(self, 'create_copy_checkbox') else False


class CreateCopyDialog(QDialog):
    """Dialog to ask user if they want to create a copy instead of moving."""
    
    def __init__(self, parent=None, feature_type="feature"):
        super().__init__(parent)
        self.setWindowTitle("Create Copy?")
        self.setModal(True)
        self.resize(350, 120)
        
        layout = QVBoxLayout()
        
        # Message label
        message = QLabel(
            f"Would you like to create a copy of this {feature_type}?\n\n"
            "Yes: Create a copy at the new location (original stays in place)\n"
            "No: Move the original to the new location"
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.yes_button = QPushButton("Yes, Create Copy")
        self.no_button = QPushButton("No, Move Original")
        self.cancel_button = QPushButton("Cancel")
        
        self.yes_button.clicked.connect(lambda: self.done(1))  # Return 1 for copy
        self.no_button.clicked.connect(lambda: self.done(0))   # Return 0 for move
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.yes_button)
        button_layout.addWidget(self.no_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_choice(self):
        """Get user choice: 1 = create copy, 0 = move original, None = cancelled."""
        result = self.exec_()
        if result == QDialog.Rejected:
            return None
        return result


class MovePointToCoordinatesAction(BaseAction):
    """
    Action to move a point feature to exact coordinates.
    
    This action opens a dialog window where the user can input exact X and Y coordinates.
    After confirmation, the point is moved to those coordinates. Handles CRS transformation
    if the input coordinates are in a different CRS than the layer.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "move_point_to_coordinates"
        self.name = "Move Point to Coordinates"
        self.category = "Editing"
        self.description = "Move the selected point feature to exact coordinates. Opens a dialog for inputting X and Y coordinates. Automatically handles CRS transformation and edit mode."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with point features
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # COORDINATE INPUT SETTINGS
            'coordinate_decimals': {
                'type': 'int',
                'default': 6,
                'label': 'Coordinate Decimal Places',
                'description': 'Number of decimal places shown in coordinate input dialog',
                'min': 0,
                'max': 15,
                'step': 1,
            },
            'use_current_coordinates_as_default': {
                'type': 'bool',
                'default': True,
                'label': 'Use Current Coordinates as Default',
                'description': 'Pre-fill the coordinate input dialog with the current point coordinates',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_before_move': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Moving',
                'description': 'Show confirmation dialog before moving the point',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when point is moved successfully',
            },
            'show_coordinate_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Coordinate Info',
                'description': 'Display coordinate information in success messages',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after moving (recommended)',
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
                'description': 'Rollback changes if move operation fails',
            },
            
            # CRS SETTINGS
            'input_crs_mode': {
                'type': 'choice',
                'default': 'layer_crs',
                'label': 'Input CRS Mode',
                'description': 'Coordinate system for input coordinates. Layer CRS uses the layer\'s CRS, Canvas CRS uses the map canvas CRS.',
                'options': ['layer_crs', 'canvas_crs'],
            },
            'show_crs_warning': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Warning',
                'description': 'Show warning if coordinates need to be transformed between CRS',
            },
            
            # DIALOG SETTINGS
            'use_unified_dialog': {
                'type': 'bool',
                'default': True,
                'label': 'Use Unified Dialog',
                'description': 'Include copy option in coordinate input dialog. If disabled, shows separate popup for copy choice.',
            },
            
            # COPY SETTINGS
            'ask_create_copy': {
                'type': 'bool',
                'default': True,
                'label': 'Ask to Create Copy',
                'description': 'Ask user each time if they want to create a copy instead of moving the original',
            },
            'default_copy_choice': {
                'type': 'choice',
                'default': 'ask',
                'label': 'Default Copy Choice',
                'description': 'Default choice when asking about creating copy. "ask" means prompt user each time, "copy" means always create copy, "move" means always move original.',
                'options': ['ask', 'copy', 'move'],
            },
            'show_copy_info_in_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Copy Info in Messages',
                'description': 'Include information about copy creation in success messages',
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
        Execute the move point to coordinates action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            coordinate_decimals = int(self.get_setting('coordinate_decimals', 6))
            use_current_as_default = bool(self.get_setting('use_current_coordinates_as_default', True))
            confirm_before_move = bool(self.get_setting('confirm_before_move', False))
            show_success = bool(self.get_setting('show_success_message', True))
            show_coordinate_info = bool(self.get_setting('show_coordinate_info', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            input_crs_mode = str(self.get_setting('input_crs_mode', 'layer_crs'))
            show_crs_warning = bool(self.get_setting('show_crs_warning', True))
            ask_create_copy = bool(self.get_setting('ask_create_copy', True))
            default_copy_choice = str(self.get_setting('default_copy_choice', 'ask'))
            show_copy_info = bool(self.get_setting('show_copy_info_in_messages', True))
            use_unified_dialog = bool(self.get_setting('use_unified_dialog', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No point features found at this location")
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
        
        # Validate that this is a point feature
        if geometry.type() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "This action only works with point features")
            return
        
        # Get current point coordinates
        current_point = geometry.asPoint()
        current_x = current_point.x()
        current_y = current_point.y()
        
        # Determine input CRS
        layer_crs = layer.crs()
        if canvas:
            canvas_crs = canvas.mapSettings().destinationCrs()
        else:
            canvas_crs = layer_crs
        
        input_crs = canvas_crs if input_crs_mode == 'canvas_crs' else layer_crs
        
        # Transform current coordinates to input CRS if needed
        default_x = current_x
        default_y = current_y
        
        if use_current_as_default and input_crs != layer_crs:
            try:
                transform = QgsCoordinateTransform(layer_crs, input_crs, QgsProject.instance())
                transformed_point = transform.transform(current_x, current_y)
                default_x = transformed_point.x()
                default_y = transformed_point.y()
            except Exception as e:
                if show_crs_warning:
                    self.show_warning("Warning", f"Could not transform coordinates to input CRS: {str(e)}")
        
        # Determine copy options for dialog
        default_copy = False
        show_copy_option = False
        if ask_create_copy and use_unified_dialog:
            if default_copy_choice == 'copy':
                default_copy = True
                show_copy_option = True
            elif default_copy_choice == 'move':
                default_copy = False
                show_copy_option = True
            else:  # 'ask'
                default_copy = False
                show_copy_option = True
        
        # Show input dialog
        dialog = CoordinateInputDialog(
            None,
            default_x=default_x,
            default_y=default_y,
            decimals=coordinate_decimals,
            ask_copy=show_copy_option,
            default_copy=default_copy
        )
        
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get the user input coordinates
        input_x, input_y = dialog.get_coordinates()
        
        # Get copy choice from dialog or settings
        if use_unified_dialog and show_copy_option:
            create_copy = dialog.get_create_copy()
        elif use_unified_dialog:
            # Not showing option, use default
            create_copy = (default_copy_choice == 'copy')
        else:
            # Not using unified dialog, ask separately
            create_copy = False
            if ask_create_copy:
                if default_copy_choice == 'ask':
                    copy_dialog = CreateCopyDialog(None, "point")
                    copy_choice = copy_dialog.get_choice()
                    if copy_choice is None:
                        return  # User cancelled
                    create_copy = (copy_choice == 1)
                elif default_copy_choice == 'copy':
                    create_copy = True
                else:  # default_copy_choice == 'move'
                    create_copy = False
            else:
                create_copy = (default_copy_choice == 'copy')
        
        # Transform coordinates to layer CRS if needed
        target_x = input_x
        target_y = input_y
        
        if input_crs != layer_crs:
            try:
                transform = QgsCoordinateTransform(input_crs, layer_crs, QgsProject.instance())
                transformed_point = transform.transform(input_x, input_y)
                target_x = transformed_point.x()
                target_y = transformed_point.y()
                
                if show_crs_warning:
                    self.show_info("CRS Transformation", 
                        f"Coordinates transformed from {input_crs.description()} to {layer_crs.description()}")
            except Exception as e:
                self.show_error("Error", f"Failed to transform coordinates: {str(e)}")
                return
        
        # Store create_copy setting for later use
        self._create_copy = create_copy
        
        # Confirm move if enabled
        if confirm_before_move:
            action_word = "Copy" if create_copy else "Move"
            confirmation_message = f"{action_word} point feature ID {feature.id()} from layer '{layer.name()}'?\n\n"
            if show_coordinate_info:
                confirmation_message += f"Current: ({current_x:.{coordinate_decimals}f}, {current_y:.{coordinate_decimals}f})\n"
                confirmation_message += f"New: ({target_x:.{coordinate_decimals}f}, {target_y:.{coordinate_decimals}f})"
            
            if not self.confirm_action(f"{action_word} Point", confirmation_message):
                return
        
        # Handle edit mode
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "point move")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Create new point geometry
            new_point = QgsPointXY(target_x, target_y)
            new_geometry = QgsGeometry.fromPointXY(new_point)
            
            # Calculate distance moved for success message
            distance_moved = current_point.distance(new_point)
            
            # Get create_copy setting from stored settings
            create_copy = getattr(self, '_create_copy', False)
            new_feature = None
            
            if create_copy:
                # Create a copy of the feature with new geometry
                new_feature = QgsFeature(feature)
                new_feature.setId(-1)  # Let QGIS assign new ID
                new_feature.setGeometry(new_geometry)
                
                # Add the new feature to the layer
                if not layer.addFeature(new_feature):
                    self.show_error("Error", "Failed to create copy of point")
                    return
                
                operation_name = "point copy"
            else:
                # Update original feature geometry
                feature.setGeometry(new_geometry)
                if not layer.updateFeature(feature):
                    self.show_error("Error", "Failed to update point geometry")
                    return
                
                operation_name = "point move"
            
            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, operation_name):
                    return
            
            # Show success message if enabled
            if show_success:
                if create_copy and new_feature:
                    success_message = f"Point feature copy created successfully (ID: {new_feature.id()})"
                else:
                    success_message = f"Point feature ID {feature.id()} moved successfully"
                
                if show_coordinate_info:
                    success_message += f"\n\n"
                    if create_copy:
                        success_message += f"Original: ({current_x:.{coordinate_decimals}f}, {current_y:.{coordinate_decimals}f})\n"
                        success_message += f"Copy: ({target_x:.{coordinate_decimals}f}, {target_y:.{coordinate_decimals}f})\n"
                    else:
                        success_message += f"Previous: ({current_x:.{coordinate_decimals}f}, {current_y:.{coordinate_decimals}f})\n"
                        success_message += f"New: ({target_x:.{coordinate_decimals}f}, {target_y:.{coordinate_decimals}f})\n"
                    success_message += f"Distance: {distance_moved:.{coordinate_decimals}f} map units"
                
                if show_copy_info and create_copy:
                    success_message += f"\n\nOriginal feature (ID: {feature.id()}) remains at original location."
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to move point: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
        
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
move_point_to_coordinates = MovePointToCoordinatesAction()

