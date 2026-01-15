"""
Move Polygon by Distance and Direction Action for Right-click Utilities and Shortcuts Hub

Moves the selected polygon feature by a specified distance and direction.
User inputs distance in map units and direction in degrees.
"""

from .base_action import BaseAction
from qgis.core import QgsPointXY, QgsGeometry, QgsCoordinateTransform, QgsProject, QgsFeature
from qgis.PyQt.QtWidgets import (
    QInputDialog, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFormLayout, QDoubleSpinBox, QCheckBox, QGroupBox
)
from qgis.PyQt.QtCore import Qt
import math


class MoveByDistanceDirectionDialog(QDialog):
    """Unified dialog for move by distance and direction with copy option."""
    
    def __init__(self, parent=None, default_distance=100.0, default_direction=0.0, 
                 polygon_area=None, ask_copy=True, default_copy=False):
        super().__init__(parent)
        self.setWindowTitle("Move by Distance & Direction")
        self.setModal(True)
        self.resize(400, 250)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Polygon area info
        if polygon_area is not None:
            area_label = QLabel(f"Polygon area: {polygon_area:.2f} square map units")
            area_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", area_label)
        
        # Distance input
        self.distance_spinbox = QDoubleSpinBox()
        self.distance_spinbox.setRange(0.0, 1000000.0)
        self.distance_spinbox.setValue(default_distance)
        self.distance_spinbox.setSuffix(" units")
        self.distance_spinbox.setDecimals(2)
        form_layout.addRow("Distance:", self.distance_spinbox)
        
        # Direction input
        self.direction_spinbox = QDoubleSpinBox()
        self.direction_spinbox.setRange(0.0, 360.0)
        self.direction_spinbox.setValue(default_direction)
        self.direction_spinbox.setSuffix("°")
        self.direction_spinbox.setDecimals(1)
        form_layout.addRow("Direction:", self.direction_spinbox)
        
        # Direction help
        direction_help = QLabel("0° = North, 90° = East, 180° = South, 270° = West")
        direction_help.setStyleSheet("color: gray; font-size: 10px;")
        form_layout.addRow("", direction_help)
        
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
        self.ok_button = QPushButton("Move")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to distance input
        self.distance_spinbox.setFocus()
        self.distance_spinbox.selectAll()
    
    def get_values(self):
        """Get the input values."""
        return {
            'distance': self.distance_spinbox.value(),
            'direction': self.direction_spinbox.value(),
            'create_copy': self.create_copy_checkbox.isChecked() if hasattr(self, 'create_copy_checkbox') else False
        }


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


class MovePolygonByDistanceDirectionAction(BaseAction):
    """Action to move polygon features by distance and direction."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "move_polygon_by_distance_direction"
        self.name = "Move Polygon by Distance & Direction"
        self.category = "Editing"
        self.description = "Move the selected polygon feature by a specified distance and direction. User inputs distance in map units and direction in degrees (0° = North, 90° = East, 180° = South, 270° = West)."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygon features
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # BEHAVIOR SETTINGS - User experience options
            'confirm_move': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Moving',
                'description': 'Show confirmation dialog before moving the polygon',
            },
            'confirmation_message_template': {
                'type': 'str',
                'default': 'Move polygon feature ID {feature_id} from layer \'{layer_name}\' by {distance} units at {direction}°?',
                'label': 'Confirmation Message Template',
                'description': 'Template for confirmation message. Available variables: {feature_id}, {layer_name}, {distance}, {direction}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when polygon is moved successfully',
            },
            'success_message_template': {
                'type': 'str',
                'default': 'Polygon feature ID {feature_id} moved successfully by {distance} units at {direction}°',
                'label': 'Success Message Template',
                'description': 'Template for success message. Available variables: {feature_id}, {layer_name}, {distance}, {direction}',
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
            'show_polygon_area_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Polygon Area Info',
                'description': 'Display polygon area information in confirmation and success messages',
            },
            'default_distance': {
                'type': 'float',
                'default': 100.0,
                'label': 'Default Distance',
                'description': 'Default distance value for the input dialog',
                'min': 0.0,
                'max': 1000000.0,
                'step': 1.0,
            },
            'default_direction': {
                'type': 'float',
                'default': 0.0,
                'label': 'Default Direction',
                'description': 'Default direction value for the input dialog (degrees)',
                'min': 0.0,
                'max': 360.0,
                'step': 1.0,
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
                'description': 'Use a single dialog for all inputs (distance, direction, copy). If disabled, shows separate popups for each input.',
            },
        }
    
    def execute(self, context):
        """
        Execute the move polygon by distance and direction action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            confirm_move = bool(self.get_setting('confirm_move', True))
            confirmation_template = str(self.get_setting('confirmation_message_template', 'Move polygon feature ID {feature_id} from layer \'{layer_name}\' by {distance} units at {direction}°?'))
            show_success = bool(self.get_setting('show_success_message', True))
            success_template = str(self.get_setting('success_message_template', 'Polygon feature ID {feature_id} moved successfully by {distance} units at {direction}°'))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            show_polygon_area = bool(self.get_setting('show_polygon_area_info', True))
            default_distance = float(self.get_setting('default_distance', 100.0))
            default_direction = float(self.get_setting('default_direction', 0.0))
            ask_create_copy = bool(self.get_setting('ask_create_copy', True))
            default_copy_choice = str(self.get_setting('default_copy_choice', 'ask'))
            show_copy_info = bool(self.get_setting('show_copy_info_in_messages', True))
            use_unified_dialog = bool(self.get_setting('use_unified_dialog', True))
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
            
            dialog = MoveByDistanceDirectionDialog(
                None,
                default_distance=default_distance,
                default_direction=default_direction,
                polygon_area=polygon_area,
                ask_copy=show_copy_option,
                default_copy=default_copy
            )
            
            if dialog.exec_() != QDialog.Accepted:
                return  # User cancelled
            
            values = dialog.get_values()
            distance = values['distance']
            direction = values['direction']
            create_copy = values['create_copy'] if show_copy_option else (default_copy_choice == 'copy')
        else:
            # Use separate popups (legacy behavior)
            distance, ok1 = QInputDialog.getDouble(
                None, 
                "Move Polygon by Distance & Direction", 
                f"Enter distance to move (map units):\nPolygon area: {polygon_area:.2f} square map units" if polygon_area else "Enter distance to move (map units):",
                default_distance, 
                0.0, 
                1000000.0, 
                2
            )
            
            if not ok1:
                return  # User cancelled
            
            direction, ok2 = QInputDialog.getDouble(
                None, 
                "Move Polygon by Distance & Direction", 
                "Enter direction in degrees (0° = North, 90° = East, 180° = South, 270° = West):",
                default_direction, 
                0.0, 
                360.0, 
            1
            )
            
            if not ok2:
                return  # User cancelled
            
            create_copy = False
        
        # Calculate offset
        try:
            # Convert direction from degrees to radians
            # QGIS uses mathematical convention: 0° = East, 90° = North
            # User expects: 0° = North, 90° = East
            # So we need to convert: math_angle = 90° - user_angle
            direction_rad = math.radians(90.0 - direction)
            
            # Calculate offset
            offset_x = distance * math.cos(direction_rad)
            offset_y = distance * math.sin(direction_rad)
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate offset: {str(e)}")
            return
        
        # Ask for user confirmation before moving if enabled
        if confirm_move:
            # Prepare confirmation message
            confirmation_message = self.format_message_template(
                confirmation_template,
                feature_id=feature.id(),
                layer_name=layer.name(),
                distance=f"{distance:.2f}",
                direction=f"{direction:.1f}"
            )
            
            # Add polygon area info if requested
            if show_polygon_area and polygon_area is not None:
                confirmation_message += f"\n\nPolygon area: {polygon_area:.2f} square map units"
            
            if not self.confirm_action("Move Polygon by Distance & Direction", confirmation_message):
                return
        
        # Handle copy choice if not already set by unified dialog
        if not use_unified_dialog:
            if ask_create_copy:
                if default_copy_choice == 'ask':
                    copy_dialog = CreateCopyDialog(None, "polygon")
                    copy_choice = copy_dialog.get_choice()
                    if copy_choice is None:
                        return  # User cancelled
                    create_copy = (copy_choice == 1)
                elif default_copy_choice == 'copy':
                    create_copy = True
                else:  # default_copy_choice == 'move'
                    create_copy = False
            else:
                # If not asking, use default choice
                create_copy = (default_copy_choice == 'copy')
        
        # Store settings for the move operation
        self._current_settings = {
            'show_success_message': show_success,
            'success_message_template': success_template,
            'auto_commit_changes': auto_commit,
            'handle_edit_mode_automatically': handle_edit_mode,
            'rollback_on_error': rollback_on_error,
            'show_polygon_area_info': show_polygon_area,
            'show_copy_info': show_copy_info,
            'create_copy': create_copy,
            'polygon_area': polygon_area,
            'feature_id': feature.id(),
            'layer_name': layer.name(),
            'distance': f"{distance:.2f}",
            'direction': f"{direction:.1f}"
        }
        
        # Move the feature
        self._move_feature_by_offset(feature, layer, geometry, offset_x, offset_y)
    
    def _move_feature_by_offset(self, feature, layer, original_geometry, offset_x, offset_y):
        """
        Move the feature by the specified offset.
        
        Args:
            feature: The feature to move
            layer: The layer containing the feature
            original_geometry: The original geometry
            offset_x: X offset in map units
            offset_y: Y offset in map units
        """
        settings = getattr(self, '_current_settings', {})
        
        # Handle edit mode if enabled
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if settings.get('handle_edit_mode_automatically', True):
            edit_result = self.handle_edit_mode(layer, "polygon move")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Create new geometry by translating the original
            new_geometry = QgsGeometry(original_geometry)
            new_geometry.translate(offset_x, offset_y)
            
            create_copy = settings.get('create_copy', False)
            new_feature = None
            
            if create_copy:
                # Create a copy of the feature with new geometry
                new_feature = QgsFeature(feature)
                new_feature.setId(-1)  # Let QGIS assign new ID
                new_feature.setGeometry(new_geometry)
                
                # Add the new feature to the layer
                if not layer.addFeature(new_feature):
                    self.show_error("Error", "Failed to create copy of polygon")
                    return
                
                operation_name = "polygon copy"
            else:
                # Update original feature geometry
                feature.setGeometry(new_geometry)
                if not layer.updateFeature(feature):
                    self.show_error("Error", "Failed to update polygon geometry")
                    return
                
                operation_name = "polygon move"
            
            # Commit changes if enabled
            if settings.get('auto_commit_changes', True) and settings.get('handle_edit_mode_automatically', True):
                if not self.commit_changes(layer, operation_name):
                    return
            
            # Show success message if enabled
            if settings.get('show_success_message', True):
                if create_copy and new_feature:
                    success_message = f"Polygon feature copy created successfully (ID: {new_feature.id()})"
                    success_message += f"\n\nMoved by {settings.get('distance', '0.00')} units at {settings.get('direction', '0.0')}°"
                else:
                    success_message = self.format_message_template(
                        settings.get('success_message_template', 'Polygon feature ID {feature_id} moved successfully by {distance} units at {direction}°'),
                        feature_id=settings.get('feature_id', feature.id()),
                        layer_name=settings.get('layer_name', layer.name()),
                        distance=settings.get('distance', '0.00'),
                        direction=settings.get('direction', '0.0')
                    )
                
                # Add polygon area info if requested
                if settings.get('show_polygon_area_info', False) and settings.get('polygon_area') is not None:
                    success_message += f"\n\nPolygon area: {settings.get('polygon_area'):.2f} square map units"
                
                if settings.get('show_copy_info', True) and create_copy:
                    success_message += f"\n\nOriginal feature (ID: {settings.get('feature_id', feature.id())}) remains at original location."
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to move polygon feature: {str(e)}")
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
move_polygon_by_distance_direction_action = MovePolygonByDistanceDirectionAction()
