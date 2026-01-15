"""
Snap Point to Polygon Action for Right-click Utilities and Shortcuts Hub

Snaps the selected point feature to the closest visible polygon feature.
Moves the point so it is positioned "on" the closest polygon boundary or inside it.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer, QgsWkbTypes, QgsMapLayer


class SnapPointToPolygonAction(BaseAction):
    """
    Action to snap point features to the closest visible polygon.
    
    This action finds all visible polygon layers in the project, calculates
    the distance from the selected point to each polygon, and moves the point
    to the closest polygon feature (either on the boundary or inside).
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "snap_point_to_polygon"
        self.name = "Snap Point to Polygon"
        self.category = "Editing"
        self.description = "Snap the selected point feature to the closest visible polygon. Moves the point to the centroid (center) of the nearest polygon feature from all visible polygon layers."
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
                'default': 'Snap point feature ID {feature_id} to the closest polygon?',
                'label': 'Confirmation Message Template',
                'description': 'Template for confirmation message. Available variables: {feature_id}, {layer_name}, {closest_polygon_info}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when point is snapped successfully',
            },
            'success_message_template': {
                'type': 'str',
                'default': 'Point snapped to polygon successfully. Distance moved: {distance_moved} map units',
                'label': 'Success Message Template',
                'description': 'Template for success message. Available variables: {feature_id}, {layer_name}, {distance_moved}, {closest_polygon_info}',
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
            
            # POLYGON LAYER SETTINGS - Which polygon layers to consider
            'include_invisible_polygon_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Include Invisible Polygon Layers',
                'description': 'Also consider polygon layers that are not visible in the layer tree',
            },
            'exclude_current_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Exclude Current Layer',
                'description': 'Exclude the current point layer from polygon layer search (prevents self-snapping)',
            },
            'polygon_layer_name_filter': {
                'type': 'str',
                'default': '',
                'label': 'Polygon Layer Name Filter',
                'description': 'Only consider polygon layers whose names contain this text (leave empty to consider all)',
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
            
            # SNAPPING BEHAVIOR SETTINGS - How to snap to polygons
            'snap_to_centroid': {
                'type': 'bool',
                'default': True,
                'label': 'Snap to Centroid (Default)',
                'description': 'Snap point to the polygon centroid/center point (default behavior)',
            },
            'snap_to_boundary': {
                'type': 'bool',
                'default': False,
                'label': 'Snap to Boundary (Optional)',
                'description': 'Snap point to the polygon boundary/edge (alternative option)',
            },
            'prefer_centroid_over_boundary': {
                'type': 'bool',
                'default': True,
                'label': 'Prefer Centroid Over Boundary',
                'description': 'When both options are enabled, always prefer centroid snapping over boundary',
            },
            
            # INFORMATION SETTINGS - What information to show
            'show_closest_polygon_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Closest Polygon Info',
                'description': 'Display information about the closest polygon in messages',
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
        Execute the snap point to polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            confirm_snap = bool(self.get_setting('confirm_snap', True))
            confirmation_template = str(self.get_setting('confirmation_message_template', 'Snap point feature ID {feature_id} to the closest polygon?'))
            show_success = bool(self.get_setting('show_success_message', True))
            success_template = str(self.get_setting('success_message_template', 'Point snapped to polygon successfully. Distance moved: {distance_moved} map units'))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            include_invisible = bool(self.get_setting('include_invisible_polygon_layers', False))
            exclude_current = bool(self.get_setting('exclude_current_layer', True))
            layer_filter = str(self.get_setting('polygon_layer_name_filter', ''))
            max_distance = float(self.get_setting('maximum_snap_distance', 1000.0))
            decimal_places = int(self.get_setting('decimal_places', 2))
            snap_to_centroid = bool(self.get_setting('snap_to_centroid', True))
            snap_to_boundary = bool(self.get_setting('snap_to_boundary', False))
            prefer_centroid = bool(self.get_setting('prefer_centroid_over_boundary', True))
            show_polygon_info = bool(self.get_setting('show_closest_polygon_info', True))
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
            
            # Find all visible polygon layers
            polygon_layers = self._get_visible_polygon_layers(include_invisible, exclude_current, layer, layer_filter)
            
            if not polygon_layers:
                self.show_warning("No Polygon Layers", "No visible polygon layers found in the project.")
                return
            
            # Find the closest polygon
            closest_result = self._find_closest_polygon(clicked_point, polygon_layers, max_distance, snap_to_centroid, snap_to_boundary, prefer_centroid)
            
            if not closest_result:
                formatted_distance = f"{max_distance:.{decimal_places}f}"
                self.show_warning("No Polygons Found", f"No polygons found within {formatted_distance} map units.")
                return
            
            closest_polygon_feature, closest_polygon_layer, closest_point_on_polygon, distance, snap_type = closest_result
            
            # Prepare polygon info for messages
            polygon_info = ""
            if show_polygon_info:
                snap_type_text = "centroid" if snap_type == "centroid" else "boundary"
                polygon_info = f"Polygon ID {closest_polygon_feature.id()} from layer '{closest_polygon_layer.name()}' (snapped to {snap_type_text})"
            
            # Ask for user confirmation before snapping if enabled
            if confirm_snap:
                confirmation_message = self.format_message_template(
                    confirmation_template,
                    feature_id=feature.id(),
                    layer_name=layer.name(),
                    closest_polygon_info=polygon_info
                )
                
                # Add coordinate info if requested
                if show_coordinate_info:
                    current_coords = f"({clicked_point.x():.6f}, {clicked_point.y():.6f})"
                    new_coords = f"({closest_point_on_polygon.x():.6f}, {closest_point_on_polygon.y():.6f})"
                    confirmation_message += f"\n\nCurrent coordinates: {current_coords}\nNew coordinates: {new_coords}"
                
                if not self.confirm_action("Snap Point to Polygon", confirmation_message):
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
                # Create new point geometry at the closest point on the polygon
                new_geometry = QgsGeometry.fromPointXY(closest_point_on_polygon)
                
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
                        closest_polygon_info=polygon_info
                    )
                    
                    # Add coordinate info if requested
                    if show_coordinate_info:
                        new_coords = f"({closest_point_on_polygon.x():.6f}, {closest_point_on_polygon.y():.6f})"
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
            self.show_error("Error", f"Failed to snap point to polygon: {str(e)}")
    
    def _get_visible_polygon_layers(self, include_invisible, exclude_current, current_layer, layer_filter):
        """
        Get all visible polygon layers in the project.
        
        Args:
            include_invisible (bool): Whether to include invisible layers
            exclude_current (bool): Whether to exclude the current layer
            current_layer: The current point layer
            layer_filter (str): Name filter for polygon layers
            
        Returns:
            list: List of visible polygon layers
        """
        project = QgsProject.instance()
        layer_tree_root = project.layerTreeRoot()
        all_layers = project.mapLayers().values()
        
        polygon_layers = []
        
        for layer in all_layers:
            if not layer.isValid():
                continue
            
            # Check if it's a vector layer
            if layer.type() != QgsMapLayer.VectorLayer:
                continue
            
            # Check if it's a polygon layer using proper QGIS method
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
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
            
            polygon_layers.append(layer)
        
        return polygon_layers
    
    def _find_closest_polygon(self, point, polygon_layers, max_distance, snap_to_centroid, snap_to_boundary, prefer_centroid):
        """
        Find the closest polygon to the given point.
        
        Args:
            point (QgsPointXY): The point to find closest polygon for
            polygon_layers (list): List of polygon layers to search
            max_distance (float): Maximum distance to consider
            snap_to_centroid (bool): Whether to snap to polygon centroid (default)
            snap_to_boundary (bool): Whether to snap to polygon boundary
            prefer_centroid (bool): Whether to prefer centroid over boundary
            
        Returns:
            tuple or None: (closest_feature, closest_layer, closest_point, distance, snap_type) or None
        """
        closest_feature = None
        closest_layer = None
        closest_point = None
        closest_distance = float('inf')
        closest_snap_type = None
        
        for layer in polygon_layers:
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if not geometry or geometry.isEmpty():
                    continue
                
                # Check if point is inside the polygon
                point_geom = QgsGeometry.fromPointXY(point)
                is_inside = geometry.contains(point_geom)
                
                # Try centroid snapping first (default behavior)
                if snap_to_centroid:
                    centroid = geometry.centroid().asPoint()
                    centroid_distance = point.distance(centroid)
                    
                    if centroid_distance <= max_distance:
                        if centroid_distance < closest_distance:
                            closest_distance = centroid_distance
                            closest_feature = feature
                            closest_layer = layer
                            closest_point = centroid
                            closest_snap_type = "centroid"
                
                # Try boundary snapping only if:
                # 1. Boundary snapping is enabled AND
                # 2. Either centroid snapping is disabled OR prefer_centroid is False
                if snap_to_boundary and (not snap_to_centroid or not prefer_centroid):
                    boundary_distance = geometry.distance(point_geom)
                    
                    if boundary_distance <= max_distance:
                        # Find closest point on boundary
                        closest_boundary_point = self._find_closest_point_on_boundary(point, geometry)
                        
                        # Calculate actual distance to the found boundary point
                        actual_boundary_distance = point.distance(closest_boundary_point)
                        
                        # Only use boundary if centroid snapping is disabled or if no centroid was found
                        if (not snap_to_centroid or closest_snap_type != "centroid"):
                            if actual_boundary_distance < closest_distance:
                                closest_distance = actual_boundary_distance
                                closest_feature = feature
                                closest_layer = layer
                                closest_point = closest_boundary_point
                                closest_snap_type = "boundary"
        
        if closest_feature is None:
            return None
        
        return (closest_feature, closest_layer, closest_point, closest_distance, closest_snap_type)
    
    def _find_closest_point_on_boundary(self, point, polygon_geometry):
        """
        Find the closest point on the polygon boundary.
        
        Args:
            point (QgsPointXY): The point to find closest boundary point for
            polygon_geometry (QgsGeometry): The polygon geometry
            
        Returns:
            QgsPointXY: The closest point on the boundary
        """
        try:
            # Get the exterior ring of the polygon
            exterior_ring = polygon_geometry.exteriorRing()
            if not exterior_ring:
                # If no exterior ring, return the centroid
                return polygon_geometry.centroid().asPoint()
            
            # Sample points along the exterior ring
            ring_length = exterior_ring.length()
            if ring_length > 0:
                closest_point_on_boundary = None
                min_distance = float('inf')
                
                # Sample more points along the ring for better accuracy
                num_samples = 501  # Sample 501 points along the ring
                for i in range(0, num_samples):
                    ratio = i / (num_samples - 1.0)
                    sample_point = exterior_ring.interpolate(ratio * ring_length).asPoint()
                    distance = point.distance(sample_point)
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_point_on_boundary = sample_point
                
                return closest_point_on_boundary
            else:
                # If ring has no length, return the centroid
                return polygon_geometry.centroid().asPoint()
                
        except Exception:
            # If any error occurs, return the centroid as fallback
            return polygon_geometry.centroid().asPoint()
    
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
snap_point_to_polygon_action = SnapPointToPolygonAction()
