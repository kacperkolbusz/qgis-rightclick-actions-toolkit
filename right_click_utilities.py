"""
Right-click Utilities and Shortcuts Hub - Main Plugin Class

This module contains the main plugin class that handles right-click detection
on polygon features and displays a context menu with available options.
"""

from qgis.PyQt.QtWidgets import QAction, QMenu, QDialog, QVBoxLayout, QLabel, QPushButton
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsVectorLayer, QgsFeatureRequest, QgsRectangle,
    QgsWkbTypes, QgsGeometry, QgsPointXY, QgsSpatialIndex
)
from qgis.gui import QgsMapMouseEvent

from .action_registry import ActionRegistry
from .settings_dialog import SettingsDialog
from .feature_detector import FeatureDetector
from .context_menu_builder import ContextMenuBuilder
from .custom_menu_provider import CustomMenuProvider


class RightClickUtilities:
    """
    Main plugin class for Right-click Utilities and Shortcuts Hub.
    
    This plugin provides universal right-click functionality that works anywhere on the canvas.
    It automatically detects features at the cursor position and shows context-aware actions.
    
    Features:
    - Works on any visible vector layer (no layer selection required)
    - Detects points, multipoints, lines, multilines, polygons, and multipolygons automatically
    - Handles overlapping features with hierarchical menus
    - Extended search area for point and line features (10px tolerance)
    - Context-aware actions based on detected feature types
    - Backward compatibility with legacy polygon-only mode
    """
    
    # Class-level flag to track if plugin is already initialized
    _initialized = False
    
    def __init__(self, iface):
        """
        Initialize the plugin.
        
        Args:
            iface: QGIS interface instance
        """
        print(f"RightClickUtilities: Plugin instance created (ID: {id(self)})")
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None
        self.settings_action = None
        self.history_action = None
        self._gui_initialized = False
        
        # Initialize action registry
        self.action_registry = ActionRegistry()
        
        # Initialize new detection and menu building system
        self.feature_detector = FeatureDetector(self.canvas)
        self.context_menu_builder = ContextMenuBuilder(self.action_registry)
        
        # Initialize custom menu provider
        self.custom_menu_provider = CustomMenuProvider(self.context_menu_builder, self.iface, self.canvas)
        
        # Initialize history manager
        from .history_manager import get_history_manager
        self.history_manager = get_history_manager()
        
        # Legacy extension hooks (kept for backward compatibility)
        self._registered_actions = []
        self._context_callbacks = []
        
    def initGui(self):
        """
        Initialize the plugin GUI and connect signals.
        Called by QGIS when the plugin is enabled.
        """
        # Prevent duplicate initialization
        if self._gui_initialized:
            print("RightClickUtilities: GUI already initialized, skipping...")
            return
            
        print("RightClickUtilities: Initializing GUI...")
        
        # First, try to clean up any existing menu items (in case of reload)
        try:
            # This is a bit aggressive but should help with reload issues
            from qgis.PyQt.QtWidgets import QMenuBar
            menubar = self.iface.mainWindow().menuBar()
            for action in menubar.actions():
                if action.text() == "&Right-click Actions Toolkit":
                    # Found the menu, try to clear it
                    menu = action.menu()
                    if menu:
                        menu.clear()
                    break
        except Exception as e:
            print(f"RightClickUtilities: Error during cleanup: {e}")
        
        # Create main plugin action (this will be the menu entry)
        # Changed to directly open Configure Actions dialog for better UX
        self.action = QAction("Configure Actions", self.iface.mainWindow())
        self.action.triggered.connect(self.show_settings_dialog)
        self.iface.addPluginToMenu("&Right-click Actions Toolkit", self.action)
        
        # Create history manager action
        self.history_action = QAction("History Manager", self.iface.mainWindow())
        self.history_action.triggered.connect(self.show_history_dialog)
        self.iface.addPluginToMenu("&Right-click Actions Toolkit", self.history_action)
        
        # Add history manager to toolbar
        self.history_toolbar_action = QAction("RAT History", self.iface.mainWindow())
        self.history_toolbar_action.setToolTip("Open RAT History Manager - View and undo plugin actions")
        self.history_toolbar_action.triggered.connect(self.show_history_dialog)
        self.iface.addToolBarIcon(self.history_toolbar_action)
        
        # Remove the separate settings action since main action now opens settings directly
        self.settings_action = None
        
        # Mark as initialized
        self._gui_initialized = True
        print("RightClickUtilities: GUI initialization complete")
        
    def unload(self):
        """
        Clean up when the plugin is disabled.
        Called by QGIS when the plugin is disabled.
        """
        # Only unload if GUI was initialized
        if not self._gui_initialized:
            print("RightClickUtilities: GUI not initialized, skipping unload...")
            return
            
        print("RightClickUtilities: Unloading GUI...")
        
        # Remove the plugin actions
        if self.action is not None:
            self.iface.removePluginMenu("&Right-click Actions Toolkit", self.action)
            self.action = None
        
        # Remove history action from menu
        if self.history_action is not None:
            self.iface.removePluginMenu("&Right-click Actions Toolkit", self.history_action)
            self.history_action = None
        
        # Remove history toolbar action
        if hasattr(self, 'history_toolbar_action') and self.history_toolbar_action is not None:
            self.iface.removeToolBarIcon(self.history_toolbar_action)
            self.history_toolbar_action = None
            
        # settings_action is now None, so no need to remove it
            
        # Clean up custom menu provider
        if hasattr(self, 'custom_menu_provider') and self.custom_menu_provider is not None:
            self.custom_menu_provider.cleanup()
        
        # Save history before unloading
        if hasattr(self, 'history_manager') and self.history_manager is not None:
            self.history_manager.save_to_disk()
        
        # Clean up history panel
        from .history_dialog import destroy_history_panel
        destroy_history_panel()
        
        # Clear registered actions
        self._registered_actions.clear()
        self._context_callbacks.clear()
        
        # Mark as not initialized
        self._gui_initialized = False
        print("RightClickUtilities: GUI unload complete")
    
    def show_history_dialog(self):
        """
        Show or toggle the History Manager panel.
        """
        from .history_dialog import get_history_panel
        
        panel = get_history_panel(self.iface)
        
        # Add dock widget to main window if not already added
        if not panel._added_to_main_window:
            self.iface.addDockWidget(Qt.RightDockWidgetArea, panel)
            panel._added_to_main_window = True
            panel.show()
        else:
            # Toggle visibility
            if panel.isVisible():
                panel.hide()
            else:
                panel.show()
                panel.raise_()
    
    def _populate_legacy_context_menu(self, menu, event):
        """
        Legacy context menu population for backward compatibility.
        Only works with active polygon layers.
        
        Args:
            menu (QMenu): The context menu to populate
            event (QgsMapMouseEvent): The mouse event containing click coordinates
        """
        # 1) Check active layer (only when user has selected the layer in the Layers panel)
        layer = self.iface.activeLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            return  # Not a vector layer — do nothing
            
        # 2) Only polygon layers
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            return
            
        # 3) Get clicked point in map coordinates
        click_pt = event.mapPoint()  # QgsPointXY
        
        # 4) Tolerance: convert a few pixels into map units for feature query
        tol_pixels = 5  # Adjustable tolerance in pixels
        tol_mapunits = tol_pixels * self.canvas.mapUnitsPerPixel()
        
        # Create search rectangle around click point
        rect = QgsRectangle(
            click_pt.x() - tol_mapunits, click_pt.y() - tol_mapunits,
            click_pt.x() + tol_mapunits, click_pt.y() + tol_mapunits
        )
        
        # 5) Find features that contain or intersect the clicked point
        found_feature = self._find_clicked_feature(layer, click_pt, rect)
        
        if found_feature:
            # Create context object
            context = {
                'feature': found_feature,
                'layer': layer,
                'canvas': self.canvas,
                'map_point': click_pt
            }
            
            # Get enabled actions from registry
            enabled_actions = self.action_registry.get_enabled_actions()
            
            if enabled_actions:
                # Add actions from registry directly to main menu
                self._add_registry_actions(menu, enabled_actions, context)
                
                # Add legacy registered actions (for backward compatibility)
                self._add_registered_actions(menu, found_feature, layer, click_pt)
                
                # Add default placeholder action if no actions are available
                if not enabled_actions and not self._registered_actions:
                    placeholder_action = menu.addAction('No actions available')
                    placeholder_action.setEnabled(False)
                
    def _find_clicked_feature(self, layer, click_pt, search_rect):
        """
        Find the feature that contains the clicked point.
        
        Args:
            layer (QgsVectorLayer): The layer to search in
            click_pt (QgsPointXY): The clicked point
            search_rect (QgsRectangle): Search rectangle for initial filtering
            
        Returns:
            QgsFeature or None: The feature containing the point, or None if not found
        """
        # Use spatial index for better performance on large layers
        if layer.featureCount() > 1000:
            return self._find_feature_with_spatial_index(layer, click_pt, search_rect)
        else:
            return self._find_feature_simple(layer, click_pt, search_rect)
            
    def _find_feature_simple(self, layer, click_pt, search_rect):
        """
        Simple feature search for smaller layers.
        
        Args:
            layer (QgsVectorLayer): The layer to search in
            click_pt (QgsPointXY): The clicked point
            search_rect (QgsRectangle): Search rectangle
            
        Returns:
            QgsFeature or None: The feature containing the point
        """
        # Request candidate features using bounding box filter
        req = QgsFeatureRequest().setFilterRect(search_rect)
        
        for feature in layer.getFeatures(req):
            geometry = feature.geometry()
            if not geometry:
                continue
                
            # Create point geometry for the check
            pt_geom = QgsGeometry.fromPointXY(click_pt)
            
            try:
                # Check if the feature contains or intersects the clicked point
                if geometry.contains(pt_geom) or geometry.intersects(pt_geom):
                    return feature
            except Exception:
                # Handle geometry validity issues gracefully
                continue
                
        return None
        
    def _find_feature_with_spatial_index(self, layer, click_pt, search_rect):
        """
        Feature search using spatial index for better performance on large layers.
        
        Args:
            layer (QgsVectorLayer): The layer to search in
            click_pt (QgsPointXY): The clicked point
            search_rect (QgsRectangle): Search rectangle
            
        Returns:
            QgsFeature or None: The feature containing the point
        """
        try:
            # Build spatial index
            spatial_index = QgsSpatialIndex(layer.getFeatures())
            
            # Query spatial index for candidate features
            candidate_fids = spatial_index.intersects(search_rect)
            
            if not candidate_fids:
                return None
                
            # Get features by their IDs
            req = QgsFeatureRequest().setFilterFids(candidate_fids)
            pt_geom = QgsGeometry.fromPointXY(click_pt)
            
            for feature in layer.getFeatures(req):
                geometry = feature.geometry()
                if not geometry:
                    continue
                    
                try:
                    if geometry.contains(pt_geom) or geometry.intersects(pt_geom):
                        return feature
                except Exception:
                    continue
                    
        except Exception:
            # Fallback to simple search if spatial index fails
            return self._find_feature_simple(layer, click_pt, search_rect)
            
        return None
        
    def _add_registry_actions(self, menu, enabled_actions, context):
        """
        Add actions from the registry to the context menu.
        
        Args:
            menu (QMenu): The menu to add actions to
            enabled_actions (list): List of enabled BaseAction instances
            context (dict): Context containing feature, layer, canvas, and map_point
        """
        # Group actions by category
        categories = {}
        for action in enabled_actions:
            category = action.category or 'Other'
            if category not in categories:
                categories[category] = []
            categories[category].append(action)
        
        # Add actions grouped by category
        for category, actions in categories.items():
            if len(categories) > 1:
                # Create submenu for category
                category_menu = menu.addMenu(category)
                for action in actions:
                    action_item = category_menu.addAction(action.name)
                    action_item.triggered.connect(
                        lambda checked, action_obj=action: action_obj.execute(context)
                    )
            else:
                # Add actions directly to main menu
                for action in actions:
                    action_item = menu.addAction(action.name)
                    action_item.triggered.connect(
                        lambda checked, action_obj=action: action_obj.execute(context)
                    )
        
    def _add_registered_actions(self, menu, feature, layer, click_pt):
        """
        Add registered actions to the context menu.
        
        Args:
            menu (QMenu): The menu to add actions to
            feature (QgsFeature): The clicked feature
            layer (QgsVectorLayer): The active layer
            click_pt (QgsPointXY): The clicked point
        """
        for action_info in self._registered_actions:
            action = menu.addAction(action_info['name'])
            action.triggered.connect(
                lambda checked, info=action_info: info['callback'](feature, layer, click_pt)
            )
            
    def _show_placeholder_dialog(self, feature, layer):
        """
        Show a placeholder dialog for future functionality.
        
        Args:
            feature (QgsFeature): The clicked feature
            layer (QgsVectorLayer): The active layer
        """
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('Right-click Utilities - Options')
        dialog.setModal(True)
        dialog.resize(400, 200)
        
        layout = QVBoxLayout()
        
        # Add information about the clicked feature
        info_label = QLabel(f"Feature ID: {feature.id()}")
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        layer_label = QLabel(f"Layer: {layer.name()}")
        layout.addWidget(layer_label)
        
        # Placeholder content
        placeholder_label = QLabel("This is a placeholder dialog.\nFuture functionality will be added here.")
        placeholder_label.setStyleSheet("color: #666; font-style: italic; margin: 20px 0;")
        layout.addWidget(placeholder_label)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        
        dialog.setLayout(layout)
        dialog.exec_()
        
    def show_settings_dialog(self):
        """
        Show the settings dialog for configuring actions.
        """
        dialog = SettingsDialog(self.action_registry, self.iface.mainWindow())
        if dialog.exec_() == QDialog.Accepted:
            dialog.apply_settings()
            self.iface.messageBar().pushMessage(
                "Right-click Utilities",
                "Settings saved successfully.",
                duration=2
            )
    
    def run(self):
        """
        Run method that can be called manually.
        Shows information about the plugin and available actions.
        """
        # Get enabled actions count
        enabled_actions = self.action_registry.get_enabled_actions()
        action_count = len(enabled_actions)
        
        # Create action list
        action_names = [action.name for action in enabled_actions]
        action_list = ", ".join(action_names) if action_names else "None"
        
        message = f"Right-click Utilities is active!\n\n"
        message += f"NEW: Custom Context Menu!\n"
        message += f"- Hides built-in 'Copy Coordinates' by default for cleaner interface\n"
        message += f"- Toggle 'Copy Coordinates' in General Settings if needed\n\n"
        message += f"Universal Detection System:\n"
        message += f"- Works anywhere on canvas (no layer selection required)\n"
        message += f"- Detects points, multipoints, lines, multilines, polygons, multipolygons\n"
        message += f"- Handles overlapping features with hierarchical menus\n"
        message += f"- Extended search area for points and lines (10px)\n"
        message += f"- Easy clicking - no need to click exactly on features!\n\n"
        message += f"Enabled actions ({action_count}): {action_list}\n\n"
        message += "Right-click anywhere on the canvas to test the new detection system!\n"
        message += "Use 'Configure Actions...' to enable/disable actions and customize the context menu."
        
        self.iface.messageBar().pushMessage(
            "Right-click Utilities",
            message,
            duration=10
        )
        
    # Extension hooks for future functionality
    
    def register_action(self, action_id, name, callback, enabled=True, category=None, description=""):
        """
        Register a new action in the action registry.
        
        Args:
            action_id (str): Unique identifier for the action
            name (str): Display name for the action
            callback (callable): Function to call when action is triggered.
                               Should accept a context dictionary parameter.
            enabled (bool): Whether the action is enabled by default
            category (str): Optional category for grouping actions
            description (str): Optional description of the action
        """
        self.action_registry.register_action(action_id, name, callback, enabled, category, description)
    
    def register_legacy_action(self, name, callback):
        """
        Register a new action using the legacy system (for backward compatibility).
        
        Args:
            name (str): Display name for the action
            callback (callable): Function to call when action is triggered.
                               Should accept (feature, layer, click_pt) parameters.
        """
        self._registered_actions.append({
            'name': name,
            'callback': callback
        })
        
    def register_context_callback(self, callback):
        """
        Register a callback that will be called when a polygon is right-clicked.
        
        Args:
            callback (callable): Function to call with context information.
                               Should accept (feature, layer, click_pt, menu) parameters.
        """
        self._context_callbacks.append(callback)
        
    def get_registered_actions(self):
        """
        Get list of registered actions.
        
        Returns:
            list: List of registered action dictionaries
        """
        return self._registered_actions.copy()
        
    def clear_registered_actions(self):
        """
        Clear all registered actions.
        """
        self._registered_actions.clear()
