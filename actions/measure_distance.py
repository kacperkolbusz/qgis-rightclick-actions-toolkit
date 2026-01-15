"""
Measure Distance Action for Right-click Utilities and Shortcuts Hub

Interactive distance measurement with X marker visualization.
Right-click to start measurement, then move mouse to see real-time distance dynamically.
Right-click again to complete measurement and show final result.
Press Escape to cancel measurement.
Works universally on any canvas location with proper CRS handling.
"""

from .base_action import BaseAction


class MeasureDistanceAction(BaseAction):
    """Action to measure distance with X marker visualization."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "measure_distance"
        self.name = "Measure Distance"
        self.category = "Analysis"
        self.description = "Interactive distance measurement with X marker visualization. Right-click to start, move mouse to see real-time distance dynamically, right-click again to complete measurement. Shows X marker at start point with live distance updates and proper CRS handling."
        self.enabled = True
        
        # Action scoping - this works universally
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
            'show_instruction_popup': {
                'type': 'bool',
                'default': False,
                'label': 'Show Instruction Popup',
                'description': 'Display initial popup with instructions when starting measurement',
            },
            'show_final_measurement': {
                'type': 'bool',
                'default': False,
                'label': 'Show Final Measurement Dialog',
                'description': 'Display measurement result dialog after completing measurement',
            },
            
            # X MARKER SETTINGS
            'marker_color': {
                'type': 'color',
                'default': '#FF0000',
                'label': 'Marker Color',
                'description': 'Color for the start point X marker and distance label',
            },
            'marker_size': {
                'type': 'int',
                'default': 8,
                'label': 'Marker Size',
                'description': 'Size of the X marker in pixels',
                'min': 4,
                'max': 20,
                'step': 1,
            },
            'marker_width': {
                'type': 'int',
                'default': 3,
                'label': 'Marker Line Width',
                'description': 'Width of the X marker lines in pixels',
                'min': 1,
                'max': 8,
                'step': 1,
            },
            
            # DISTANCE LABEL SETTINGS
            'show_distance_label': {
                'type': 'bool',
                'default': True,
                'label': 'Show Distance Label',
                'description': 'Display distance label next to the mouse cursor',
            },
            'label_font_size': {
                'type': 'int',
                'default': 10,
                'label': 'Label Font Size',
                'description': 'Font size for the distance label',
                'min': 8,
                'max': 20,
                'step': 1,
            },
            'label_background': {
                'type': 'bool',
                'default': True,
                'label': 'Label Background',
                'description': 'Show background behind the distance label for better readability',
            },
            
            # PERFORMANCE SETTINGS
            'update_sensitivity': {
                'type': 'float',
                'default': 0.1,
                'label': 'Update Sensitivity',
                'description': 'Minimum distance change required to update display (lower = more responsive, higher = better performance)',
                'min': 0.01,
                'max': 1.0,
                'step': 0.01,
            },
            
            # DISTANCE DISPLAY SETTINGS
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in distance measurements',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            'show_units': {
                'type': 'bool',
                'default': True,
                'label': 'Show Units',
                'description': 'Display units (meters, feet, etc.) with distance measurements',
            },
            'auto_convert_units': {
                'type': 'bool',
                'default': True,
                'label': 'Auto Convert Units',
                'description': 'Automatically convert to appropriate units (e.g., km for long distances)',
            },
            'copy_to_clipboard': {
                'type': 'bool',
                'default': False,
                'label': 'Copy to Clipboard',
                'description': 'Automatically copy distance measurement to clipboard',
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
    
    def execute(self, context):
        """
        Execute the measure distance action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            show_instruction_popup = bool(self.get_setting('show_instruction_popup', False))
            show_final_measurement = bool(self.get_setting('show_final_measurement', False))
            marker_color = str(self.get_setting('marker_color', '#FF0000'))
            marker_size = int(self.get_setting('marker_size', 8))
            marker_width = int(self.get_setting('marker_width', 3))
            show_distance_label = bool(self.get_setting('show_distance_label', True))
            label_font_size = int(self.get_setting('label_font_size', 10))
            label_background = bool(self.get_setting('label_background', True))
            update_sensitivity = float(self.get_setting('update_sensitivity', 0.1))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_units = bool(self.get_setting('show_units', True))
            auto_convert_units = bool(self.get_setting('auto_convert_units', True))
            copy_to_clipboard = bool(self.get_setting('copy_to_clipboard', False))
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
            # Get canvas CRS for proper coordinate handling
            canvas_crs = canvas.mapSettings().destinationCrs()
            
            # Store the first point for measurement
            first_point = click_point
            
            # Show instruction to user only if setting is enabled
            if show_instruction_popup:
                self.show_info("Measure Distance", 
                    f"First point set at: {first_point.x():.{decimal_places}f}, {first_point.y():.{decimal_places}f}\n\n"
                    f"Move your mouse to see the distance dynamically.\n"
                    f"Right-click to complete measurement and show final result.\n"
                    f"Press Escape to cancel measurement.")
            
            # Set up the canvas to capture the next click
            self._setup_measurement_mode(canvas, first_point, canvas_crs, {
                'show_final_measurement': show_final_measurement,
                'marker_color': marker_color,
                'marker_size': marker_size,
                'marker_width': marker_width,
                'show_distance_label': show_distance_label,
                'label_font_size': label_font_size,
                'label_background': label_background,
                'update_sensitivity': update_sensitivity,
                'decimal_places': decimal_places,
                'show_units': show_units,
                'auto_convert_units': auto_convert_units,
                'copy_to_clipboard': copy_to_clipboard,
            })
            
        except Exception as e:
            self.show_error("Error", f"Failed to start distance measurement: {str(e)}")
    
    def _setup_measurement_mode(self, canvas, first_point, canvas_crs, settings):
        """Set up the canvas to capture the second click for measurement with X marker."""
        from qgis.PyQt.QtCore import Qt, QTime
        from qgis.PyQt.QtGui import QPen, QColor, QFont, QPainter, QBrush
        from qgis.PyQt.QtWidgets import QLabel, QApplication
        from qgis.gui import QgsMapTool, QgsMapCanvasItem
        from qgis.core import QgsPointXY
        
        # Store the current map tool to restore it later
        original_tool = canvas.mapTool()
        
        class StaticStartMarker(QgsMapCanvasItem):
            """Simple canvas item for drawing the start marker only."""
            
            def __init__(self, canvas, first_point, settings):
                super().__init__(canvas)
                self.canvas = canvas
                self.first_point = first_point
                self.settings = settings
                self.setZValue(1000)  # Draw on top
            
            def paint(self, painter, option, widget):
                """Paint the start marker."""
                # Convert map coordinates to screen coordinates
                start_screen = self.toCanvasCoordinates(self.first_point)
                
                # Set up pen for the marker
                pen = QPen()
                pen.setColor(QColor(self.settings['marker_color']))
                pen.setWidth(self.settings['marker_width'])
                
                painter.setPen(pen)
                
                # Draw X marker at start point only
                self._draw_x_marker(painter, start_screen, self.settings['marker_size'])
            
            def _draw_x_marker(self, painter, center, size):
                """Draw an X marker at the given center point."""
                half_size = size // 2
                
                # Convert to integer coordinates
                center_x = int(center.x())
                center_y = int(center.y())
                
                # Draw the X
                painter.drawLine(
                    center_x - half_size, center_y - half_size,
                    center_x + half_size, center_y + half_size
                )
                painter.drawLine(
                    center_x - half_size, center_y + half_size,
                    center_x + half_size, center_y - half_size
                )
        
        class SimpleDistanceMeasurementTool(QgsMapTool):
            """Simple map tool with distance measurement."""
            
            def __init__(self, canvas, first_point, canvas_crs, settings, parent_action, original_tool):
                super().__init__(canvas)
                self.canvas = canvas
                self.first_point = first_point
                self.canvas_crs = canvas_crs
                self.settings = settings
                self.parent_action = parent_action
                self.original_tool = original_tool
                self.setCursor(self.parent_action._get_measure_cursor())
                
                # Create the static start marker
                self.start_marker = StaticStartMarker(canvas, first_point, settings)
                self.start_marker.show()
                
                # Create distance label
                self.distance_label = QLabel()
                self.distance_label.setStyleSheet(f"""
                    QLabel {{
                        background-color: rgba(255, 255, 255, 200);
                        border: 1px solid {settings['marker_color']};
                        border-radius: 3px;
                        padding: 2px 6px;
                        font-weight: bold;
                        font-size: {settings['label_font_size']}px;
                        color: {settings['marker_color']};
                    }}
                """)
                self.distance_label.hide()
                
                # Performance optimization
                self._last_distance = 0.0
                self._distance_threshold = float(settings.get('update_sensitivity', 0.1))
                self._last_update_time = QTime.currentTime()
                self._update_interval = 50  # Update every 50ms max
            
            def _update_distance_display(self, current_point, distance):
                """Update the distance display efficiently."""
                if not self.settings['show_distance_label']:
                    return
                
                # Ensure distance is a float
                distance = float(distance)
                
                # Format distance
                distance_formatted, unit_display = self.parent_action._format_distance_with_units(
                    distance, "units", int(self.settings['decimal_places']), bool(self.settings['auto_convert_units'])
                )
                
                # Get unit name
                unit_name = "units"
                if self.settings['show_units']:
                    if self.canvas_crs.isGeographic():
                        unit_name = "degrees"
                    else:
                        try:
                            unit_name = self.canvas_crs.mapUnits().name().lower()
                        except:
                            unit_name = "map units"
                
                # Create label text
                if self.settings['show_units']:
                    label_text = f"{distance_formatted} {unit_display}"
                else:
                    label_text = distance_formatted
                
                # Update label text
                self.distance_label.setText(label_text)
                
                # Position label near mouse cursor
                cursor_pos = self.canvas.mapFromGlobal(self.canvas.cursor().pos())
                label_x = cursor_pos.x() + 15
                label_y = cursor_pos.y() - 30
                
                # Ensure label stays within canvas bounds
                canvas_rect = self.canvas.rect()
                if label_x + self.distance_label.width() > canvas_rect.width():
                    label_x = cursor_pos.x() - self.distance_label.width() - 15
                if label_y < 0:
                    label_y = cursor_pos.y() + 15
                
                # Move and show label
                self.distance_label.move(label_x, label_y)
                self.distance_label.show()
                self.distance_label.raise_()
            
            def canvasMoveEvent(self, event):
                """Handle mouse move efficiently."""
                # Get the current mouse position in map coordinates
                current_point = self.toMapCoordinates(event.pos())
                
                # Throttle distance updates for performance
                current_time = QTime.currentTime()
                if self._last_update_time.msecsTo(current_time) < self._update_interval:
                    return
                
                self._last_update_time = current_time
                
                # Calculate distance and ensure it's a float
                distance = float(self.first_point.distance(current_point))
                
                # Only update if distance changed significantly
                # Ensure both values are floats for comparison
                if abs(distance - float(self._last_distance)) > float(self._distance_threshold):
                    self._last_distance = distance
                    self._update_distance_display(current_point, distance)
            
            def canvasPressEvent(self, event):
                """Handle canvas press event to complete measurement."""
                if event.button() == 2:  # Right click to complete measurement
                    # Get the current mouse position as the second point
                    second_point = self.toMapCoordinates(event.pos())
                    
                    # Hide the start marker and label
                    self.start_marker.hide()
                    self.canvas.scene().removeItem(self.start_marker)
                    self.distance_label.hide()
                    
                    # Calculate and show final distance
                    self.parent_action._calculate_and_show_distance(
                        self.first_point, second_point, self.canvas_crs, self.settings
                    )
                    
                    # Restore the original map tool
                    if self.original_tool:
                        self.canvas.setMapTool(self.original_tool)
                    else:
                        # If no original tool, unset the current tool
                        self.canvas.unsetMapTool(self)
                elif event.button() == 1:  # Left click - just continue measuring
                    # Don't complete measurement, just continue showing distance
                    pass
            
            def keyPressEvent(self, event):
                """Handle key press events."""
                from qgis.PyQt.QtCore import Qt
                if event.key() == Qt.Key_Escape:
                    # Cancel measurement on Escape
                    self.start_marker.hide()
                    self.canvas.scene().removeItem(self.start_marker)
                    self.distance_label.hide()
                    
                    # Restore the original map tool
                    if self.original_tool:
                        self.canvas.setMapTool(self.original_tool)
                    else:
                        # If no original tool, unset the current tool
                        self.canvas.unsetMapTool(self)
                else:
                    super().keyPressEvent(event)
            
            def deactivate(self):
                """Clean up when tool is deactivated."""
                # Hide the start marker and label
                if hasattr(self, 'start_marker'):
                    self.start_marker.hide()
                    self.canvas.scene().removeItem(self.start_marker)
                if hasattr(self, 'distance_label'):
                    self.distance_label.hide()
                
                super().deactivate()
        
        # Create and set the simple measurement tool
        measurement_tool = SimpleDistanceMeasurementTool(canvas, first_point, canvas_crs, settings, self, original_tool)
        canvas.setMapTool(measurement_tool)
    
    def _get_measure_cursor(self):
        """Get appropriate cursor for measurement mode."""
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtGui import QCursor
        return QCursor(Qt.CrossCursor)
    
    def _calculate_and_show_distance(self, first_point, second_point, canvas_crs, settings):
        """Calculate and display the distance between two points."""
        try:
            # Calculate distance and ensure it's a float
            distance = float(first_point.distance(second_point))
            
            # Get unit information
            unit_name = "units"
            if settings['show_units']:
                if canvas_crs.isGeographic():
                    unit_name = "degrees"
                else:
                    # For projected CRS, get the map units
                    try:
                        unit_name = canvas_crs.mapUnits().name().lower()
                    except:
                        unit_name = "map units"
            
            # Auto-convert units if requested
            distance_formatted, unit_display = self._format_distance_with_units(
                distance, unit_name, settings['decimal_places'], settings['auto_convert_units']
            )
            
            # Build result message
            result_lines = []
            result_lines.append(f"Point 1: {first_point.x():.{settings['decimal_places']}f}, {first_point.y():.{settings['decimal_places']}f}")
            result_lines.append(f"Point 2: {second_point.x():.{settings['decimal_places']}f}, {second_point.y():.{settings['decimal_places']}f}")
            result_lines.append("")  # Empty line for spacing
            result_lines.append(f"Distance: {distance_formatted}")
            
            if settings['show_units']:
                result_lines.append(f"Units: {unit_display}")
            
            result_lines.append(f"CRS: {canvas_crs.description()}")
            
            result_text = "\n".join(result_lines)
            
            # Copy to clipboard if requested
            if settings['copy_to_clipboard']:
                from qgis.PyQt.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(distance_formatted)
                self.show_info("Copied to Clipboard", f"Distance '{distance_formatted}' copied to clipboard")
            
            # Show result if enabled
            if settings['show_final_measurement']:
                self.show_info("Distance Measurement", result_text)
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate distance: {str(e)}")
    
    def _format_distance_with_units(self, distance, base_unit, decimal_places, auto_convert):
        """Format distance with appropriate units."""
        # Ensure all parameters are proper types
        distance = float(distance)
        decimal_places = int(decimal_places)
        auto_convert = bool(auto_convert)
        
        if not auto_convert:
            return f"{distance:.{decimal_places}f}", base_unit
        
        # Auto-convert to appropriate units
        if base_unit in ['meters', 'meter', 'm']:
            if distance >= 1000:
                return f"{distance/1000:.{decimal_places}f}", "km"
            else:
                return f"{distance:.{decimal_places}f}", "m"
        elif base_unit in ['feet', 'foot', 'ft']:
            if distance >= 5280:
                return f"{distance/5280:.{decimal_places}f}", "miles"
            else:
                return f"{distance:.{decimal_places}f}", "ft"
        else:
            # For other units, just return as is
            return f"{distance:.{decimal_places}f}", base_unit


# REQUIRED: Create global instance for automatic discovery
measure_distance_action = MeasureDistanceAction()
