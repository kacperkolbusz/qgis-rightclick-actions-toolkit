"""
Change Map Scale Action for Right-click Utilities and Shortcuts Hub

Provides a submenu with common map scales to quickly change the map view scale.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import QMenu, QAction
from qgis.PyQt.QtGui import QCursor


class ChangeMapScaleAction(BaseAction):
    """
    Action to change the map scale via a submenu with predefined scale options.
    
    This universal action works anywhere on the map and provides a quick way to
    set the map to common scales without using the scale dropdown in the main interface.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        # Required properties
        self.action_id = "change_map_scale"
        self.name = "Change Map Scale"
        self.category = "Navigation"
        self.description = "Change the map scale to a predefined value. Opens a submenu with common scale options."
        self.enabled = True
        
        # Action scoping configuration - universal action
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])

        # Feature type support - canvas click (no feature required)
        # include 'universal' click type so action appears in general universal lists
        self.set_supported_click_types(['canvas', 'universal'])
        # support canvas geometry and universal placeholder
        self.set_supported_geometry_types(['canvas', 'universal'])
        
        # Initialize canvas reference
        self._current_canvas = None
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'show_scale_labels': {
                'type': 'bool',
                'default': True,
                'label': 'Show Scale Labels',
                'description': 'Show descriptive labels for each scale option',
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
    
    def create_scale_submenu(self, context):
        """
        Create a submenu with scale options.
        
        Args:
            context (dict): Action context
            
        Returns:
            QMenu: Submenu with scale options
        """
        # Create submenu
        submenu = QMenu("Select Map Scale")
        
        # Get settings with proper type conversion
        try:
            show_scale_labels = bool(self.get_setting('show_scale_labels', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return submenu
        
        # Predefined scales with descriptive labels
        predefined_scales = {
            "1:500": {
                'scale': 500,
                'label': 'Very Detailed (Building Level)'
            },
            "1:1,000": {
                'scale': 1000,
                'label': 'Detailed (Street Level)'
            },
            "1:2,000": {
                'scale': 2000,
                'label': 'Local Area'
            },
            "1:5,000": {
                'scale': 5000,
                'label': 'Neighborhood'
            },
            "1:10,000": {
                'scale': 10000,
                'label': 'District'
            },
            "1:25,000": {
                'scale': 25000,
                'label': 'Town/City'
            },
            "1:50,000": {
                'scale': 50000,
                'label': 'Large City'
            },
            "1:100,000": {
                'scale': 100000,
                'label': 'Regional'
            },
            "1:250,000": {
                'scale': 250000,
                'label': 'County/Province'
            },
            "1:500,000": {
                'scale': 500000,
                'label': 'State/Large Region'
            },
            "1:1,000,000": {
                'scale': 1000000,
                'label': 'Country'
            },
            "1:5,000,000": {
                'scale': 5000000,
                'label': 'Continental'
            },
            "1:10,000,000": {
                'scale': 10000000,
                'label': 'Global'
            }
        }
        
        # Add predefined scales to submenu
        for scale_text, scale_data in predefined_scales.items():
            scale_value = scale_data['scale']
            
            # Create action text based on settings
            if show_scale_labels:
                action_text = f"{scale_text} - {scale_data['label']}"
            else:
                action_text = scale_text
                
            # Create action
            scale_action = QAction(action_text, submenu)
            scale_action.triggered.connect(lambda checked=False, s=scale_value: self._on_scale_selected(s))
            submenu.addAction(scale_action)
        
        # No custom scales - only using predefined scales
        
        return submenu
    
    def set_map_scale(self, scale, canvas=None):
        """
        Set the map scale to the specified value.
        
        Args:
            scale (int): The denominator of the scale fraction (e.g., 1000 for 1:1000)
            canvas (QgsMapCanvas, optional): The map canvas to use. If None, will try to get from context.
        """
        try:
            # Use provided canvas or try to get from context/iface
            if not canvas:
                # Import iface at runtime to avoid import-time failures
                from qgis.utils import iface
                canvas = self._current_canvas or iface.mapCanvas()

            if not canvas:
                self.show_error("Error", "Could not access map canvas")
                return

            # Set the scale
            canvas.zoomScale(scale)

            # Refresh the map
            canvas.refresh()
        except Exception as e:
            self.show_error("Error", f"Failed to set map scale: {str(e)}")

    def _on_scale_selected(self, scale: int):
        """Handle scale selection: record history (view change) then apply."""
        try:
            # Import iface at runtime
            from qgis.utils import iface
            canvas = self._current_canvas or iface.mapCanvas()
            if not canvas:
                self.show_error("Error", "No canvas available for scale change")
                return

            # Capture previous view state
            try:
                prev_scale = float(canvas.scale())
            except Exception:
                prev_scale = None

            try:
                center_pt = canvas.center() if hasattr(canvas, 'center') else canvas.extent().center()
                prev_center = {'x': center_pt.x(), 'y': center_pt.y()}
            except Exception:
                prev_center = None

            # Apply new scale
            self.set_map_scale(scale, canvas)

            # Capture new view state for redo
            try:
                new_scale = float(canvas.scale())
            except Exception:
                new_scale = scale

            try:
                center_pt = canvas.center() if hasattr(canvas, 'center') else canvas.extent().center()
                new_center = {'x': center_pt.x(), 'y': center_pt.y()}
            except Exception:
                new_center = None

            # Record history entry for view change
            # Import history manager at runtime
            from ..history_manager import get_history_manager, HistoryManager
            hm = get_history_manager()
            undo_payload = {'scale': prev_scale, 'center': prev_center}
            redo_payload = {'scale': new_scale, 'center': new_center}

            try:
                hm.record(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Changed map scale to 1:{int(new_scale) if new_scale else scale}",
                    undo_type=HistoryManager.UNDO_TYPE_VIEW_CHANGE,
                    can_undo=True,
                    undo_payload=undo_payload,
                    redo_payload=redo_payload,
                    meta={'initiator': 'change_map_scale'}
                )
            except Exception:
                # Non-fatal: continue even if history recording fails
                pass

        except Exception as e:
            self.show_error("Error", f"Scale selection failed: {e}")
    
    def execute(self, context):
        """
        Execute the action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Store the canvas in the instance for use in set_map_scale
        self._current_canvas = context.get('canvas')
        if not self._current_canvas:
            self.show_error("Error", "No canvas available in context")
            return
            
        # Create submenu with scale options
        submenu = self.create_scale_submenu(context)
        
        # Show the submenu at the global cursor position
        cursor_pos = QCursor.pos()
        submenu.exec_(cursor_pos)


# REQUIRED: Create global instance for automatic discovery
change_map_scale_action = ChangeMapScaleAction()
