"""
Zoom to Point Action for Right-click Utilities and Shortcuts Hub

Zooms the map to show the selected point feature by creating a virtual bounding box
with 400-unit radius around the point. Works with point and multipoint features.
"""

from .base_action import BaseAction
from qgis.core import QgsRectangle, QgsPointXY


class ZoomToPointAction(BaseAction):
    """Action to zoom to point features with virtual bounding box."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "zoom_to_point"
        self.name = "Zoom to Point"
        self.category = "Navigation"
        self.description = "Zoom the map to show the selected point feature with virtual bounding box. Creates a 400-unit radius around the point for better visibility. Works with point and multipoint features."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with point features
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # ZOOM SETTINGS - Easy to customize zoom behavior
            'zoom_radius': {
                'type': 'float',
                'default': 400.0,
                'label': 'Zoom Radius',
                'description': 'Radius in map units to create around the point for zooming. Larger values show more area around the point.',
                'min': 10.0,
                'max': 10000.0,
                'step': 10.0,
            },
            'minimum_zoom_radius': {
                'type': 'float',
                'default': 50.0,
                'label': 'Minimum Zoom Radius',
                'description': 'Minimum radius to prevent zooming too close to the point',
                'min': 1.0,
                'max': 1000.0,
                'step': 1.0,
            },
            'maximum_zoom_radius': {
                'type': 'float',
                'default': 5000.0,
                'label': 'Maximum Zoom Radius',
                'description': 'Maximum radius to prevent zooming too far from the point',
                'min': 100.0,
                'max': 50000.0,
                'step': 10.0,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_zoom_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Zoom Info',
                'description': 'Display information about the zoom operation (point coordinates, radius used, etc.)',
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
            'center_on_point': {
                'type': 'bool',
                'default': True,
                'label': 'Center on Point',
                'description': 'Ensure the point is centered in the view after zooming',
            },
        }
    
    def execute(self, context):
        """
        Execute the zoom to point action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            zoom_radius = float(self.get_setting('zoom_radius', 400.0))
            minimum_radius = float(self.get_setting('minimum_zoom_radius', 50.0))
            maximum_radius = float(self.get_setting('maximum_zoom_radius', 5000.0))
            show_zoom_info = bool(self.get_setting('show_zoom_info', False))
            smooth_zoom = bool(self.get_setting('smooth_zoom', True))
            zoom_duration = int(self.get_setting('zoom_duration', 500))
            center_on_point = bool(self.get_setting('center_on_point', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No point features found at this location")
            return
        
        if not canvas:
            self.show_error("Error", "Map canvas not available")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get feature geometry
            geometry = feature.geometry()
            if not geometry:
                self.show_error("Error", "Feature has no geometry")
                return
            
            # Get the point coordinates
            point = geometry.asPoint()
            if point.isEmpty():
                self.show_error("Error", "Feature has empty point geometry")
                return
            
            # Apply radius constraints
            actual_radius = max(minimum_radius, min(maximum_radius, zoom_radius))
            
            # Create virtual bounding box with configured radius around the point
            virtual_bbox = QgsRectangle(
                point.x() - actual_radius,  # x minimum
                point.y() - actual_radius,  # y minimum
                point.x() + actual_radius,  # x maximum
                point.y() + actual_radius   # y maximum
            )
            
            # Ensure point is centered if requested
            if center_on_point:
                # Adjust bbox to center the point
                center_x = point.x()
                center_y = point.y()
                virtual_bbox.setXMinimum(center_x - actual_radius)
                virtual_bbox.setXMaximum(center_x + actual_radius)
                virtual_bbox.setYMinimum(center_y - actual_radius)
                virtual_bbox.setYMaximum(center_y + actual_radius)
            
            # Zoom to the virtual bounding box
            if smooth_zoom:
                # Use smooth zoom animation (placeholder for future enhancement)
                canvas.setExtent(virtual_bbox)
                canvas.refresh()
            else:
                # Instant zoom
                canvas.setExtent(virtual_bbox)
                canvas.refresh()
            
            # Show zoom info if requested
            if show_zoom_info:
                info_text = f"Feature ID: {feature.id()}\n"
                info_text += f"Layer: {layer.name()}\n"
                info_text += f"Point Coordinates: ({point.x():.2f}, {point.y():.2f})\n"
                info_text += f"Zoom Radius: {actual_radius:.2f} map units\n"
                info_text += f"Extent: {virtual_bbox.width():.2f} x {virtual_bbox.height():.2f} map units"
                self.show_info("Zoom Information", info_text)
            
        except Exception as e:
            self.show_error("Error", f"Failed to zoom to point feature: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
zoom_to_point_action = ZoomToPointAction()
