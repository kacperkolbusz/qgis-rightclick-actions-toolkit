"""
Scale Line Action for Right-click Utilities and Shortcuts Hub

Scales the selected line feature by a specified scale factor.
User inputs the scale factor, and the line is scaled around its centroid.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFormLayout, QDoubleSpinBox
)


class ScaleLineDialog(QDialog):
    """Dialog for user input of scale factor."""
    
    def __init__(self, parent=None, default_scale=1.0, line_length=None):
        super().__init__(parent)
        self.setWindowTitle("Scale Line")
        self.setModal(True)
        self.resize(350, 150)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Line length info
        if line_length is not None:
            length_label = QLabel(f"Line length: {line_length:.2f} map units")
            length_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", length_label)
        
        # Scale factor input
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(0.01, 100.0)
        self.scale_spinbox.setValue(default_scale)
        self.scale_spinbox.setSuffix("x")
        self.scale_spinbox.setDecimals(2)
        form_layout.addRow("Scale Factor:", self.scale_spinbox)
        
        # Scale help
        scale_help = QLabel("1.0 = original size, >1.0 = larger, <1.0 = smaller")
        scale_help.setStyleSheet("color: gray; font-size: 10px;")
        form_layout.addRow("", scale_help)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Scale")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to scale input
        self.scale_spinbox.setFocus()
        self.scale_spinbox.selectAll()
    
    def get_scale(self):
        """Get the input scale factor."""
        return self.scale_spinbox.value()


class ScaleLineAction(BaseAction):
    """
    Action to scale a line feature by a specified scale factor.
    
    This action scales the selected line feature around its centroid by the scale
    factor specified by the user. Scale factor > 1.0 makes the line larger,
    scale factor < 1.0 makes it smaller.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "scale_line"
        self.name = "Scale Line"
        self.category = "Editing"
        self.description = "Scale the selected line feature by a specified scale factor. User inputs scale factor (1.0 = original size, >1.0 = larger, <1.0 = smaller). Line is scaled around its centroid."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # SCALING SETTINGS
            'default_scale_factor': {
                'type': 'float',
                'default': 1.0,
                'label': 'Default Scale Factor',
                'description': 'Default scale factor value shown in the input dialog (1.0 = original size)',
                'min': 0.01,
                'max': 100.0,
                'step': 0.1,
            },
            
            # BEHAVIOR SETTINGS
            'confirm_before_scale': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Scaling',
                'description': 'Show confirmation dialog before scaling the line',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when line is scaled successfully',
            },
            'show_line_length_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Line Length Info',
                'description': 'Display line length information in the input dialog and success messages',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after scaling (recommended)',
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
                'description': 'Rollback changes if scaling operation fails',
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
        Execute the scale line action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            default_scale = float(self.get_setting('default_scale_factor', 1.0))
            confirm_before_scale = bool(self.get_setting('confirm_before_scale', False))
            show_success = bool(self.get_setting('show_success_message', True))
            show_line_length = bool(self.get_setting('show_line_length_info', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
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
        
        # Validate that this is a line feature
        if geometry.type() != QgsWkbTypes.LineGeometry:
            self.show_error("Error", "This action only works with line features")
            return
        
        # Calculate line length if requested
        line_length = None
        if show_line_length:
            try:
                line_length = geometry.length()
            except Exception:
                pass
        
        # Show input dialog
        dialog = ScaleLineDialog(
            None,
            default_scale=default_scale,
            line_length=line_length
        )
        
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get the user input scale factor
        scale_factor = dialog.get_scale()
        
        # Confirm scaling if enabled
        if confirm_before_scale:
            confirmation_message = f"Scale line feature ID {feature.id()} from layer '{layer.name()}' by {scale_factor:.2f}x?\n\n"
            if show_line_length and line_length is not None:
                new_length = line_length * scale_factor
                confirmation_message += f"Current length: {line_length:.2f} map units\n"
                confirmation_message += f"New length: {new_length:.2f} map units"
            
            if not self.confirm_action("Scale Line", confirmation_message):
                return
        
        # Handle edit mode
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "line scaling")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Get centroid as scaling center point
            centroid = geometry.centroid().asPoint()
            centroid_x = centroid.x()
            centroid_y = centroid.y()
            
            # Create a copy of the geometry for scaling
            scaled_geometry = QgsGeometry(geometry)
            
            # Scale the geometry around its centroid by transforming each vertex
            # Try single line first, then multiline
            try:
                # Try as single line first
                vertices = geometry.asPolyline()
                scaled_vertices = []
                
                for vertex in vertices:
                    # Calculate offset from centroid
                    offset_x = vertex.x() - centroid_x
                    offset_y = vertex.y() - centroid_y
                    
                    # Scale the offset
                    scaled_offset_x = offset_x * scale_factor
                    scaled_offset_y = offset_y * scale_factor
                    
                    # Calculate new vertex position
                    new_x = centroid_x + scaled_offset_x
                    new_y = centroid_y + scaled_offset_y
                    scaled_vertices.append(QgsPointXY(new_x, new_y))
                
                # Create new geometry from scaled vertices
                scaled_geometry = QgsGeometry.fromPolylineXY(scaled_vertices)
            except (TypeError, AttributeError):
                # Handle multiline geometry
                try:
                    multi_polyline = geometry.asMultiPolyline()
                    scaled_multi_polyline = []
                    
                    for polyline in multi_polyline:
                        scaled_vertices = []
                        for vertex in polyline:
                            # Calculate offset from centroid
                            offset_x = vertex.x() - centroid_x
                            offset_y = vertex.y() - centroid_y
                            
                            # Scale the offset
                            scaled_offset_x = offset_x * scale_factor
                            scaled_offset_y = offset_y * scale_factor
                            
                            # Calculate new vertex position
                            new_x = centroid_x + scaled_offset_x
                            new_y = centroid_y + scaled_offset_y
                            scaled_vertices.append(QgsPointXY(new_x, new_y))
                        
                        scaled_multi_polyline.append(scaled_vertices)
                    
                    # Create new geometry from scaled vertices
                    scaled_geometry = QgsGeometry.fromMultiPolylineXY(scaled_multi_polyline)
                except (TypeError, AttributeError):
                    self.show_error("Error", "Unsupported line geometry type")
                    return
            
            # Update feature geometry
            feature.setGeometry(scaled_geometry)
            if not layer.updateFeature(feature):
                self.show_error("Error", "Failed to update line geometry")
                return
            
            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, "line scaling"):
                    return
            
            # Show success message if enabled
            if show_success:
                success_message = f"Line feature ID {feature.id()} scaled successfully by {scale_factor:.2f}x"
                
                if show_line_length and line_length is not None:
                    new_length = line_length * scale_factor
                    success_message += f"\n\nOriginal length: {line_length:.2f} map units"
                    success_message += f"\nNew length: {new_length:.2f} map units"
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to scale line: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
        
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
scale_line = ScaleLineAction()

