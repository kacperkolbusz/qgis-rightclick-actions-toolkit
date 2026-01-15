"""
Zoom to Polygon Action for Right-click Utilities and Shortcuts Hub

Zooms the map to show the selected polygon feature with a 10% buffer around it.
Works with polygon and multipolygon features.
"""

from .base_action import BaseAction


class ZoomToPolygonAction(BaseAction):
    """Action to zoom to polygon features with buffer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "zoom_to_polygon"
        self.name = "Zoom to Polygon"
        self.category = "Navigation"
        self.description = "Zoom the map to show the selected polygon feature with 10% buffer. Calculates feature bounding box and adds padding for better visibility. Works with polygon and multipolygon features."
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
            # ZOOM SETTINGS - Easy to customize buffer and behavior
            'buffer_percentage': {
                'type': 'float',
                'default': 10.0,
                'label': 'Buffer Percentage',
                'description': 'Percentage of feature size to add as buffer when zooming. Higher values show more area around the feature.',
                'min': 0.0,
                'max': 100.0,
                'step': 1.0,
            },
            'minimum_buffer_percentage': {
                'type': 'float',
                'default': 1.0,
                'label': 'Minimum Buffer Percentage',
                'description': 'Minimum buffer percentage to prevent zooming too close to the feature',
                'min': 0.0,
                'max': 50.0,
                'step': 0.5,
            },
            'maximum_buffer_percentage': {
                'type': 'float',
                'default': 50.0,
                'label': 'Maximum Buffer Percentage',
                'description': 'Maximum buffer percentage to prevent zooming too far from the feature',
                'min': 5.0,
                'max': 200.0,
                'step': 1.0,
            },
            'minimum_zoom_level': {
                'type': 'float',
                'default': 0.0,
                'label': 'Minimum Zoom Level',
                'description': 'Minimum zoom level to prevent zooming too close to features',
                'min': 0.0,
                'max': 1000000.0,
                'step': 100.0,
            },
            'maximum_zoom_level': {
                'type': 'float',
                'default': 1000000.0,
                'label': 'Maximum Zoom Level',
                'description': 'Maximum zoom level to prevent zooming too far from features',
                'min': 0.0,
                'max': 1000000.0,
                'step': 100.0,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_zoom_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Zoom Info',
                'description': 'Display information about the zoom operation (feature size, buffer applied, etc.)',
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
            'center_on_feature': {
                'type': 'bool',
                'default': True,
                'label': 'Center on Feature',
                'description': 'Ensure the feature is centered in the view after zooming',
            },
            'show_error_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Error Messages',
                'description': 'Display error messages if zoom operation fails (useful for debugging)',
            },
        }
    
    def execute(self, context):
        """
        Execute the zoom to polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            buffer_percentage = float(self.get_setting('buffer_percentage', 10.0))
            minimum_buffer = float(self.get_setting('minimum_buffer_percentage', 1.0))
            maximum_buffer = float(self.get_setting('maximum_buffer_percentage', 50.0))
            minimum_zoom_level = float(self.get_setting('minimum_zoom_level', 0.0))
            maximum_zoom_level = float(self.get_setting('maximum_zoom_level', 1000000.0))
            show_zoom_info = bool(self.get_setting('show_zoom_info', False))
            smooth_zoom = bool(self.get_setting('smooth_zoom', True))
            zoom_duration = int(self.get_setting('zoom_duration', 500))
            center_on_feature = bool(self.get_setting('center_on_feature', True))
            show_errors = bool(self.get_setting('show_error_messages', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            if show_errors:
                self.show_error("Error", "No polygon features found at this location")
            return
        
        if not canvas:
            if show_errors:
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
                if show_errors:
                    self.show_error("Error", "Feature has no geometry")
                return
            
            # Get the bounding box of the polygon feature (in layer CRS)
            bbox = geometry.boundingBox()
            if bbox.isEmpty():
                if show_errors:
                    self.show_error("Error", "Feature has empty bounding box")
                return
            
            # CRITICAL: Transform bounding box to canvas CRS for proper canvas operations
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            
            # Always transform extent to canvas CRS for proper canvas operations
            from qgis.core import QgsCoordinateTransform, QgsProject, QgsRectangle
            
            # Create transform from layer CRS to canvas CRS
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            
            # Transform the bounding box to canvas CRS
            try:
                # Use transformBoundingBox for extent transformation
                canvas_bbox = transform.transformBoundingBox(bbox)
                
                # Ensure the transformed extent is valid
                if canvas_bbox.isEmpty() or not canvas_bbox.isFinite():
                    if show_errors:
                        self.show_error("Error", f"Transformed extent is invalid for feature ID {feature.id()}")
                    return
                    
                # Use the transformed bounding box for all canvas operations
                bbox = canvas_bbox
                
            except Exception as transform_error:
                if show_errors:
                    self.show_error("Error", f"CRS transformation failed from {layer_crs.description()} to {canvas_crs.description()}: {str(transform_error)}")
                return
            
            # Apply buffer percentage constraints
            actual_buffer = max(minimum_buffer, min(maximum_buffer, buffer_percentage))
            buffer_factor = actual_buffer / 100.0
            
            # Calculate buffer based on settings
            width = bbox.width()
            height = bbox.height()
            
            # Add buffer percentage to each side
            buffer_x = width * buffer_factor
            buffer_y = height * buffer_factor
            
            # Create buffered extent
            buffered_bbox = bbox
            buffered_bbox.setXMinimum(bbox.xMinimum() - buffer_x)
            buffered_bbox.setXMaximum(bbox.xMaximum() + buffer_x)
            buffered_bbox.setYMinimum(bbox.yMinimum() - buffer_y)
            buffered_bbox.setYMaximum(bbox.yMaximum() + buffer_y)
            
            # Check zoom level constraints
            bbox_width = buffered_bbox.width()
            bbox_height = buffered_bbox.height()
            max_dimension = max(bbox_width, bbox_height)
            
            if max_dimension < minimum_zoom_level:
                # Zoom is too close, adjust to minimum
                scale_factor = minimum_zoom_level / max_dimension
                center_x = buffered_bbox.center().x()
                center_y = buffered_bbox.center().y()
                new_width = bbox_width * scale_factor
                new_height = bbox_height * scale_factor
                
                buffered_bbox.setXMinimum(center_x - new_width / 2)
                buffered_bbox.setXMaximum(center_x + new_width / 2)
                buffered_bbox.setYMinimum(center_y - new_height / 2)
                buffered_bbox.setYMaximum(center_y + new_height / 2)
            elif max_dimension > maximum_zoom_level:
                # Zoom is too far, adjust to maximum
                scale_factor = maximum_zoom_level / max_dimension
                center_x = buffered_bbox.center().x()
                center_y = buffered_bbox.center().y()
                new_width = bbox_width * scale_factor
                new_height = bbox_height * scale_factor
                
                buffered_bbox.setXMinimum(center_x - new_width / 2)
                buffered_bbox.setXMaximum(center_x + new_width / 2)
                buffered_bbox.setYMinimum(center_y - new_height / 2)
                buffered_bbox.setYMaximum(center_y + new_height / 2)
            
            # Ensure feature is centered if requested
            if center_on_feature:
                # Calculate feature center
                feature_center = bbox.center()
                buffered_center = buffered_bbox.center()
                
                # Adjust buffered extent to center the feature
                offset_x = feature_center.x() - buffered_center.x()
                offset_y = feature_center.y() - buffered_center.y()
                
                buffered_bbox.setXMinimum(buffered_bbox.xMinimum() + offset_x)
                buffered_bbox.setXMaximum(buffered_bbox.xMaximum() + offset_x)
                buffered_bbox.setYMinimum(buffered_bbox.yMinimum() + offset_y)
                buffered_bbox.setYMaximum(buffered_bbox.yMaximum() + offset_y)
            
            # Zoom to the buffered extent
            if smooth_zoom:
                # Use smooth zoom animation
                self.smooth_zoom_to_extent(canvas, buffered_bbox, zoom_duration)
            else:
                # Instant zoom
                canvas.setExtent(buffered_bbox)
                canvas.refresh()
            
            # Show zoom info if requested
            if show_zoom_info:
                info_text = f"Feature ID: {feature.id()}\n"
                info_text += f"Layer: {layer.name()}\n"
                info_text += f"Original Extent: {bbox.width():.2f} x {bbox.height():.2f} map units\n"
                info_text += f"Buffer Percentage: {actual_buffer:.1f}%\n"
                info_text += f"Final Extent: {buffered_bbox.width():.2f} x {buffered_bbox.height():.2f} map units"
                self.show_info("Zoom Information", info_text)
            
        except Exception as e:
            if show_errors:
                self.show_error("Error", f"Failed to zoom to polygon feature: {str(e)}")
            # Silently handle any errors if not showing errors
    
    def smooth_zoom_to_extent(self, canvas, target_extent, duration):
        """
        Perform smooth zoom animation to target extent.
        
        Args:
            canvas: Map canvas
            target_extent: Target extent to zoom to
            duration: Animation duration in milliseconds
        """
        try:
            # For now, use instant zoom (smooth zoom would require more complex implementation)
            # This is a placeholder for future enhancement
            canvas.setExtent(target_extent)
            canvas.refresh()
        except Exception:
            # Fallback to instant zoom
            canvas.setExtent(target_extent)
            canvas.refresh()


# REQUIRED: Create global instance for automatic discovery
zoom_to_polygon_action = ZoomToPolygonAction()
