"""
Calculate Line Bearing/Azimuth Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the bearing/azimuth of line features.
For polylines, calculates the bearing of the segment closest to the click point.
For simple lines, calculates bearing from first to last vertex.
Shows bearing in degrees (0° = North, 90° = East, 180° = South, 270° = West).
"""

from .base_action import BaseAction
from qgis.core import QgsWkbTypes, QgsPointXY, QgsGeometry
import math


class CalculateLineBearingAction(BaseAction):
    """
    Action to calculate and display line bearing/azimuth.
    
    This action calculates the bearing (azimuth) of a line feature from its first vertex
    to its last vertex. Bearing is displayed in degrees with 0° = North, 90° = East,
    180° = South, 270° = West.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_line_bearing"
        self.name = "Calculate Line Bearing/Azimuth"
        self.category = "Analysis"
        self.description = "Calculate and display the bearing/azimuth of the selected line feature. For polylines, calculates the bearing of the segment closest to the click point. For simple lines, calculates bearing from first to last vertex. Shows bearing in degrees (0° = North, 90° = East, 180° = South, 270° = West). Displays result in information dialog with customizable formatting options."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # DISPLAY SETTINGS - Easy to customize output format
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in bearing calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature ID',
                'description': 'Display the feature ID in the result dialog',
            },
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Display the layer name in the result dialog',
            },
            'show_start_end_coordinates': {
                'type': 'bool',
                'default': True,
                'label': 'Show Start/End Coordinates',
                'description': 'Display the start and end point coordinates of the segment in the result dialog',
            },
            'show_segment_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Segment Information',
                'description': 'Display segment number and total segments for polylines',
            },
            'show_line_length': {
                'type': 'bool',
                'default': True,
                'label': 'Show Line Length',
                'description': 'Display the line length in the result dialog',
            },
            'show_cardinal_direction': {
                'type': 'bool',
                'default': True,
                'label': 'Show Cardinal Direction',
                'description': 'Display cardinal direction (N, NE, E, SE, S, SW, W, NW) in addition to degrees',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result dialog',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a brief success message after calculation',
            },
            'copy_to_clipboard': {
                'type': 'bool',
                'default': False,
                'label': 'Copy to Clipboard',
                'description': 'Copy the bearing value to clipboard for easy pasting',
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
    
    def calculate_bearing(self, start_point, end_point):
        """
        Calculate bearing from start point to end point.
        
        Args:
            start_point (QgsPointXY): Starting point
            end_point (QgsPointXY): Ending point
            
        Returns:
            float: Bearing in degrees (0° = North, 90° = East, 180° = South, 270° = West)
        """
        # Calculate differences
        delta_x = end_point.x() - start_point.x()
        delta_y = end_point.y() - start_point.y()
        
        # Calculate bearing using atan2
        # atan2(delta_x, delta_y) gives angle from North (0° = North, 90° = East)
        bearing_rad = math.atan2(delta_x, delta_y)
        
        # Convert to degrees
        bearing_deg = math.degrees(bearing_rad)
        
        # Normalize to 0-360 range
        if bearing_deg < 0:
            bearing_deg += 360.0
        
        return bearing_deg
    
    def get_cardinal_direction(self, bearing):
        """
        Get cardinal direction from bearing.
        
        Args:
            bearing (float): Bearing in degrees
            
        Returns:
            str: Cardinal direction (N, NE, E, SE, S, SW, W, NW)
        """
        # Normalize bearing to 0-360
        bearing = bearing % 360.0
        
        # Determine cardinal direction
        if bearing >= 337.5 or bearing < 22.5:
            return "N"
        elif bearing >= 22.5 and bearing < 67.5:
            return "NE"
        elif bearing >= 67.5 and bearing < 112.5:
            return "E"
        elif bearing >= 112.5 and bearing < 157.5:
            return "SE"
        elif bearing >= 157.5 and bearing < 202.5:
            return "S"
        elif bearing >= 202.5 and bearing < 247.5:
            return "SW"
        elif bearing >= 247.5 and bearing < 292.5:
            return "W"
        else:  # 292.5 to 337.5
            return "NW"
    
    def find_closest_segment(self, geometry, click_point):
        """
        Find the segment of a polyline closest to the click point.
        
        Args:
            geometry (QgsGeometry): Line geometry
            click_point (QgsPointXY): Click point coordinates
            
        Returns:
            tuple: (start_point, end_point, segment_index, total_segments) or None if not found
        """
        # Get all vertices and convert to QgsPointXY
        vertices = geometry.vertices()
        vertex_list = []
        for vertex in vertices:
            # Convert QgsPoint to QgsPointXY
            vertex_list.append(QgsPointXY(vertex.x(), vertex.y()))
        
        if len(vertex_list) < 2:
            return None
        
        # If only 2 vertices, return the single segment
        if len(vertex_list) == 2:
            return (vertex_list[0], vertex_list[1], 0, 1)
        
        # For polylines, find the closest segment
        closest_segment = None
        closest_distance = float('inf')
        segment_index = 0
        
        # Create a point geometry from click point for distance calculations
        click_point_geom = QgsGeometry.fromPointXY(click_point)
        
        for i in range(len(vertex_list) - 1):
            start_vertex = vertex_list[i]
            end_vertex = vertex_list[i + 1]
            
            # Create a line segment geometry
            segment_geometry = QgsGeometry.fromPolylineXY([start_vertex, end_vertex])
            
            # Calculate distance from click point to segment
            distance = click_point_geom.distance(segment_geometry)
            
            if distance < closest_distance:
                closest_distance = distance
                closest_segment = (start_vertex, end_vertex, i, len(vertex_list) - 1)
        
        return closest_segment
    
    def execute(self, context):
        """
        Execute the calculate line bearing action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_feature_id = bool(self.get_setting('show_feature_id', True))
            show_layer_name = bool(self.get_setting('show_layer_name', True))
            show_start_end_coords = bool(self.get_setting('show_start_end_coordinates', True))
            show_line_length = bool(self.get_setting('show_line_length', True))
            show_cardinal = bool(self.get_setting('show_cardinal_direction', True))
            show_crs_info = bool(self.get_setting('show_crs_info', False))
            show_segment_info = bool(self.get_setting('show_segment_info', True))
            show_success_message = bool(self.get_setting('show_success_message', False))
            copy_to_clipboard = bool(self.get_setting('copy_to_clipboard', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        click_point = context.get('click_point')
        
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
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
            
            # Validate that this is a line feature
            if geometry.type() != QgsWkbTypes.LineGeometry:
                self.show_error("Error", "This action only works with line features")
                return
            
            # Get vertices of the line and convert to QgsPointXY
            vertices = geometry.vertices()
            vertex_list = []
            for vertex in vertices:
                # Convert QgsPoint to QgsPointXY
                vertex_list.append(QgsPointXY(vertex.x(), vertex.y()))
            
            if len(vertex_list) < 2:
                self.show_error("Error", "Line must have at least 2 vertices to calculate bearing")
                return
            
            # Determine if this is a polyline (more than 2 vertices)
            is_polyline = len(vertex_list) > 2
            
            # Find the segment to calculate bearing for
            segment_info = None
            start_point = None
            end_point = None
            segment_index = 0
            total_segments = 1
            
            if is_polyline and click_point:
                # For polylines, find the segment closest to the click point
                segment_info = self.find_closest_segment(geometry, click_point)
                if segment_info:
                    start_point, end_point, segment_index, total_segments = segment_info
                else:
                    # Fallback to first segment if finding failed
                    start_point = vertex_list[0]
                    end_point = vertex_list[1]
                    segment_index = 0
                    total_segments = len(vertex_list) - 1
            else:
                # For simple lines or if no click point, use first to last vertex
                start_point = vertex_list[0]
                end_point = vertex_list[-1]
                segment_index = 0
                total_segments = 1
            
            # Calculate bearing
            bearing = self.calculate_bearing(start_point, end_point)
            
            # Format the bearing value
            bearing_formatted = f"{bearing:.{decimal_places}f}°"
            
            # Build result message
            result_lines = []
            
            if show_feature_id:
                result_lines.append(f"Feature ID: {feature.id()}")
            
            if show_layer_name:
                result_lines.append(f"Layer: {layer.name()}")
            
            if show_segment_info and is_polyline and total_segments > 1:
                result_lines.append(f"Segment: {segment_index + 1} of {total_segments}")
            
            result_lines.append(f"Bearing/Azimuth: {bearing_formatted}")
            
            if show_cardinal:
                cardinal = self.get_cardinal_direction(bearing)
                result_lines.append(f"Direction: {cardinal}")
            
            if show_start_end_coords:
                result_lines.append("")
                result_lines.append(f"Segment Start: ({start_point.x():.6f}, {start_point.y():.6f})")
                result_lines.append(f"Segment End: ({end_point.x():.6f}, {end_point.y():.6f})")
            
            if show_line_length:
                try:
                    length = geometry.length()
                    result_lines.append(f"Line Length: {length:.2f} map units")
                except Exception:
                    pass
            
            if show_crs_info:
                crs = layer.crs()
                result_lines.append(f"CRS: {crs.description()}")
            
            result_text = "\n".join(result_lines)

            # Show result
            self.show_info("Bearing/Azimuth Calculation", result_text)

            # Record informational entry in history (no undo) for audit purposes
            try:
                from ..history_manager import get_history_manager
                hm = get_history_manager()
                meta = {
                    'feature_id': feature.id(),
                    'layer_id': layer.id() if hasattr(layer, 'id') else None,
                    'layer_name': layer.name() if hasattr(layer, 'name') else None,
                    'bearing': float(bearing),
                    'bearing_formatted': bearing_formatted,
                    'is_polyline': is_polyline,
                    'segment_index': int(segment_index),
                    'total_segments': int(total_segments)
                }
                description = f"Calculated bearing {bearing_formatted} for feature {feature.id()} on layer {layer.name()}"
                hm.record_informational(self.action_id, self.name, description, meta=meta)
            except Exception:
                # History manager not available or failed -> silently continue
                pass

            # Copy to clipboard if requested
            if copy_to_clipboard:
                from qgis.PyQt.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(bearing_formatted)

            # Show success message if requested
            if show_success_message:
                cardinal_text = f" ({self.get_cardinal_direction(bearing)})" if show_cardinal else ""
                self.show_info("Success", f"Bearing calculated successfully: {bearing_formatted}{cardinal_text}")
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate bearing: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_line_bearing = CalculateLineBearingAction()

