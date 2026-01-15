"""
Zoom to Line Layer Action for Right-click Utilities and Shortcuts Hub

Zooms the map to show all lines on the selected line layer with buffer.
Works on line layers and operates silently without popup windows.
"""

from .base_action import BaseAction
from qgis.gui import QgsMapCanvas
from qgis.core import QgsVectorLayer


class ZoomToLineLayerAction(BaseAction):
    """Action to zoom to show all lines on a line layer with buffer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "zoom_to_line_layer"
        self.name = "Zoom to Line Layer"
        self.category = "Navigation"
        self.description = "Zoom the map to show all lines on the selected line layer with buffer. Calculates layer extent and adds padding for better visibility. Works on line and multiline layers."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # ZOOM SETTINGS - Easy to customize zoom behavior
            'buffer_percentage': {
                'type': 'float',
                'default': 10.0,
                'label': 'Buffer Percentage',
                'description': 'Percentage of layer extent to add as buffer around the zoom area. Higher values show more area around the layer.',
                'min': 0.0,
                'max': 100.0,
                'step': 1.0,
            },
            'minimum_buffer_percentage': {
                'type': 'float',
                'default': 1.0,
                'label': 'Minimum Buffer Percentage',
                'description': 'Minimum buffer percentage to prevent zooming too close to the layer',
                'min': 0.0,
                'max': 50.0,
                'step': 0.5,
            },
            'maximum_buffer_percentage': {
                'type': 'float',
                'default': 50.0,
                'label': 'Maximum Buffer Percentage',
                'description': 'Maximum buffer percentage to prevent zooming too far from the layer',
                'min': 5.0,
                'max': 200.0,
                'step': 1.0,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_zoom_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Zoom Info',
                'description': 'Display information about the zoom operation (layer name, extent, buffer used, etc.)',
            },
            'smooth_zoom': {
                'type': 'bool',
                'default': True,
                'label': 'Smooth Zoom',
                'description': 'Use smooth zoom animation instead of instant zoom',
            },
            'zoom_duration': {
                'type': 'int',
                'default': 500,
                'label': 'Zoom Duration (ms)',
                'description': 'Duration of smooth zoom animation in milliseconds',
                'min': 100,
                'max': 2000,
                'step': 100,
            },
            'center_on_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Center on Layer',
                'description': 'Ensure the layer is centered in the view after zooming',
            },
            'show_error_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Error Messages',
                'description': 'Display error messages if zoom operation fails (useful for debugging)',
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
        Execute the zoom to line layer action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion and error handling
        try:
            buffer_percentage = float(self.get_setting('buffer_percentage', 10.0))
            minimum_buffer = float(self.get_setting('minimum_buffer_percentage', 1.0))
            maximum_buffer = float(self.get_setting('maximum_buffer_percentage', 50.0))
            show_zoom_info = bool(self.get_setting('show_zoom_info', False))
            smooth_zoom = bool(self.get_setting('smooth_zoom', True))
            zoom_duration = int(self.get_setting('zoom_duration', 500))
            center_on_layer = bool(self.get_setting('center_on_layer', True))
            show_errors = bool(self.get_setting('show_error_messages', True))
        except (ValueError, TypeError) as e:
            if show_errors:
                self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            if show_errors:
                self.show_error("Error", "No line features found at this location")
            return  # Silently fail if no features found
        
        if not canvas:
            if show_errors:
                self.show_error("Error", "Map canvas not available")
            return  # Silently fail if no canvas
        
        # Get the first (closest) detected feature to determine the layer
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Check if layer is a vector layer
        if not isinstance(layer, QgsVectorLayer):
            if show_errors:
                self.show_error("Error", "Selected layer is not a vector layer")
            return  # Silently fail if not a vector layer
        
        try:
            # Get canvas and layer CRS information
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            
            # Get layer extent - this is in the layer's CRS
            layer_extent = layer.extent()
            if layer_extent.isEmpty():
                if show_errors:
                    self.show_error("Error", f"Layer '{layer.name()}' has no extent")
                return  # Silently fail if layer has no extent
            
            # CRITICAL: Always transform extent to canvas CRS for proper canvas operations
            # Even if CRS appear the same, we need to ensure proper transformation
            from qgis.core import QgsCoordinateTransform, QgsProject, QgsRectangle
            
            # Create transform from layer CRS to canvas CRS
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            
            # Transform the extent to canvas CRS
            try:
                # Use transformBoundingBox for extent transformation
                canvas_extent = transform.transformBoundingBox(layer_extent)
                
                # Ensure the transformed extent is valid
                if canvas_extent.isEmpty() or not canvas_extent.isFinite():
                    if show_errors:
                        self.show_error("Error", f"Transformed extent is invalid for layer '{layer.name()}'")
                    return
                    
                # Use the transformed extent for all canvas operations
                layer_extent = canvas_extent
                
            except Exception as transform_error:
                if show_errors:
                    self.show_error("Error", f"CRS transformation failed from {layer_crs.description()} to {canvas_crs.description()}: {str(transform_error)}")
                return  # Silently fail if transformation fails
            
            # Apply buffer percentage constraints
            actual_buffer = max(minimum_buffer, min(maximum_buffer, buffer_percentage))
            buffer_factor = actual_buffer / 100.0
            
            # Calculate buffer
            width = layer_extent.width()
            height = layer_extent.height()
            
            # Add buffer to each side
            buffer_x = width * buffer_factor
            buffer_y = height * buffer_factor
            
            # Create buffered extent
            buffered_extent = layer_extent
            buffered_extent.setXMinimum(layer_extent.xMinimum() - buffer_x)
            buffered_extent.setXMaximum(layer_extent.xMaximum() + buffer_x)
            buffered_extent.setYMinimum(layer_extent.yMinimum() - buffer_y)
            buffered_extent.setYMaximum(layer_extent.yMaximum() + buffer_y)
            
            # Ensure layer is centered if requested
            if center_on_layer:
                # Calculate layer center
                layer_center = layer_extent.center()
                buffered_center = buffered_extent.center()
                
                # Adjust buffered extent to center the layer
                offset_x = layer_center.x() - buffered_center.x()
                offset_y = layer_center.y() - buffered_center.y()
                
                buffered_extent.setXMinimum(buffered_extent.xMinimum() + offset_x)
                buffered_extent.setXMaximum(buffered_extent.xMaximum() + offset_x)
                buffered_extent.setYMinimum(buffered_extent.yMinimum() + offset_y)
                buffered_extent.setYMaximum(buffered_extent.yMaximum() + offset_y)
            
            # Zoom to the buffered extent
            if smooth_zoom:
                # Use smooth zoom animation (placeholder for future enhancement)
                canvas.setExtent(buffered_extent)
                canvas.refresh()
            else:
                # Instant zoom
                canvas.setExtent(buffered_extent)
                canvas.refresh()
            
            # Show zoom info if requested
            if show_zoom_info:
                info_text = f"Layer: {layer.name()}\n"
                info_text += f"Feature Count: {layer.featureCount()}\n"
                info_text += f"Original Extent: {layer_extent.width():.2f} x {layer_extent.height():.2f} map units\n"
                info_text += f"Buffer Percentage: {actual_buffer:.1f}%\n"
                info_text += f"Final Extent: {buffered_extent.width():.2f} x {buffered_extent.height():.2f} map units"
                self.show_info("Zoom Information", info_text)
            
        except Exception as e:
            if show_errors:
                self.show_error("Error", f"Failed to zoom to line layer: {str(e)}")
            # Silently handle any errors if not showing errors


# REQUIRED: Create global instance for automatic discovery
zoom_to_line_layer_action = ZoomToLineLayerAction()
