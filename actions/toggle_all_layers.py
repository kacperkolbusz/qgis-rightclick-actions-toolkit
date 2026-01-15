"""
Toggle All Layers Action for Right-click Utilities and Shortcuts Hub

Toggles the visibility of all layers in the project on/off.
Works universally from any location - canvas, features, or layers.
"""

from .base_action import BaseAction
from qgis.core import QgsProject


class ToggleAllLayersAction(BaseAction):
    """
    Action to toggle visibility of all layers in the project.
    
    This action toggles the visibility state of all layers in the project.
    If any layers are visible, it hides all layers. If all layers are hidden,
    it shows all layers. Works universally from any location.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "toggle_all_layers"
        self.name = "Toggle All Layers"
        self.category = "Analysis"
        self.description = "Toggle visibility of all layers in the project on/off. If any layers are visible, hides all layers. If all layers are hidden, shows all layers. Works universally from any location."
        self.enabled = True
        
        # Action scoping - universal action that works everywhere
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - works everywhere
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['universal'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # BEHAVIOR SETTINGS
            'show_info_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Info Message',
                'description': 'Display information message when toggle operation completes',
            },
            'show_error_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Error Messages',
                'description': 'Display error messages if toggle operation fails',
            },
            'include_basemap_layers': {
                'type': 'bool',
                'default': True,
                'label': 'Include Basemap Layers',
                'description': 'Include basemap layers (OpenStreetMap, satellite imagery, etc.) in toggle operation',
            },
            'refresh_canvas': {
                'type': 'bool',
                'default': True,
                'label': 'Refresh Canvas',
                'description': 'Refresh the map canvas after toggling layer visibility',
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
        Check if a layer is a basemap layer.
        
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
        Execute the toggle all layers action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            show_info_message = bool(self.get_setting('show_info_message', True))
            show_error_messages = bool(self.get_setting('show_error_messages', True))
            include_basemap_layers = bool(self.get_setting('include_basemap_layers', True))
            refresh_canvas = bool(self.get_setting('refresh_canvas', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        canvas = context.get('canvas')
        
        try:
            # Get project and layer tree
            project = QgsProject.instance()
            layer_tree_root = project.layerTreeRoot()
            
            # Get all layers
            all_layers = project.mapLayers().values()
            
            if not all_layers:
                if show_error_messages:
                    self.show_warning("No Layers", "No layers found in the project.")
                return
            
            # Filter layers based on basemap setting
            layers_to_process = []
            for layer in all_layers:
                if layer.isValid():
                    if include_basemap_layers or not self._is_basemap_layer(layer):
                        layers_to_process.append(layer)
            
            if not layers_to_process:
                if show_error_messages:
                    self.show_warning("No Layers", "No layers to process found in the project.")
                return
            
            # Count visible and hidden layers
            visible_count = 0
            hidden_count = 0
            
            for layer in layers_to_process:
                layer_tree_layer = layer_tree_root.findLayer(layer.id())
                if layer_tree_layer:
                    if layer_tree_layer.isVisible():
                        visible_count += 1
                    else:
                        hidden_count += 1
            
            # Determine toggle action
            # If any layers are visible, hide all. If all are hidden, show all.
            if visible_count > 0:
                # Hide all layers
                new_visibility = False
                action_description = "hidden"
            else:
                # Show all layers
                new_visibility = True
                action_description = "shown"
            
            # Apply visibility changes
            layers_changed = 0
            for layer in layers_to_process:
                layer_tree_layer = layer_tree_root.findLayer(layer.id())
                if layer_tree_layer:
                    layer_tree_layer.setItemVisibilityChecked(new_visibility)
                    layers_changed += 1
            
            # Refresh canvas if requested
            if refresh_canvas and canvas:
                canvas.refresh()
            
            # Show success message if enabled
            if show_info_message:
                self.show_info("Toggle Complete", 
                    f"All layers have been {action_description}.\n"
                    f"Layers processed: {layers_changed}\n"
                    f"Basemap layers included: {'Yes' if include_basemap_layers else 'No'}")
                
        except Exception as e:
            if show_error_messages:
                self.show_error("Error", f"Failed to toggle layer visibility: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
toggle_all_layers = ToggleAllLayersAction()
