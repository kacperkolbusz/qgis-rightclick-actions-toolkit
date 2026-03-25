"""
Change Basemap Rendering Action for Right-click Utilities and Shortcuts Hub

Detects the currently visible basemap layer and allows changing its rendering settings
through predefined and custom presets.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsMapLayer, QgsRasterLayer
from qgis.PyQt.QtWidgets import QMenu, QAction
from qgis.PyQt.QtCore import QSettings
from ..history_manager import get_history_manager


class ChangeBasemapRenderingAction(BaseAction):
    """
    Action to change rendering settings of the currently visible basemap.
    
    This action detects which basemap layer is currently visible and on top,
    then provides a submenu of rendering presets to choose from.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        # Required properties
        self.action_id = "change_basemap_rendering"
        self.name = "Change Basemap Rendering"
        self.category = "Styling"
        self.description = "Change rendering settings of the currently visible basemap layer. Choose from predefined presets or create your own to enhance map visibility for different scenarios."
        self.enabled = True
        
        # Action scoping configuration - universal action
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
            'show_preset_names': {
                'type': 'bool',
                'default': True,
                'label': 'Show Preset Names',
                'description': 'Show preset names in the submenu',
            },
            'show_reset_option': {
                'type': 'bool',
                'default': True,
                'label': 'Show Reset Option',
                'description': 'Show option to reset to default rendering',
            }
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
    
    # Custom preset functionality removed
    
    def get_top_visible_basemap(self):
        """
        Get the topmost visible raster layer (basemap).
        
        Returns:
            QgsRasterLayer or None: The topmost visible raster layer or None if not found
        """
        # Get the layer tree root
        root = QgsProject.instance().layerTreeRoot()
        
        # Get all map layers in drawing order (top to bottom)
        for layer in QgsProject.instance().mapLayers().values():
            if layer.isValid() and layer.type() == QgsMapLayer.RasterLayer:
                # Find the layer tree node for this layer
                node = root.findLayer(layer.id())
                if node and node.isVisible():
                    return layer
                
        return None
    
    def apply_preset_to_layer(self, layer, preset):
        """
        Apply rendering preset to the layer.
        
        Args:
            layer (QgsRasterLayer): Layer to apply preset to
            preset (dict): Rendering settings to apply
        
        Returns:
            bool: Success or failure
        """
        if not layer or not isinstance(layer, QgsRasterLayer):
            return False
            
        try:
            # Extract the three main settings from the preset
            brightness = preset.get('brightness', 0)
            contrast = preset.get('contrast', 0)
            saturation = preset.get('saturation', 0)
            
            # Import the required filter classes
            from qgis.core import QgsBrightnessContrastFilter, QgsHueSaturationFilter
            
            # Create and configure the brightness/contrast filter
            bc_filter = QgsBrightnessContrastFilter()
            bc_filter.setBrightness(brightness)
            bc_filter.setContrast(contrast)
            
            # Create and configure the hue/saturation filter
            hs_filter = QgsHueSaturationFilter()
            # The setSaturation method expects an integer value
            hs_filter.setSaturation(int(saturation))
            
            # Get the raster pipe
            pipe = layer.pipe()
            
            # Add the filters to the pipe
            pipe.set(bc_filter)
            pipe.set(hs_filter)
            
            # We don't handle gamma in this action
            
            # Trigger repaint to apply changes
            layer.triggerRepaint()
            
            return True
            
        except Exception as e:
            self.show_error("Error", f"Failed to apply preset: {str(e)}")
            return False
    
    def get_current_rendering_settings(self, layer):
        """
        Get current rendering settings from a layer.
        
        Args:
            layer (QgsRasterLayer): Layer to get settings from
            
        Returns:
            dict: Current rendering settings
        """
        if not layer or not isinstance(layer, QgsRasterLayer):
            return {}
            
        try:
            # Start with default settings for the three main parameters
            settings = {
                'brightness': 0,
                'contrast': 0,
                'saturation': 0
            }
            
            # Import the required filter classes
            from qgis.core import QgsBrightnessContrastFilter, QgsHueSaturationFilter
            
            # Get the raster pipe
            pipe = layer.pipe()

            # Collect filters in a version-tolerant way. Different QGIS
            # versions expose different methods on QgsRasterPipe.
            filters = []
            try:
                # Preferred: pipe.size() + pipe.filter(i)
                if hasattr(pipe, 'size') and callable(getattr(pipe, 'size')) and hasattr(pipe, 'filter'):
                    try:
                        for i in range(pipe.size()):
                            try:
                                f = pipe.filter(i)
                                if f is not None:
                                    filters.append(f)
                            except Exception:
                                continue
                    except Exception:
                        filters = []
                # Next: pipe.filters() returning a list
                elif hasattr(pipe, 'filters') and callable(getattr(pipe, 'filters')):
                    try:
                        fl = pipe.filters()
                        if fl:
                            filters = list(fl)
                    except Exception:
                        filters = []
                # Fallback: attribute 'filters' (non-callable)
                elif hasattr(pipe, 'filters'):
                    try:
                        fl = getattr(pipe, 'filters')
                        if fl:
                            filters = list(fl)
                    except Exception:
                        filters = []
                # Last resort: try filterAt / filterAtIndex
                else:
                    try:
                        idx = 0
                        while True:
                            try:
                                f = pipe.filterAt(idx)
                                if f is None:
                                    break
                                filters.append(f)
                                idx += 1
                            except Exception:
                                break
                    except Exception:
                        filters = []
            except Exception:
                filters = []

            # Inspect collected filters for brightness/contrast and hue/saturation
            for pipe_filter in filters:
                try:
                    if isinstance(pipe_filter, QgsBrightnessContrastFilter):
                        settings['brightness'] = pipe_filter.brightness()
                        settings['contrast'] = pipe_filter.contrast()
                    elif isinstance(pipe_filter, QgsHueSaturationFilter):
                        settings['saturation'] = pipe_filter.saturation()
                except Exception:
                    # ignore problematic filter objects
                    continue
            
            # We don't handle gamma in this action
                
            return settings
        except Exception as e:
            self.show_error("Error", f"Failed to get current settings: {str(e)}")
            return {}
    
    def create_preset_submenu(self, context, basemap_layer):
        """
        Create a submenu with preset options.
        
        Args:
            context (dict): Action context
            basemap_layer (QgsRasterLayer): Basemap layer to modify
            
        Returns:
            QMenu: Submenu with preset options
        """
        # Create submenu
        submenu = QMenu("Select Rendering Preset")
        
        # Get settings
        show_preset_names = bool(self.get_setting('show_preset_names', True))
        show_reset_option = bool(self.get_setting('show_reset_option', True))
        
        # Predefined presets - focused on the three main settings: brightness, contrast, saturation
        predefined_presets = {
            "Default": {
                'brightness': 0,
                'contrast': 0,
                'saturation': 0
            },
            "High Contrast": {
                'brightness': 20,
                'contrast': 60,
                'saturation': -10
            },
            "Low Contrast Desaturated": {
                'brightness': -10,
                'contrast': -30,
                'saturation': -60
            },
            "High Saturation": {
                'brightness': 30,
                'contrast': 20,
                'saturation': 70
            },
            "Night Mode": {
                'brightness': -99,
                'contrast': 0,
                'saturation': 0
            },
            "Soft Pastel": {
                'brightness': 50,
                'contrast': -20,
                'saturation': -40
            },
            "Maximum Saturation": {
                'brightness': 10,
                'contrast': 30,
                'saturation': 100
            },
            "Greyscale": {
                'brightness': 0,
                'contrast': 0,
                'saturation': -100
            },
            "Dark Mode": {
                'brightness': -40,
                'contrast': 30,
                'saturation': -20
            },
            "Bright Daylight": {
                'brightness': 40,
                'contrast': 25,
                'saturation': 15
            },
            "Sepia / Vintage": {
                'brightness': 15,
                'contrast': 10,
                'saturation': -50
            },
            "Print Ready": {
                'brightness': 15,
                'contrast': 50,
                'saturation': -15
            },
            "Subtle Enhancement": {
                'brightness': 10,
                'contrast': 20,
                'saturation': 10
            },
            "Cartographic": {
                'brightness': 5,
                'contrast': 35,
                'saturation': -30
            },
            "Satellite Enhanced": {
                'brightness': 20,
                'contrast': 40,
                'saturation': 50
            },
            "Topographic": {
                'brightness': 10,
                'contrast': 45,
                'saturation': -25
            },
            "Watercolor / Artistic": {
                'brightness': 35,
                'contrast': -30,
                'saturation': 20
            },
            "Vibrant / Vivid": {
                'brightness': 25,
                'contrast': 35,
                'saturation': 80
            },
            "Muted / Subdued": {
                'brightness': 5,
                'contrast': -15,
                'saturation': -50
            },
            "Overexposed": {
                'brightness': 60,
                'contrast': -20,
                'saturation': -10
            },
            "Underexposed": {
                'brightness': -50,
                'contrast': 20,
                'saturation': -10
            },
            "High Contrast B&W": {
                'brightness': 0,
                'contrast': 70,
                'saturation': -100
            },
            "Washed Out": {
                'brightness': 45,
                'contrast': -40,
                'saturation': -30
            },
            "Deep Shadows": {
                'brightness': -30,
                'contrast': 50,
                'saturation': 5
            }
        }
        
        # Add predefined presets to submenu
        for preset_name, preset_data in predefined_presets.items():
            preset_action = QAction(preset_name, submenu)
            # Wrap preset application to record history (undoable)
            def _apply_preset_record(l, p, pname=preset_name):
                try:
                    hm = get_history_manager()
                    # Capture current settings
                    before = self.get_current_rendering_settings(l) or {}

                    success = self.apply_preset_to_layer(l, p)

                    # Capture after settings
                    after = self.get_current_rendering_settings(l) or {}

                    if success:
                        try:
                            layer_desc = hm.create_layer_descriptor(l)
                        except Exception:
                            layer_desc = {'layer_id': getattr(l, 'id', lambda: None)(), 'layer_name': getattr(l, 'name', lambda: '')()}

                        # Record informational history entry (non-undoable)
                        try:
                            hm.record_informational(
                                action_id=self.action_id,
                                action_name=self.name,
                                description=f"Applied basemap preset '{pname}' to {l.name()}",
                                meta={
                                    'before': before,
                                    'after': after,
                                    'preset_name': pname,
                                    'layer': layer_desc
                                }
                            )
                        except Exception:
                            # Non-fatal: history recording should not interrupt action
                            pass

                    return success
                except Exception:
                    # Apply without recording if something fails
                    return self.apply_preset_to_layer(l, p)

            preset_action.triggered.connect(lambda checked=False, l=basemap_layer, p=preset_data, f=_apply_preset_record: f(l, p))
            submenu.addAction(preset_action)
        
        # Custom preset functionality removed
        
        # Add reset option if enabled
        if show_reset_option:
            submenu.addSeparator()
            reset_action = QAction("Reset to Default", submenu)
            # Wrap reset to record previous state
            def _reset_and_record(l):
                try:
                    hm = get_history_manager()
                    before = self.get_current_rendering_settings(l) or {}
                    success = self.apply_preset_to_layer(l, predefined_presets["Default"])
                    after = self.get_current_rendering_settings(l) or {}
                    if success:
                        try:
                            layer_desc = hm.create_layer_descriptor(l)
                        except Exception:
                            layer_desc = {'layer_id': getattr(l, 'id', lambda: None)(), 'layer_name': getattr(l, 'name', lambda: '')()}
                        try:
                            hm.record_informational(
                                action_id=self.action_id,
                                action_name=self.name,
                                description=f"Reset basemap rendering on {l.name()} to default",
                                meta={
                                    'before': before,
                                    'after': after,
                                    'preset_name': 'Default',
                                    'layer': layer_desc
                                }
                            )
                        except Exception:
                            pass
                    return success
                except Exception:
                    return self.apply_preset_to_layer(l, predefined_presets["Default"])

            reset_action.triggered.connect(lambda: _reset_and_record(basemap_layer))
            submenu.addAction(reset_action)
        
        return submenu
    
    # Custom preset functionality removed
    
    def execute(self, context):
        """
        Execute the action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            show_preset_names = bool(self.get_setting('show_preset_names', True))
            show_reset_option = bool(self.get_setting('show_reset_option', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Get top visible basemap
        basemap_layer = self.get_top_visible_basemap()
        if not basemap_layer:
            self.show_error("Error", "No visible basemap layer found")
            return
        
        # Create submenu with presets
        submenu = self.create_preset_submenu(context, basemap_layer)
        
        # Show the submenu
        canvas = context.get('canvas')
        cursor_pos = canvas.mapToGlobal(canvas.mouseLastXY())
        submenu.exec_(cursor_pos)


# REQUIRED: Create global instance for automatic discovery
change_basemap_rendering_action = ChangeBasemapRenderingAction()