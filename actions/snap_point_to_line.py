"""
Snap Point to Line Action for Right-click Utilities and Shortcuts Hub

Snaps the selected point feature to the closest visible line feature.
Moves the point so it is positioned "on" the closest line.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer, QgsWkbTypes, QgsMapLayer


class SnapPointToLineAction(BaseAction):
    """
    Action to snap point features to the closest visible line.
    
    This action finds all visible line layers in the project, calculates
    the distance from the selected point to each line, and moves the point
    to the closest line feature.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "snap_point_to_line"
        self.name = "Snap Point to Line"
        self.category = "Editing"
        self.description = "Snap the selected point feature to the closest visible line. Moves the point so it is positioned on the nearest line feature from all visible line layers."
        self.enabled = True
        
        # Action scoping - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with point features
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # BEHAVIOR SETTINGS - User experience options
            'confirm_snap': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Snapping',
                'description': 'Show confirmation dialog before snapping the point',
            },
            'confirmation_message_template': {
                'type': 'str',
                'default': 'Snap point feature ID {feature_id} to the closest line?',
                'label': 'Confirmation Message Template',
                'description': 'Template for confirmation message. Available variables: {feature_id}, {layer_name}, {closest_line_info}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when point is snapped successfully',
            },
            'success_message_template': {
                'type': 'str',
                'default': 'Point snapped to line successfully. Distance moved: {distance_moved} map units',
                'label': 'Success Message Template',
                'description': 'Template for success message. Available variables: {feature_id}, {layer_name}, {distance_moved}, {closest_line_info}',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after snapping (recommended)',
            },
            'handle_edit_mode_automatically': {
                'type': 'bool',
                'default': True,
                'label': 'Handle Edit Mode Automatically',
                'description': 'Automatically enter/exit edit mode as needed',
            },
            'rollback_on_error': {
                'type': 'bool',
                'default': True,
                'label': 'Rollback on Error',
                'description': 'Rollback changes if snap operation fails',
            },
            
            # LINE LAYER SETTINGS - Which line layers to consider
            'include_invisible_line_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Include Invisible Line Layers',
                'description': 'Also consider line layers that are not visible in the layer tree',
            },
            'exclude_current_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Exclude Current Layer',
                'description': 'Exclude the current point layer from line layer search (prevents self-snapping)',
            },
            'line_layer_name_filter': {
                'type': 'str',
                'default': '',
                'label': 'Line Layer Name Filter',
                'description': 'Only consider line layers whose names contain this text (leave empty to consider all)',
            },
            
            # DISTANCE SETTINGS - Distance and precision options
            'maximum_snap_distance': {
                'type': 'float',
                'default': 1000.0,
                'label': 'Maximum Snap Distance',
                'description': 'Maximum distance to snap (in map units). Points farther than this will not be snapped.',
                'min': 0.0,
                'max': 100000.0,
                'step': 1.0,
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in distance calculations',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            
            # INFORMATION SETTINGS - What information to show
            'show_closest_line_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Closest Line Info',
                'description': 'Display information about the closest line in messages',
            },
            'show_coordinate_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Coordinate Info',
                'description': 'Display coordinate information in messages',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in messages',
            },
        }
    
    def execute(self, context):
        """
        Execute the snap point to line action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            confirm_snap = bool(self.get_setting('confirm_snap', True))
            confirmation_template = str(self.get_setting('confirmation_message_template', 'Snap point feature ID {feature_id} to the closest line?'))
            show_success = bool(self.get_setting('show_success_message', True))
            success_template = str(self.get_setting('success_message_template', 'Point snapped to line successfully. Distance moved: {distance_moved} map units'))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            include_invisible = bool(self.get_setting('include_invisible_line_layers', False))
            exclude_current = bool(self.get_setting('exclude_current_layer', True))
            layer_filter = str(self.get_setting('line_layer_name_filter', ''))
            max_distance = float(self.get_setting('maximum_snap_distance', 1000.0))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_line_info = bool(self.get_setting('show_closest_line_info', True))
            show_coordinate_info = bool(self.get_setting('show_coordinate_info', False))
            show_crs_info = bool(self.get_setting('show_crs_info', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No point features found at this location")
            return
        
        # Get the clicked feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get clicked feature geometry
            clicked_geometry = feature.geometry()
            if not clicked_geometry or clicked_geometry.isEmpty():
                self.show_error("Error", "Feature has no valid geometry")
                return
            
            # Get point coordinates
            clicked_point = clicked_geometry.asPoint()
            
            # Find all visible line layers
            line_layers = self._get_visible_line_layers(include_invisible, exclude_current, layer, layer_filter)
            
            if not line_layers:
                self.show_warning("No Line Layers", "No visible line layers found in the project.")
                return
            
            # Find the closest line
            closest_result = self._find_closest_line(clicked_point, line_layers, max_distance)
            
            if not closest_result:
                formatted_distance = f"{max_distance:.{decimal_places}f}"
                self.show_warning("No Lines Found", f"No lines found within {formatted_distance} map units.")
                return
            
            closest_line_feature, closest_line_layer, closest_point_on_line, distance = closest_result
            
            # Prepare line info for messages
            line_info = ""
            if show_line_info:
                line_info = f"Line ID {closest_line_feature.id()} from layer '{closest_line_layer.name()}'"
            
            # Ask for user confirmation before snapping if enabled
            if confirm_snap:
                confirmation_message = self.format_message_template(
                    confirmation_template,
                    feature_id=feature.id(),
                    layer_name=layer.name(),
                    closest_line_info=line_info
                )
                
                # Add coordinate info if requested
                if show_coordinate_info:
                    current_coords = f"({clicked_point.x():.6f}, {clicked_point.y():.6f})"
                    new_coords = f"({closest_point_on_line.x():.6f}, {closest_point_on_line.y():.6f})"
                    confirmation_message += f"\n\nCurrent coordinates: {current_coords}\nNew coordinates: {new_coords}"
                
                if not self.confirm_action("Snap Point to Line", confirmation_message):
                    return
            
            # Handle edit mode if enabled
            edit_result = None
            was_in_edit_mode = False
            edit_mode_entered = False
            
            if handle_edit_mode:
                edit_result = self.handle_edit_mode(layer, "point snapping")
                if edit_result[0] is None:  # Error occurred
                    return
                was_in_edit_mode, edit_mode_entered = edit_result
            
            try:
                # Create new point geometry at the closest point on the line
                new_geometry = QgsGeometry.fromPointXY(closest_point_on_line)
                
                # Update feature geometry
                feature.setGeometry(new_geometry)
                if not layer.updateFeature(feature):
                    self.show_error("Error", "Failed to update point geometry")
                    return
                
                # Commit changes if enabled
                if auto_commit and handle_edit_mode:
                    if not self.commit_changes(layer, "point snapping"):
                        return
                
                # Show success message if enabled
                if show_success:
                    success_message = self.format_message_template(
                        success_template,
                        feature_id=feature.id(),
                        layer_name=layer.name(),
                        distance_moved=distance,
                        closest_line_info=line_info
                    )
                    
                    # Add coordinate info if requested
                    if show_coordinate_info:
                        new_coords = f"({closest_point_on_line.x():.6f}, {closest_point_on_line.y():.6f})"
                        success_message += f"\n\nNew coordinates: {new_coords}"
                    
                    # Add CRS info if requested
                    if show_crs_info:
                        crs = layer.crs()
                        success_message += f"\n\nCRS: {crs.description()}"
                    
                    self.show_info("Success", success_message)
                
            except Exception as e:
                self.show_error("Error", f"Failed to snap point: {str(e)}")
                if rollback_on_error and handle_edit_mode:
                    self.rollback_changes(layer)
                
            finally:
                # Exit edit mode if we entered it
                if handle_edit_mode:
                    self.exit_edit_mode(layer, edit_mode_entered)
            
        except Exception as e:
            self.show_error("Error", f"Failed to snap point to line: {str(e)}")
    
    def _get_visible_line_layers(self, include_invisible, exclude_current, current_layer, layer_filter):
        """
        Get all visible line layers in the project.
        
        Args:
            include_invisible (bool): Whether to include invisible layers
            exclude_current (bool): Whether to exclude the current layer
            current_layer: The current point layer
            layer_filter (str): Name filter for line layers
            
        Returns:
            list: List of visible line layers
        """
        project = QgsProject.instance()
        layer_tree_root = project.layerTreeRoot()
        all_layers = project.mapLayers().values()
        
        line_layers = []
        
        for layer in all_layers:
            if not layer.isValid():
                continue
            
            # Check if it's a vector layer
            if layer.type() != QgsMapLayer.VectorLayer:
                continue
            
            # Check if it's a line layer using proper QGIS method
            if layer.geometryType() != QgsWkbTypes.LineGeometry:
                continue
            
            # Apply name filter if specified
            if layer_filter and layer_filter.lower() not in layer.name().lower():
                continue
            
            # Exclude current layer if requested
            if exclude_current and layer.id() == current_layer.id():
                continue
            
            # Check visibility
            if not include_invisible:
                layer_tree_layer = layer_tree_root.findLayer(layer.id())
                if not layer_tree_layer or not layer_tree_layer.isVisible():
                    continue
            
            line_layers.append(layer)
        
        return line_layers
    
    def _find_closest_line(self, point, line_layers, max_distance):
        """
        Find the closest line to the given point.
        
        Args:
            point (QgsPointXY): The point to find closest line for
            line_layers (list): List of line layers to search
            max_distance (float): Maximum distance to consider
            
        Returns:
            tuple or None: (closest_feature, closest_layer, closest_point, distance) or None
        """
        closest_feature = None
        closest_layer = None
        closest_point = None
        closest_distance = float('inf')
        
        for layer in line_layers:
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if not geometry or geometry.isEmpty():
                    continue
                
                # Calculate distance from point to line geometry
                distance = geometry.distance(QgsGeometry.fromPointXY(point))
                
                # Find the closest point on the line using interpolate method
                # Get the line length and find the point at the closest position
                line_length = geometry.length()
                if line_length > 0:
                    # Use a simple approach: find the point on the line closest to our point
                    # by checking multiple points along the line
                    closest_point_on_line = None
                    min_point_distance = float('inf')
                    
                    # Sample points along the line to find the closest one
                    for i in range(0, 101):  # Sample 101 points along the line
                        ratio = i / 100.0
                        sample_point = geometry.interpolate(ratio * line_length).asPoint()
                        point_distance = point.distance(sample_point)
                        
                        if point_distance < min_point_distance:
                            min_point_distance = point_distance
                            closest_point_on_line = sample_point
                else:
                    # If line has no length, use the first vertex
                    closest_point_on_line = geometry.vertexAt(0)
                
                # Check if within maximum distance
                if distance > max_distance:
                    continue
                
                # Check if this is the closest so far
                if distance < closest_distance:
                    closest_distance = distance
                    closest_feature = feature
                    closest_layer = layer
                    closest_point = closest_point_on_line
        
        if closest_feature is None:
            return None
        
        return (closest_feature, closest_layer, closest_point, closest_distance)
    
    def format_message_template(self, template, **kwargs):
        """
        Format a message template with provided variables.
        
        Args:
            template (str): Message template with {variable} placeholders
            **kwargs: Variables to substitute in the template
            
        Returns:
            str: Formatted message
        """
        try:
            # Handle special formatting for distance_moved
            if 'distance_moved' in kwargs and isinstance(kwargs['distance_moved'], (int, float)):
                # Get decimal places setting
                decimal_places = int(self.get_setting('decimal_places', 2))
                kwargs['distance_moved'] = f"{kwargs['distance_moved']:.{decimal_places}f}"
            
            return template.format(**kwargs)
        except KeyError as e:
            # If a variable is missing, return the template as-is
            return template


# REQUIRED: Create global instance for automatic discovery
snap_point_to_line_action = SnapPointToLineAction()