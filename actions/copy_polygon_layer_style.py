"""
Copy Polygon Layer Style Action for Right-click Utilities and Shortcuts Hub

Allows copying the style (symbology, labeling, effects) from the clicked polygon layer
to other polygon layers in the project. Shows a dialog where users can select which
polygon layers to copy the style to.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsWkbTypes, QgsVectorLayer
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                QPushButton, QCheckBox, QScrollArea, QWidget,
                                QMessageBox)
from qgis.PyQt.QtCore import Qt


class CopyPolygonLayerStyleDialog(QDialog):
    """Dialog for selecting target polygon layers to copy style to."""
    
    def __init__(self, source_layer, target_layers, parent=None):
        """
        Initialize the dialog.
        
        Args:
            source_layer (QgsVectorLayer): Source layer to copy style from
            target_layers (list): List of target layers to copy style to
            parent: Parent widget
        """
        super().__init__(parent)
        self.source_layer = source_layer
        self.target_layers = target_layers
        self.selected_layers = []
        
        self.setWindowTitle("Copy Polygon Layer Style")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Title label
        title_label = QLabel(f"Copy style from: <b>{self.source_layer.name()}</b>")
        layout.addWidget(title_label)
        
        # Instructions
        instructions = QLabel("Select polygon layers to copy the style to:")
        layout.addWidget(instructions)
        
        # Scrollable area with checkboxes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        self.checkboxes = {}
        for layer in self.target_layers:
            checkbox = QCheckBox(layer.name())
            checkbox.setChecked(False)
            self.checkboxes[layer.id()] = (checkbox, layer)
            scroll_layout.addWidget(checkbox)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(deselect_all_btn)
        
        button_layout.addStretch()
        
        ok_btn = QPushButton("Copy Style")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def select_all(self):
        """Select all checkboxes."""
        for checkbox, _ in self.checkboxes.values():
            checkbox.setChecked(True)
    
    def deselect_all(self):
        """Deselect all checkboxes."""
        for checkbox, _ in self.checkboxes.values():
            checkbox.setChecked(False)
    
    def get_selected_layers(self):
        """
        Get the list of selected target layers.
        
        Returns:
            list: Selected layer objects
        """
        selected = []
        for checkbox, layer in self.checkboxes.values():
            if checkbox.isChecked():
                selected.append(layer)
        return selected


class CopyPolygonLayerStyleAction(BaseAction):
    """Action to copy style from one polygon layer to other polygon layers."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "copy_polygon_layer_style"
        self.name = "Copy Polygon Layer Style"
        self.category = "Styling"
        self.description = (
            "Copy the style (symbology, labeling, effects) from this polygon layer "
            "to other polygon layers in the project. A dialog will show all available "
            "polygon layers where you can select which ones to apply the style to."
        )
        self.enabled = True
        
        # Action scoping - works on layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
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
            'copy_symbology': {
                'type': 'bool',
                'default': True,
                'label': 'Copy Symbology',
                'description': 'Copy the layer symbology (colors, styles, sizes) to target layers',
            },
            'copy_labeling': {
                'type': 'bool',
                'default': True,
                'label': 'Copy Labeling',
                'description': 'Copy the layer labeling settings to target layers',
            },
            'copy_effects': {
                'type': 'bool',
                'default': True,
                'label': 'Copy Effects',
                'description': 'Copy paint effects and other rendering effects to target layers',
            },
            'copy_opacity': {
                'type': 'bool',
                'default': True,
                'label': 'Copy Opacity',
                'description': 'Copy the layer opacity/transparency to target layers',
            },
            'confirm_action': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Action',
                'description': 'Show confirmation message after copying style to layers',
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
        """Execute the copy polygon layer style action."""
        try:
            copy_symbology = bool(self.get_setting('copy_symbology', True))
            copy_labeling = bool(self.get_setting('copy_labeling', True))
            copy_effects = bool(self.get_setting('copy_effects', True))
            copy_opacity = bool(self.get_setting('copy_opacity', True))
            confirm_action = bool(self.get_setting('confirm_action', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No polygon layer found at this location")
            return
        
        source_layer = detected_features[0].layer
        
        if not isinstance(source_layer, QgsVectorLayer):
            self.show_error("Error", "Source must be a vector layer")
            return
        
        if source_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "Source layer is not a polygon layer")
            return
        
        # Get all other polygon layers in the project
        target_layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if (isinstance(layer, QgsVectorLayer) and 
                layer.geometryType() == QgsWkbTypes.PolygonGeometry and
                layer.id() != source_layer.id()):
                target_layers.append(layer)
        
        if not target_layers:
            self.show_info("No Layers", "No other polygon layers found in the project")
            self.record_informational(
                description=f"Attempted to copy style from polygon layer '{source_layer.name()}' but no other polygon layers were available"
            )
            return
        
        # Show dialog to select target layers
        dialog = CopyPolygonLayerStyleDialog(source_layer, target_layers, None)
        if dialog.exec() != QDialog.Accepted:
            return
        
        selected_layers = dialog.get_selected_layers()
        
        if not selected_layers:
            self.show_info("No Selection", "Please select at least one layer to copy the style to")
            return
        
        try:
            copied_count = 0
            errors = []
            
            for target_layer in selected_layers:
                try:
                    # Copy symbology
                    if copy_symbology and source_layer.renderer():
                        target_layer.setRenderer(source_layer.renderer().clone())
                    
                    # Copy labeling
                    if copy_labeling and source_layer.labeling():
                        target_layer.setLabeling(source_layer.labeling().clone())
                    
                    # Copy effects
                    if copy_effects:
                        target_layer.setPaintEffect(source_layer.paintEffect())
                    
                    # Copy opacity
                    if copy_opacity:
                        target_layer.setOpacity(source_layer.opacity())
                    
                    target_layer.triggerRepaint()
                    copied_count += 1
                    
                except Exception as e:
                    errors.append(f"{target_layer.name()}: {str(e)}")
            
            # Show result message
            if confirm_action:
                if errors:
                    error_msg = "\n".join(errors)
                    self.show_info(
                        "Copy Style Complete (with errors)",
                        f"Successfully copied style to {copied_count} layer(s).\n\nErrors:\n{error_msg}"
                    )
                else:
                    self.show_info(
                        "Copy Style Complete",
                        f"Successfully copied style from '{source_layer.name()}' to {copied_count} polygon layer(s)"
                    )
            
            # Record to history
            self.record_informational(
                description=f"Copied style from polygon layer '{source_layer.name()}' to {copied_count} polygon layer(s)",
                meta={
                    'source_layer': source_layer.name(),
                    'target_count': copied_count,
                    'copy_symbology': copy_symbology,
                    'copy_labeling': copy_labeling,
                    'copy_effects': copy_effects,
                    'copy_opacity': copy_opacity,
                }
            )
            
        except Exception as e:
            self.show_error("Error", f"Failed to copy style: {str(e)}")


# Create global instance for automatic discovery
copy_polygon_layer_style_action = CopyPolygonLayerStyleAction()
