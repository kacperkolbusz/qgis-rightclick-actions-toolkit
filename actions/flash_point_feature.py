"""
Flash Point Feature Action for Right-click Utilities and Shortcuts Hub

Makes the selected point feature flash on the canvas for easy identification.
"""

from .base_action import BaseAction
from qgis.PyQt.QtCore import QTimer, QObject, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject


class FlashTimer(QObject):
    """Timer class to handle feature flashing using temporary selection."""
    
    def __init__(self, feature, layer, canvas, flash_duration, flash_frequency):
        super().__init__()
        self.feature = feature
        self.layer = layer
        self.canvas = canvas
        self.flash_duration = flash_duration
        self.flash_frequency = int(flash_frequency)  # Ensure integer
        self.is_flashing = False
        self.flash_count = 0
        self.max_flashes = int((flash_duration * 1000) / self.flash_frequency)
        
        # Create flash timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.toggle_flash)
        
        # Create stop timer
        self.stop_timer = QTimer()
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.stop_flashing)
        
    def start_flashing(self, flash_color):
        """Start the flashing effect using selection highlighting."""
        self.flash_color = flash_color
        self.flash_count = 0
        self.is_flashing = True
        
        # Start flash timer
        self.timer.start(self.flash_frequency)
        
        # Start stop timer
        self.stop_timer.start(int(self.flash_duration * 1000))  # Ensure integer
        
    def toggle_flash(self):
        """Toggle between normal and flash using selection."""
        if self.flash_count >= self.max_flashes:
            self.stop_flashing()
            return
            
        self.is_flashing = not self.is_flashing
        
        if self.is_flashing:
            # Select the feature to highlight it
            self.layer.select(self.feature.id())
        else:
            # Deselect the feature
            self.layer.deselect(self.feature.id())
        
        # Refresh canvas
        self.canvas.refresh()
        self.flash_count += 1
        
    def stop_flashing(self):
        """Stop the flashing effect and clear selection."""
        self.timer.stop()
        self.stop_timer.stop()
        
        # Clear selection
        self.layer.removeSelection()
        self.canvas.refresh()
        
        # Clean up
        self.deleteLater()


class FlashPointFeatureAction(BaseAction):
    """
    Action to flash the selected point feature on the canvas.
    
    This action makes the clicked point feature flash with a customizable
    color, duration, and frequency for easy identification on the map.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "flash_point_feature"
        self.name = "Flash Point Feature"
        self.category = "Visualization"
        self.description = "Make the selected point feature flash on the canvas for easy identification. Customizable flash color, duration, and frequency."
        self.enabled = True
        
        # Action scoping configuration - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with points
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'flash_color': {
                'type': 'color',
                'default': '#FF0000',
                'label': 'Flash Color',
                'description': 'Color used for flashing the feature',
            },
            'flash_duration': {
                'type': 'float',
                'default': 3.0,
                'label': 'Flash Duration (seconds)',
                'description': 'Total duration of the flashing effect in seconds',
                'min': 0.5,
                'max': 10.0,
                'step': 0.5,
            },
            'flash_frequency': {
                'type': 'int',
                'default': 500,
                'label': 'Flash Frequency (milliseconds)',
                'description': 'Time between flash toggles in milliseconds',
                'min': 200,
                'max': 2000,
                'step': 100,
            },
            'show_feature_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature Info',
                'description': 'Display feature information dialog after flashing starts',
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
        Execute the flash point feature action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            flash_color = str(self.get_setting('flash_color', schema['flash_color']['default']))
            flash_duration = float(self.get_setting('flash_duration', schema['flash_duration']['default']))
            flash_frequency = int(self.get_setting('flash_frequency', schema['flash_frequency']['default']))
            show_feature_info = bool(self.get_setting('show_feature_info', schema['show_feature_info']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        if not canvas:
            self.show_error("Error", "Canvas not available")
            return
        
        # Get the clicked feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Check if layer is valid and has features
            if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                self.show_error("Error", "Invalid layer")
                return
            
            # Start flashing
            flash_timer = FlashTimer(feature, layer, canvas, flash_duration, flash_frequency)
            flash_timer.start_flashing(flash_color)
            
            # Show feature info if enabled
            if show_feature_info:
                self.show_info("Feature Flashing", 
                    f"Point feature ID {feature.id()} is now flashing for {flash_duration} seconds.\n"
                    f"Layer: {layer.name()}\n"
                    f"Flash color: {flash_color}\n"
                    f"Flash frequency: {flash_frequency}ms")
            
            # Record informational history entry (non-undoable)
            try:
                self.record_informational(
                    description=f"Flashed point feature {feature.id()} on layer '{layer.name()}' for {flash_duration}s",
                    meta={
                        'feature_id': feature.id(),
                        'layer_id': layer.id(),
                        'flash_duration': flash_duration,
                        'flash_frequency': flash_frequency,
                        'flash_color': flash_color
                    }
                )
            except Exception:
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to flash feature: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
flash_point_feature_action = FlashPointFeatureAction()

def _add_non_undoable_methods():
    # Attach supports_undo and get_undo_category to the class to mark it non-undoable
    def supports_undo(self):
        return False

    def get_undo_category(self):
        return 'informational'

    FlashPointFeatureAction.supports_undo = supports_undo
    FlashPointFeatureAction.get_undo_category = get_undo_category

_add_non_undoable_methods()

