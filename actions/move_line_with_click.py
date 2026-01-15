"""
Move Line Action for Right-click Utilities and Shortcuts Hub

Moves the selected line feature to a new location specified by the user.
User clicks on the map to specify the new location for the line.
"""

from .base_action import BaseAction
from qgis.core import QgsPointXY, QgsGeometry, QgsCoordinateTransform, QgsProject, QgsFeature
from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QGroupBox
)


class MoveLineMapTool(QgsMapTool):
    """Custom map tool for moving line features."""
    
    def __init__(self, canvas, parent_action, feature, layer, original_geometry):
        super().__init__(canvas)
        self.canvas = canvas
        self.parent_action = parent_action
        self.feature = feature
        self.layer = layer
        self.original_geometry = original_geometry
        self.original_tool = None
        
        # Store original geometry center for offset calculation
        self.original_center = self.original_geometry.centroid().asPoint()
        
        # Get settings
        self.settings = self.parent_action.get_all_settings()
    
    def canvasPressEvent(self, event):
        """Handle canvas press to place line at new location."""
        if event.button() == 1:  # Left click to place
            # Get current mouse position
            new_point = self.toMapCoordinates(event.pos())
            
            # Calculate offset from original center
            offset_x = new_point.x() - self.original_center.x()
            offset_y = new_point.y() - self.original_center.y()
            
            # Create new geometry
            new_geometry = QgsGeometry(self.original_geometry)
            new_geometry.translate(offset_x, offset_y)
            
            # Move the feature
            self.parent_action._move_feature_to_geometry(
                self.feature, self.layer, new_geometry
            )
            
            # Restore original map tool
            if self.original_tool:
                self.canvas.setMapTool(self.original_tool)
            else:
                self.canvas.unsetMapTool(self)
        
        elif event.button() == 2:  # Right click to cancel
            self._cancel_move()
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key_Escape:
            self._cancel_move()
        else:
            super().keyPressEvent(event)
    
    def _cancel_move(self):
        """Cancel the move operation."""
        # Show cancellation message if enabled
        if self.settings.get('show_cancellation_message', True):
            self.parent_action.show_info("Move Cancelled", "Line move operation was cancelled.")
        
        # Restore original map tool
        if self.original_tool:
            self.canvas.setMapTool(self.original_tool)
        else:
            self.canvas.unsetMapTool(self)


class MoveWithClickDialog(QDialog):
    """Unified dialog for move with click actions - combines confirmation and copy option."""
    
    def __init__(self, parent=None, confirmation_message="", ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Move Feature")
        self.setModal(True)
        self.resize(400, 200)
        
        layout = QVBoxLayout()
        
        # Confirmation message
        if confirmation_message:
            message_label = QLabel(confirmation_message)
            message_label.setWordWrap(True)
            layout.addWidget(message_label)
        
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
        self.ok_button = QPushButton("Continue")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
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


class MoveLineAction(BaseAction):
    """Action to move line features to a new location."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "move_line_with_click"
        self.name = "Move Line with Click"
        self.category = "Editing"
        self.description = "Move the selected line feature to a new location. Click on the map to specify where to move the line. Right-click or press Escape to cancel."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # BEHAVIOR SETTINGS - User experience options
            'confirm_move': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Moving',
                'description': 'Show confirmation dialog before moving the line',
            },
            'confirmation_message_template': {
                'type': 'str',
                'default': 'Move line feature ID {feature_id} from layer \'{layer_name}\'?',
                'label': 'Confirmation Message Template',
                'description': 'Template for confirmation message. Available variables: {feature_id}, {layer_name}, {geometry_type}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when line is moved successfully',
            },
            'success_message_template': {
                'type': 'str',
                'default': 'Line feature ID {feature_id} moved successfully',
                'label': 'Success Message Template',
                'description': 'Template for success message. Available variables: {feature_id}, {layer_name}, {distance_moved}',
            },
            'show_cancellation_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Cancellation Message',
                'description': 'Display a message when move operation is cancelled',
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
            'show_line_length_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Line Length Info',
                'description': 'Display line length information in confirmation and success messages',
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
            
            # DIALOG SETTINGS
            'use_unified_dialog': {
                'type': 'bool',
                'default': True,
                'label': 'Use Unified Dialog',
                'description': 'Combine confirmation and copy options in one dialog. If disabled, shows separate popups.',
            },
        }
    
    def execute(self, context):
        """
        Execute the move line action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            confirm_move = bool(self.get_setting('confirm_move', False))
            confirmation_template = str(self.get_setting('confirmation_message_template', 'Move line feature ID {feature_id} from layer \'{layer_name}\'?'))
            show_success = bool(self.get_setting('show_success_message', True))
            success_template = str(self.get_setting('success_message_template', 'Line feature ID {feature_id} moved successfully'))
            show_cancellation = bool(self.get_setting('show_cancellation_message', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            show_line_length = bool(self.get_setting('show_line_length_info', False))
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
            self.show_error("Error", "No line features found at this location")
            return
        
        if not canvas:
            self.show_error("Error", "Map canvas not available")
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
        
        # Calculate line length if requested
        line_length = None
        if show_line_length:
            try:
                line_length = geometry.length()
            except Exception:
                pass
        
        # Prepare confirmation message if needed
        confirmation_message = ""
        if confirm_move:
            confirmation_message = self.format_message_template(
                confirmation_template,
                feature_id=feature.id(),
                layer_name=layer.name(),
                geometry_type=detected_feature.geometry_type
            )
            
            # Add line length info if requested
            if show_line_length and line_length is not None:
                confirmation_message += f"\n\nLine length: {line_length:.2f} map units"
        
        # Determine copy options
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
        
        # Use unified dialog or separate popups
        create_copy = False
        if use_unified_dialog and (confirm_move or show_copy_option):
            # Combine confirmation and copy in one dialog
            dialog = MoveWithClickDialog(
                None,
                confirmation_message=confirmation_message,
                ask_copy=show_copy_option,
                default_copy=default_copy
            )
            
            if dialog.exec_() != QDialog.Accepted:
                return  # User cancelled
            
            create_copy = dialog.get_create_copy() if show_copy_option else (default_copy_choice == 'copy')
        else:
            # Use separate popups (legacy behavior)
            if confirm_move:
                if not self.confirm_action("Move Line", confirmation_message):
                    return
            
            if ask_create_copy:
                if default_copy_choice == 'ask':
                    copy_dialog = CreateCopyDialog(None, "line")
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
        
        # Store settings for the map tool
        self._current_settings = {
            'show_success_message': show_success,
            'success_message_template': success_template,
            'show_cancellation_message': show_cancellation,
            'auto_commit_changes': auto_commit,
            'handle_edit_mode_automatically': handle_edit_mode,
            'rollback_on_error': rollback_on_error,
            'show_line_length_info': show_line_length,
            'show_copy_info': show_copy_info,
            'create_copy': create_copy,
            'line_length': line_length,
            'feature_id': feature.id(),
            'layer_name': layer.name(),
            'geometry_type': detected_feature.geometry_type
        }
        
        # Create and activate the move tool
        move_tool = MoveLineMapTool(canvas, self, feature, layer, geometry)
        move_tool.original_tool = canvas.mapTool()
        canvas.setMapTool(move_tool)
    
    def _move_feature_to_geometry(self, feature, layer, new_geometry):
        """
        Move the feature to the new geometry.
        
        Args:
            feature: The feature to move
            layer: The layer containing the feature
            new_geometry: The new geometry for the feature
        """
        settings = getattr(self, '_current_settings', {})
        
        # Handle edit mode if enabled
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if settings.get('handle_edit_mode_automatically', True):
            edit_result = self.handle_edit_mode(layer, "line move")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Calculate distance moved for success message
            original_geometry = feature.geometry()
            original_center = original_geometry.centroid().asPoint()
            new_center = new_geometry.centroid().asPoint()
            distance_moved = original_center.distance(new_center)
            
            create_copy = settings.get('create_copy', False)
            new_feature = None
            
            if create_copy:
                # Create a copy of the feature with new geometry
                new_feature = QgsFeature(feature)
                new_feature.setId(-1)  # Let QGIS assign new ID
                new_feature.setGeometry(new_geometry)
                
                # Add the new feature to the layer
                if not layer.addFeature(new_feature):
                    self.show_error("Error", "Failed to create copy of line")
                    return
                
                operation_name = "line copy"
            else:
                # Update original feature geometry
                feature.setGeometry(new_geometry)
                if not layer.updateFeature(feature):
                    self.show_error("Error", "Failed to update line geometry")
                    return
                
                operation_name = "line move"
            
            # Commit changes if enabled
            if settings.get('auto_commit_changes', True) and settings.get('handle_edit_mode_automatically', True):
                if not self.commit_changes(layer, operation_name):
                    return
            
            # Show success message if enabled
            if settings.get('show_success_message', True):
                if create_copy and new_feature:
                    success_message = f"Line feature copy created successfully (ID: {new_feature.id()})"
                else:
                    success_message = self.format_message_template(
                        settings.get('success_message_template', 'Line feature ID {feature_id} moved successfully'),
                        feature_id=settings.get('feature_id', feature.id()),
                        layer_name=settings.get('layer_name', layer.name()),
                        distance_moved=f"{distance_moved:.2f} map units"
                    )
                
                # Add line length info if requested
                if settings.get('show_line_length_info', False) and settings.get('line_length') is not None:
                    success_message += f"\n\nLine length: {settings.get('line_length'):.2f} map units"
                
                if settings.get('show_copy_info', True) and create_copy:
                    success_message += f"\n\nOriginal feature (ID: {settings.get('feature_id', feature.id())}) remains at original location."
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to move line feature: {str(e)}")
            if settings.get('rollback_on_error', True) and settings.get('handle_edit_mode_automatically', True):
                self.rollback_changes(layer)
            
        finally:
            # Exit edit mode if we entered it
            if settings.get('handle_edit_mode_automatically', True):
                self.exit_edit_mode(layer, edit_mode_entered)
    
    def format_message_template(self, template, **kwargs):
        """
        Format a message template with provided variables.
        
        Args:
            template (str): Message template with {variable} placeholders
            **kwargs: Variables to substitute in the template
            
        Returns:
            str: Formatted message
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            # If a variable is missing, return the template as-is
            return template
    
# REQUIRED: Create global instance for automatic discovery
move_line_with_click_action = MoveLineAction()
