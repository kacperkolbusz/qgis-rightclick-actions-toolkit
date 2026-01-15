"""
Zoom to Visible Data Layers Action for Right-click Utilities and Shortcuts Hub

Zooms the map canvas to show all visible data layers in the project.
Excludes basemap layers to prevent excessive zoom-out. Only available when clicking on empty canvas areas.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsCoordinateTransform


class ZoomToVisibleDataLayersAction(BaseAction):
    """
    Action to zoom the canvas to show all visible data layers.
    
    This action calculates the combined extent of all visible data layers
    in the project and zooms the canvas to fit them all in view.
    Excludes basemap layers to prevent excessive zoom-out.
    Only works when clicking on empty canvas areas.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "zoom_to_visible_data_layers"
        self.name = "Zoom to Visible Data Layers"
        self.category = "Analysis"
        self.description = "Zoom the map canvas to show all visible data layers in the project. Calculates combined extent of all visible data layers (excluding basemaps) and adjusts view accordingly. Only available when clicking on empty canvas."
        self.enabled = True
        
        # Action scoping - universal action that works on canvas
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - only works with canvas clicks
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['universal'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # ZOOM SETTINGS
            'buffer_percentage': {
                'type': 'float',
                'default': 10.0,
                'label': 'Zoom Buffer Percentage',
                'description': 'Percentage of extent size to add as buffer when zooming. Higher values show more area around the layers.',
                'min': 0.0,
                'max': 50.0,
                'step': 1.0,
            },
            'smooth_zoom': {
                'type': 'bool',
                'default': True,
                'label': 'Smooth Zoom Animation',
                'description': 'Use smooth zoom animation instead of instant zoom',
            },
            'zoom_duration': {
                'type': 'int',
                'default': 500,
                'label': 'Zoom Animation Duration',
                'description': 'Duration of zoom animation in milliseconds (only used if smooth zoom is enabled)',
                'min': 100,
                'max': 2000,
                'step': 50,
            },
            
            # BEHAVIOR SETTINGS
            'include_invisible_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Include Invisible Layers',
                'description': 'Include invisible layers in extent calculation (normally only visible layers are included)',
            },
            'show_info_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Info Message',
                'description': 'Display information message when zoom operation completes',
            },
            'show_error_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Error Messages',
                'description': 'Display error messages if zoom operation fails',
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
    
    def _is_basemap_layer(self, layer):
        """
        Check if a layer is a basemap layer that should be excluded from extent calculation.
        
        Args:
            layer: QgsMapLayer to check
            
        Returns:
            bool: True if layer is a basemap layer
        """
        # Check layer type - basemaps are usually raster layers
        if layer.type() != layer.RasterLayer:
            return False
        
        # Check layer name for common basemap patterns
        layer_name = layer.name().lower()
        basemap_keywords = [
            'openstreetmap', 'osm', 'google', 'bing', 'mapbox', 'cartodb',
            'satellite', 'imagery', 'terrain', 'hybrid', 'streets', 'roads',
            'world', 'global', 'basemap', 'base map', 'tile', 'xyz'
        ]
        
        for keyword in basemap_keywords:
            if keyword in layer_name:
                return True
        
        # Check layer source for common basemap URLs
        if hasattr(layer, 'source'):
            source = layer.source().lower()
            basemap_urls = [
                'openstreetmap.org', 'googleapis.com', 'bing.com', 'mapbox.com',
                'cartodb.com', 'arcgis.com', 'tile.openstreetmap.org'
            ]
            
            for url in basemap_urls:
                if url in source:
                    return True
        
        # Check if layer has very large extent (typical of basemaps)
        try:
            extent = layer.extent()
            if extent.width() > 360 or extent.height() > 180:  # Global extent
                return True
        except:
            pass
        
        return False
    
    def execute(self, context):
        """
        Execute the zoom to visible data layers action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            buffer_percentage = float(self.get_setting('buffer_percentage', 10.0))
            smooth_zoom = bool(self.get_setting('smooth_zoom', True))
            zoom_duration = int(self.get_setting('zoom_duration', 500))
            include_invisible_layers = bool(self.get_setting('include_invisible_layers', False))
            show_info_message = bool(self.get_setting('show_info_message', True))
            show_error_messages = bool(self.get_setting('show_error_messages', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        canvas = context.get('canvas')
        click_point = context.get('click_point')
        
        if not canvas:
            if show_error_messages:
                self.show_error("Error", "No canvas available")
            return
        
        try:
            # Get project and layers
            project = QgsProject.instance()
            layers = project.mapLayers().values()
            
            if not layers:
                if show_error_messages:
                    self.show_warning("No Layers", "No layers found in the project.")
                return
            
            # Filter layers based on visibility setting
            if not include_invisible_layers:
                # Only include visible layers (checked in layer tree)
                layer_tree_root = project.layerTreeRoot()
                visible_layers = []
                for layer in layers:
                    if layer.isValid():
                        # Check if layer is visible in layer tree
                        layer_tree_layer = layer_tree_root.findLayer(layer.id())
                        if layer_tree_layer and layer_tree_layer.isVisible():
                            # Skip basemap layers (they have global extent and cause zoom issues)
                            if not self._is_basemap_layer(layer):
                                visible_layers.append(layer)
                layers = visible_layers
            
            if not layers:
                if show_error_messages:
                    self.show_warning("No Visible Layers", "No visible layers found in the project.")
                return
            
            # Calculate combined extent
            combined_extent = None
            canvas_crs = canvas.mapSettings().destinationCrs()
            layers_processed = 0
            
            for layer in layers:
                if not layer.isValid():
                    continue
                
                try:
                    # Get layer extent
                    layer_extent = layer.extent()
                    if layer_extent.isEmpty():
                        continue
                    
                    # CRITICAL: Transform to canvas CRS if needed
                    layer_crs = layer.crs()
                    if canvas_crs != layer_crs:
                        transform = QgsCoordinateTransform(layer_crs, canvas_crs, project)
                        try:
                            layer_extent = transform.transformBoundingBox(layer_extent)
                        except Exception as e:
                            if show_error_messages:
                                self.show_warning("CRS Warning", f"Could not transform layer '{layer.name()}' extent: {str(e)}")
                            continue
                    
                    # Combine with overall extent
                    if combined_extent is None:
                        combined_extent = layer_extent
                    else:
                        combined_extent.combineExtentWith(layer_extent)
                    
                    layers_processed += 1
                    
                except Exception as e:
                    if show_error_messages:
                        self.show_warning("Layer Warning", f"Could not process layer '{layer.name()}': {str(e)}")
                    continue
            
            if combined_extent is None or combined_extent.isEmpty():
                if show_error_messages:
                    self.show_warning("No Extent", "Could not determine extent from any layers.")
                return
            
            # Apply buffer if specified
            if buffer_percentage > 0:
                width = combined_extent.width()
                height = combined_extent.height()
                buffer_x = width * (buffer_percentage / 100.0)
                buffer_y = height * (buffer_percentage / 100.0)
                
                combined_extent.setXMinimum(combined_extent.xMinimum() - buffer_x)
                combined_extent.setXMaximum(combined_extent.xMaximum() + buffer_x)
                combined_extent.setYMinimum(combined_extent.yMinimum() - buffer_y)
                combined_extent.setYMaximum(combined_extent.yMaximum() + buffer_y)
            
            # Perform zoom
            if smooth_zoom:
                # Use smooth zoom animation
                canvas.zoomToFeatureExtent(combined_extent)
                canvas.refresh()
            else:
                # Use instant zoom
                canvas.setExtent(combined_extent)
                canvas.refresh()
            
            # Show success message if enabled
            if show_info_message:
                self.show_info("Zoom Complete", 
                    f"Canvas zoomed to show {layers_processed} layer(s).\n"
                    f"Extent: {combined_extent.xMinimum():.2f}, {combined_extent.yMinimum():.2f} to "
                    f"{combined_extent.xMaximum():.2f}, {combined_extent.yMaximum():.2f}")
                
        except Exception as e:
            if show_error_messages:
                self.show_error("Error", f"Failed to zoom to visible data layers: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
zoom_to_visible_data_layers = ZoomToVisibleDataLayersAction()
