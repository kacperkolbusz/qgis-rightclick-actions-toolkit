"""
Scale Line Layer Action for Right-click Utilities and Shortcuts Hub

Scales all line features in the selected line layer by a specified scale factor.
Each line is scaled around its own centroid.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes, QgsFeature
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFormLayout, QDoubleSpinBox, QGroupBox, QRadioButton, QCheckBox
)


class ScaleLineLayerDialog(QDialog):
    """Dialog for user input of scale factor and scaling mode."""
    
    def __init__(self, parent=None, default_scale=1.0, feature_count=None, default_mode='individual', default_scale_objects=True):
        super().__init__(parent)
        self.setWindowTitle("Scale Line Layer")
        self.setModal(True)
        self.resize(400, 250)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Feature count info
        if feature_count is not None:
            count_label = QLabel(f"Features in layer: {feature_count}")
            count_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", count_label)
        
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
        
        # Scaling mode selection
        mode_group = QGroupBox("Scaling Mode")
        mode_layout = QVBoxLayout()
        
        self.individual_radio = QRadioButton("Scale individual objects")
        self.individual_radio.setToolTip("Each line scales around its own centroid")
        self.layer_radio = QRadioButton("Scale entire layer")
        self.layer_radio.setToolTip("Scale the layer as a whole around layer centroid (distances between objects are scaled)")
        
        if default_mode == 'individual':
            self.individual_radio.setChecked(True)
        else:
            self.layer_radio.setChecked(True)
        
        mode_layout.addWidget(self.individual_radio)
        mode_layout.addWidget(self.layer_radio)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # Scale object sizes option (only for layer scaling)
        self.scale_objects_checkbox = QCheckBox("Also scale object sizes")
        self.scale_objects_checkbox.setToolTip("When scaling the layer, also scale each line's geometry around its own centroid")
        self.scale_objects_checkbox.setChecked(default_scale_objects)
        self.scale_objects_checkbox.setEnabled(False)  # Disabled by default, enabled when layer mode is selected
        
        # Connect radio buttons to enable/disable scale objects option
        def update_scale_objects_enabled():
            self.scale_objects_checkbox.setEnabled(self.layer_radio.isChecked())
        
        self.individual_radio.toggled.connect(lambda checked: update_scale_objects_enabled())
        self.layer_radio.toggled.connect(lambda checked: update_scale_objects_enabled())
        
        mode_layout.addWidget(self.scale_objects_checkbox)
        
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
    
    def get_values(self):
        """Get the input values."""
        return {
            'scale_factor': self.scale_spinbox.value(),
            'mode': 'individual' if self.individual_radio.isChecked() else 'layer',
            'scale_objects': self.scale_objects_checkbox.isChecked() if self.layer_radio.isChecked() else False
        }


class ScaleLineLayerAction(BaseAction):
    """
    Action to scale all line features in a line layer by a specified scale factor.
    
    This action scales all line features in the selected layer around their own
    centroid by the scale factor specified by the user. Scale factor > 1.0 makes
    lines larger, scale factor < 1.0 makes them smaller.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "scale_line_layer"
        self.name = "Scale Line Layer"
        self.category = "Editing"
        self.description = "Scale all line features in the selected line layer by a specified scale factor. Each line is scaled around its own centroid. User inputs scale factor (1.0 = original size, >1.0 = larger, <1.0 = smaller)."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with line layers
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
            'default_scaling_mode': {
                'type': 'choice',
                'default': 'individual',
                'label': 'Default Scaling Mode',
                'description': 'Default scaling mode: "individual" scales each object around its own centroid, "layer" scales the entire layer around layer centroid',
                'options': ['individual', 'layer'],
            },
            'default_scale_objects': {
                'type': 'bool',
                'default': True,
                'label': 'Default: Scale Object Sizes',
                'description': 'When scaling the entire layer, also scale each object\'s geometry by default',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_before_scale': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Scaling',
                'description': 'Show confirmation dialog before scaling all lines in the layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when layer is scaled successfully',
            },
            'show_feature_count': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature Count',
                'description': 'Display feature count information in dialogs and messages',
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
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip features with invalid or empty geometries',
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
    
    def _scale_line_geometry(self, geometry, scale_factor, center_point=None):
        """
        Scale a line geometry around a center point.
        
        Args:
            geometry (QgsGeometry): Line geometry to scale
            scale_factor (float): Scale factor to apply
            center_point (QgsPointXY, optional): Center point for scaling. If None, uses geometry's centroid.
            
        Returns:
            QgsGeometry: Scaled geometry, or None if scaling failed
        """
        try:
            # Get center point for scaling
            if center_point is None:
                center_point = geometry.centroid().asPoint()
            
            centroid_x = center_point.x()
            centroid_y = center_point.y()
            
            # Try single line first
            try:
                vertices = geometry.asPolyline()
                scaled_vertices = []
                
                for vertex in vertices:
                    # Calculate offset from center point
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
                return QgsGeometry.fromPolylineXY(scaled_vertices)
            except (TypeError, AttributeError):
                # Handle multiline geometry
                try:
                    multi_polyline = geometry.asMultiPolyline()
                    scaled_multi_polyline = []
                    
                    for polyline in multi_polyline:
                        scaled_vertices = []
                        for vertex in polyline:
                            # Calculate offset from center point
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
                    return QgsGeometry.fromMultiPolylineXY(scaled_multi_polyline)
                except (TypeError, AttributeError):
                    return None
        except Exception:
            return None
    
    def execute(self, context):
        """
        Execute the scale line layer action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            default_scale = float(self.get_setting('default_scale_factor', 1.0))
            default_mode = str(self.get_setting('default_scaling_mode', 'individual'))
            default_scale_objects = bool(self.get_setting('default_scale_objects', True))
            confirm_before_scale = bool(self.get_setting('confirm_before_scale', True))
            show_success = bool(self.get_setting('show_success_message', True))
            show_feature_count = bool(self.get_setting('show_feature_count', True))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            skip_invalid = bool(self.get_setting('skip_invalid_geometries', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
            return
        
        # Get the layer from the first detected feature
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Get feature count
        feature_count = layer.featureCount()
        
        if feature_count == 0:
            self.show_error("Error", "Layer contains no features")
            return
        
        # Show input dialog
        dialog = ScaleLineLayerDialog(
            None,
            default_scale=default_scale,
            feature_count=feature_count if show_feature_count else None,
            default_mode=default_mode,
            default_scale_objects=default_scale_objects
        )
        
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get the user input values
        values = dialog.get_values()
        scale_factor = values['scale_factor']
        scaling_mode = values['mode']
        scale_objects = values['scale_objects']
        
        # Calculate layer centroid if scaling entire layer
        layer_center = None
        if scaling_mode == 'layer':
            try:
                layer_extent = layer.extent()
                if not layer_extent.isEmpty():
                    layer_center = layer_extent.center()
                else:
                    # Fallback: calculate from features
                    features = list(layer.getFeatures())
                    if features:
                        total_x = 0.0
                        total_y = 0.0
                        count = 0
                        for feature in features:
                            geometry = feature.geometry()
                            if geometry and not geometry.isEmpty():
                                centroid = geometry.centroid().asPoint()
                                total_x += centroid.x()
                                total_y += centroid.y()
                                count += 1
                        if count > 0:
                            layer_center = QgsPointXY(total_x / count, total_y / count)
            except Exception:
                pass
            
            if layer_center is None:
                self.show_error("Error", "Could not calculate layer center point")
                return
        
        # Confirm scaling if enabled
        if confirm_before_scale:
            if scaling_mode == 'individual':
                confirmation_message = f"Scale all {feature_count} line features in layer '{layer.name()}' by {scale_factor:.2f}x?\n\n"
                confirmation_message += "Each line will be scaled around its own centroid."
            else:
                confirmation_message = f"Scale entire layer '{layer.name()}' ({feature_count} features) by {scale_factor:.2f}x?\n\n"
                confirmation_message += "Distances between objects will be scaled around the layer centroid."
                if scale_objects:
                    confirmation_message += "\nObject sizes will also be scaled."
                else:
                    confirmation_message += "\nObject sizes will remain unchanged."
            
            if not self.confirm_action("Scale Line Layer", confirmation_message):
                return
        
        # Handle edit mode
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "line layer scaling")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Process all features in the layer
            success_count = 0
            error_count = 0
            
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                
                if not geometry or geometry.isEmpty():
                    if skip_invalid:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature {feature.id()} has invalid geometry")
                        if rollback_on_error and handle_edit_mode:
                            self.rollback_changes(layer)
                        return
                
                # Scale the geometry based on mode
                if scaling_mode == 'individual':
                    # Scale around feature's own centroid
                    scaled_geometry = self._scale_line_geometry(geometry, scale_factor)
                else:
                    # Scale around layer center
                    scaled_geometry = self._scale_line_geometry(geometry, scale_factor, layer_center)
                    
                    # If also scaling object sizes, scale again around feature's own centroid
                    if scale_objects:
                        scaled_geometry = self._scale_line_geometry(scaled_geometry, scale_factor)
                
                if not scaled_geometry:
                    if skip_invalid:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Failed to scale feature {feature.id()}")
                        if rollback_on_error and handle_edit_mode:
                            self.rollback_changes(layer)
                        return
                
                # Update feature geometry
                feature.setGeometry(scaled_geometry)
                if not layer.updateFeature(feature):
                    if skip_invalid:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Failed to update feature {feature.id()}")
                        if rollback_on_error and handle_edit_mode:
                            self.rollback_changes(layer)
                        return
                
                success_count += 1
            
            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, "line layer scaling"):
                    return
            
            # Show success message if enabled
            if show_success:
                success_message = f"Line layer scaled successfully by {scale_factor:.2f}x"
                
                if show_feature_count:
                    success_message += f"\n\nFeatures processed: {success_count}"
                    if error_count > 0:
                        success_message += f"\nFeatures skipped: {error_count}"
                
                self.show_info("Success", success_message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to scale line layer: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
        
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
scale_line_layer = ScaleLineLayerAction()

