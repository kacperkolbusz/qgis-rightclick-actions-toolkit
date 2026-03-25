"""
Custom Menu Provider for Right-click Utilities and Shortcuts Hub

This module provides a custom menu provider that controls the right-click context menu
in QGIS, allowing the plugin to hide built-in options like "Copy Coordinates" by default
while providing a setting to restore them.
"""

from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtCore import QSettings, QMimeData, Qt, QPoint
from qgis.PyQt.QtGui import QClipboard
from qgis.core import QgsPointXY, QgsApplication
from qgis.gui import QgsMapMouseEvent


class CustomMenuProvider:
    """
    Custom menu provider that controls the right-click context menu.
    
    Features:
    - Hide built-in QGIS context menu items by default
    - Show "Copy Coordinates" option based on user settings
    - Integrate with the plugin's action system
    - Provide clean, focused context menu experience
    """
    
    def __init__(self, context_menu_builder, iface, canvas):
        """
        Initialize the custom menu provider.
        
        Args:
            context_menu_builder: ContextMenuBuilder instance for building plugin menus
            iface: QGIS interface instance
            canvas: QGIS map canvas instance
        """
        self.context_menu_builder = context_menu_builder
        self.iface = iface
        self.canvas = canvas
        self.settings = QSettings()
        
        # Connect to the context menu signal to intercept and modify it
        self.canvas.contextMenuAboutToShow.connect(self.modify_context_menu)
        
    def modify_context_menu(self, menu, event):
        """
        Modify the QGIS context menu to hide Copy Coordinates by default and add plugin actions.
        
        Args:
            menu: QGIS context menu to modify
            event: Mouse event containing click coordinates
        """
        # Check if Copy Coordinates should be shown
        show_copy_coords = self.settings.value('rightclick_utilities/show_copy_coordinates', False, type=bool)
        
        # Remove all existing actions from the menu
        menu.clear()
        
        if show_copy_coords:
            # Add the built-in Copy Coordinates action
            copy_coords_action = QAction("Copy Coordinates", menu)
            copy_coords_action.triggered.connect(
                lambda: self._copy_coordinates_from_event(event)
            )
            menu.addAction(copy_coords_action)
            menu.addSeparator()
        
        # Build the plugin's context menu using the existing system
        try:
            # Get click context using the feature detector
            from .feature_detector import FeatureDetector
            feature_detector = FeatureDetector(self.canvas)
            context = feature_detector.get_click_context(event)
            
            # Add canvas and other context information
            context['canvas'] = self.canvas
            context['iface'] = self.iface
            
            # Build context menu using the existing system
            menu_added = self.context_menu_builder.build_context_menu(menu, context)
            
            if not menu_added:
                # Add a placeholder if no actions are available
                placeholder_action = menu.addAction("Right-click Utilities")
                placeholder_action.setEnabled(False)
                
        except Exception as e:
            print(f"Error building context menu: {e}")
            # Add fallback menu item
            fallback_action = menu.addAction("Right-click Utilities (Error)")
            fallback_action.setEnabled(False)
    
    
    def _copy_coordinates_from_event(self, event):
        """
        Copy coordinates to clipboard (built-in QGIS functionality).
        
        Args:
            event: QgsMapMouseEvent containing click coordinates
        """
        try:
            print("Copy Coordinates: Starting coordinate copy...")
            
            # Get the clicked point in map coordinates
            map_point = event.mapPoint()
            print(f"Copy Coordinates: Map point: {map_point}")
            
            # Format coordinates for clipboard
            x = map_point.x()
            y = map_point.y()
            print(f"Copy Coordinates: X={x}, Y={y}")
            
            # Get current CRS for display
            crs = self.canvas.mapSettings().destinationCrs()
            crs_authid = crs.authid()
            print(f"Copy Coordinates: CRS: {crs_authid}")
            
            # Create coordinate text (matching QGIS format)
            coord_text = f"{x:.6f}, {y:.6f}"
            if crs_authid:
                coord_text += f" ({crs_authid})"
            
            print(f"Copy Coordinates: Text to copy: {coord_text}")
            
            # Use QGIS clipboard functionality
            clipboard = QgsApplication.clipboard()
            clipboard.setText(coord_text)
            print("Copy Coordinates: Text copied to clipboard successfully")
            
            # Show feedback to user
            self.iface.messageBar().pushMessage(
                "Copy Coordinates",
                f"Coordinates copied to clipboard: {coord_text}",
                duration=2
            )
            
        except Exception as e:
            print(f"Error copying coordinates: {e}")
            import traceback
            traceback.print_exc()
            self.iface.messageBar().pushMessage(
                "Copy Coordinates",
                f"Error copying coordinates to clipboard: {str(e)}",
                duration=3
            )
    
    def cleanup(self):
        """
        Clean up the custom menu provider.
        """
        try:
            self.canvas.contextMenuAboutToShow.disconnect(self.modify_context_menu)
        except Exception as e:
            print(f"Error cleaning up custom menu provider: {e}")
