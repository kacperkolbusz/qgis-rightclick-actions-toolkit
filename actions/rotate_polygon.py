"""
Rotate Polygon Action for Right-click Utilities and Shortcuts Hub

Rotates the selected polygon feature by a specified angle in degrees.
User inputs the rotation angle, and the polygon is rotated around its centroid.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFormLayout, QDoubleSpinBox
)


class RotatePolygonDialog(QDialog):
    """Dialog for user input of rotation angle."""
    
    def __init__(self, parent=None, default_angle=0.0, polygon_area=None):
        super().__init__(parent)
        self.setWindowTitle("Rotate Polygon")
        self.setModal(True)
        self.resize(350, 150)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Polygon area info
        if polygon_area is not None:
            area_label = QLabel(f"Polygon area: {polygon_area:.2f} square map units")
            area_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", area_label)
        
        # Rotation angle input
        self.angle_spinbox = QDoubleSpinBox()
        self.angle_spinbox.setRange(-360.0, 360.0)
        self.angle_spinbox.setValue(default_angle)
        self.angle_spinbox.setSuffix("°")
        self.angle_spinbox.setDecimals(1)
        form_layout.addRow("Rotation Angle:", self.angle_spinbox)
        
        # Rotation help
        rotation_help = QLabel("Positive = counter-clockwise, Negative = clockwise")
        rotation_help.setStyleSheet("color: gray; font-size: 10px;")
        form_layout.addRow("", rotation_help)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Rotate")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to angle input
        self.angle_spinbox.setFocus()
        self.angle_spinbox.selectAll()
    
    def get_angle(self):
        """Get the input rotation angle."""
        return self.angle_spinbox.value()


class RotatePolygonAction(BaseAction):
    """
    Action to rotate a polygon feature by a specified angle.
    
    This action rotates the selected polygon feature around its centroid by the angle
    specified by the user. Positive angles rotate counter-clockwise, negative angles
    rotate clockwise.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "rotate_polygon"
        self.name = "Rotate Polygon"
        self.category = "Editing"
        self.description = "Rotate the selected polygon feature by a specified angle. User inputs rotation angle in degrees. Polygon is rotated around its centroid. Positive angles rotate counter-clockwise, negative angles rotate clockwise."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygon features
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # ROTATION SETTINGS
            'default_rotation_angle': {
                'type': 'float',
                'default': 0.0,
                'label': 'Default Rotation Angle',
                'description': 'Default rotation angle value shown in the input dialog (degrees)',
                'min': -360.0,
                'max': 360.0,
                'step': 1.0,
            },
            
            # BEHAVIOR SETTINGS
            'confirm_before_rotate': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Rotating',
                'description': 'Show confirmation dialog before rotating the polygon',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when polygon is rotated successfully',
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
                'description': 'Automatically commit changes after rotating (recommended)',
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
                'description': 'Rollback changes if rotation operation fails',
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
        Execute the rotate polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            default_angle = float(self.get_setting('default_rotation_angle', 0.0))
            confirm_before_rotate = bool(self.get_setting('confirm_before_rotate', False))
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
        
        # Show input dialog
        dialog = RotatePolygonDialog(
            None,
            default_angle=default_angle,
            polygon_area=polygon_area
        )
        
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get the user input angle
        rotation_angle = dialog.get_angle()
        
        # Confirm rotation if enabled
        if confirm_before_rotate:
            confirmation_message = f"Rotate polygon feature ID {feature.id()} from layer '{layer.name()}' by {rotation_angle:.1f}°?\n\n"
            if show_polygon_area and polygon_area is not None:
                confirmation_message += f"Polygon area: {polygon_area:.2f} square map units"
            
            if not self.confirm_action("Rotate Polygon", confirmation_message):
                return
        
        # Handle edit mode
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "polygon rotation")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Get centroid as rotation point
            centroid = geometry.centroid().asPoint()
            
            # Create a copy of the geometry for rotation
            rotated_geometry = QgsGeometry(geometry)
            
            # Rotate the geometry around its centroid
            rotated_geometry.rotate(rotation_angle, centroid)
            
            # Update feature geometry
            feature.setGeometry(rotated_geometry)
            if not layer.updateFeature(feature):
                self.show_error("Error", "Failed to update polygon geometry")
                return
            
            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, "polygon rotation"):
                    return
            
            # Show success message if enabled
            if show_success:
                success_message = f"Polygon feature ID {feature.id()} rotated successfully by {rotation_angle:.1f}°"
                
                if show_polygon_area and polygon_area is not None:
                    success_message += f"\n\nPolygon area: {polygon_area:.2f} square map units"
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to rotate polygon: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
        
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
rotate_polygon = RotatePolygonAction()

