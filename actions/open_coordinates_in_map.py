"""
Open Coordinates in Map Service Action for Right-click Utilities and Shortcuts Hub

Opens the clicked location's coordinates in a web map service (Google Maps, OpenStreetMap, etc.).
Works universally on any click location, transforming coordinates to WGS84 for map services.
"""

from .base_action import BaseAction
import webbrowser
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject


class OpenCoordinatesInMapAction(BaseAction):
    """Action to open coordinates in a web map service."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "open_coordinates_in_map"
        self.name = "Open Coordinates in Map"
        self.category = "Navigation"
        self.description = "Open the clicked location's coordinates in a web map service (Google Maps, OpenStreetMap, Bing Maps, etc.). Works universally on any click location. Automatically transforms coordinates to WGS84 for map services. Choose your preferred map service in settings."
        self.enabled = True
        
        # Action scoping - universal action works everywhere
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - works everywhere
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['point', 'multipoint', 'line', 'multiline', 'polygon', 'multipolygon', 'canvas'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # MAP SERVICE SETTINGS - Easy to customize map service
            'map_service': {
                'type': 'choice',
                'default': 'Google Maps',
                'label': 'Map Service',
                'description': 'Web map service to use for opening coordinates',
                'options': [
                    'Google Maps',
                    'OpenStreetMap',
                    'Bing Maps',
                    'Mapbox',
                    'Yandex Maps',
                    'Apple Maps',
                    'Here WeGo',
                    'Baidu Maps'
                ],
            },
            'zoom_level': {
                'type': 'int',
                'default': 15,
                'label': 'Default Zoom Level',
                'description': 'Default zoom level for map (1-20, where 1 is world view and 20 is street level)',
                'min': 1,
                'max': 20,
                'step': 1,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_coordinates': {
                'type': 'bool',
                'default': True,
                'label': 'Show Coordinates',
                'description': 'Display the coordinates that will be opened in a message before opening',
            },
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a success message after opening the map',
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
    
    def _build_map_url(self, lat, lon, map_service, zoom_level):
        """
        Build the URL for the selected map service.
        
        Args:
            lat (float): Latitude in WGS84
            lon (float): Longitude in WGS84
            map_service (str): Name of the map service
            zoom_level (int): Zoom level (1-20)
            
        Returns:
            str: URL to open in browser
        """
        # Clamp zoom level to valid range
        zoom = max(1, min(20, zoom_level))
        
        # Build URL based on map service
        if map_service == 'Google Maps':
            return f"https://www.google.com/maps?q={lat},{lon}&z={zoom}"
        elif map_service == 'OpenStreetMap':
            return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom={zoom}"
        elif map_service == 'Bing Maps':
            return f"https://www.bing.com/maps?cp={lat}~{lon}&lvl={zoom}"
        elif map_service == 'Mapbox':
            # Mapbox URL format (note: may require API key for full functionality)
            return f"https://www.mapbox.com/maps?lat={lat}&lon={lon}&zoom={zoom}"
        elif map_service == 'Yandex Maps':
            return f"https://yandex.com/maps/?pt={lon},{lat}&z={zoom}"
        elif map_service == 'Apple Maps':
            return f"https://maps.apple.com/?ll={lat},{lon}&z={zoom}"
        elif map_service == 'Here WeGo':
            return f"https://wego.here.com/?map={lat},{lon},{zoom},normal"
        elif map_service == 'Baidu Maps':
            return f"https://map.baidu.com/?newmap=1&ie=utf-8&s=s%26wd%3D{lat}%2C{lon}"
        else:
            # Default to Google Maps
            return f"https://www.google.com/maps?q={lat},{lon}&z={zoom}"
    
    def execute(self, context):
        """Execute the open coordinates in map action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            map_service = str(self.get_setting('map_service', schema['map_service']['default']))
            zoom_level = int(self.get_setting('zoom_level', schema['zoom_level']['default']))
            show_coordinates = bool(self.get_setting('show_coordinates', schema['show_coordinates']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        click_point = context.get('click_point')
        canvas = context.get('canvas')
        
        if not click_point:
            self.show_error("Error", "No click point available")
            return
        
        if not canvas:
            self.show_error("Error", "Map canvas not available")
            return
        
        try:
            # Get canvas CRS
            canvas_crs = canvas.mapSettings().destinationCrs()
            
            # Transform to WGS84 (EPSG:4326) for map services
            wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            
            # Get coordinates in canvas CRS
            x = click_point.x()
            y = click_point.y()
            
            # Transform to WGS84 if needed
            if canvas_crs != wgs84_crs:
                try:
                    transform = QgsCoordinateTransform(canvas_crs, wgs84_crs, QgsProject.instance())
                    transformed_point = transform.transform(x, y)
                    lon = transformed_point.x()
                    lat = transformed_point.y()
                except Exception as e:
                    self.show_error("Error", f"Failed to transform coordinates to WGS84: {str(e)}")
                    return
            else:
                # Already in WGS84
                lon = x
                lat = y
            
            # Validate coordinates (WGS84 bounds)
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                self.show_error("Error", f"Invalid coordinates: Longitude {lon:.6f}, Latitude {lat:.6f}")
                return
            
            # Build map URL
            map_url = self._build_map_url(lat, lon, map_service, zoom_level)
            
            # Show coordinates if requested
            if show_coordinates:
                coord_text = f"Opening coordinates in {map_service}:\n\n"
                coord_text += f"Latitude: {lat:.6f}\n"
                coord_text += f"Longitude: {lon:.6f}\n"
                coord_text += f"Zoom Level: {zoom_level}"
                self.show_info("Opening Map", coord_text)
            
            # Open URL in browser
            try:
                webbrowser.open(map_url)
                
                if show_success_message:
                    self.show_info("Success", f"Opened {map_service} in your browser.")
            except Exception as e:
                self.show_error("Error", f"Failed to open browser: {str(e)}")
            
        except Exception as e:
            self.show_error("Error", f"Failed to open coordinates in map: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
open_coordinates_in_map_action = OpenCoordinatesInMapAction()

