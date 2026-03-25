"""
Calculate Shortest Path Through Points Action for Right-click Utilities and Shortcuts Hub

Calculates the shortest path that visits all points in a point layer (Traveling Salesman Problem).
Creates a polyline layer showing the optimal route through all points.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsVectorFileWriter,
    QgsPointXY
)
from ..history_manager import get_history_manager
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import (
    QFileDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QDialogButtonBox
)
import math


class PointSelectionDialog(QDialog):
    """Dialog for selecting start and end points."""
    
    def __init__(self, parent, features, layer):
        """
        Initialize the dialog.
        
        Args:
            parent: Parent widget
            features: List of QgsFeature objects
            layer: QgsVectorLayer
        """
        super().__init__(parent)
        self.setWindowTitle("Select Start and End Points")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        info_label = QLabel(
            "Select the start and end points for the route.\n"
            "All other points will be visited in the shortest path between them."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Start point selection
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("Start Point:"))
        self.start_combo = QComboBox()
        self._populate_combo(self.start_combo, features, layer)
        start_layout.addWidget(self.start_combo)
        layout.addLayout(start_layout)
        
        # End point selection
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("End Point:"))
        self.end_combo = QComboBox()
        self._populate_combo(self.end_combo, features, layer)
        end_layout.addWidget(self.end_combo)
        layout.addLayout(end_layout)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _populate_combo(self, combo, features, layer):
        """Populate combo box with point information."""
        for i, feature in enumerate(features):
            # Create display text with ID and first attribute if available
            feature_id = feature.id()
            display_text = f"Point {i + 1} (ID: {feature_id})"
            
            # Add first attribute value if available
            if feature.attributes():
                first_attr = feature.attributes()[0]
                if first_attr and str(first_attr).strip():
                    display_text += f" - {str(first_attr)}"
            
            combo.addItem(display_text, feature_id)
    
    def get_selected_indices(self):
        """
        Get selected start and end point indices.
        
        Returns:
            tuple: (start_index, end_index) or (None, None) if cancelled
        """
        start_id = self.start_combo.currentData()
        end_id = self.end_combo.currentData()
        return start_id, end_id


class CalculateShortestPathThroughPointsAction(BaseAction):
    """Action to calculate shortest path through all points (TSP solution)."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_shortest_path_through_points"
        self.name = "Calculate Shortest Path Through Points"
        self.category = "Analysis"
        self.description = "Calculate the shortest path that visits all points in a point layer (Traveling Salesman Problem). Creates a polyline layer showing the optimal route through all points, minimizing total travel distance. Supports automatic or manual selection of start and end points."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with point layers
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # OUTPUT SETTINGS
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'default': 'Shortest Path_{source_layer}',
                'label': 'Layer Name Template',
                'description': 'Template for the path layer name. Available variables: {source_layer}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created path layer to the project',
            },
            
            # PATH CALCULATION SETTINGS
            'algorithm': {
                'type': 'choice',
                'default': 'nearest_neighbor',
                'label': 'Algorithm',
                'description': 'Algorithm to use for calculating shortest path. Nearest Neighbor is fast but may not be optimal. 2-opt improves the result but takes longer.',
                'options': ['nearest_neighbor', 'nearest_neighbor_2opt'],
            },
            'point_selection_mode': {
                'type': 'choice',
                'default': 'automatic',
                'label': 'Point Selection Mode',
                'description': 'Automatic: Use predefined start point. Manual: Select start and end points from dialog.',
                'options': ['automatic', 'manual'],
            },
            'start_point': {
                'type': 'choice',
                'default': 'first',
                'label': 'Start Point (Automatic Mode)',
                'description': 'Which point to start the path from (only used in automatic mode)',
                'options': ['first', 'last', 'northernmost', 'southernmost', 'easternmost', 'westernmost', 'closest_to_center'],
            },
            'return_to_start': {
                'type': 'bool',
                'default': False,
                'label': 'Return to Start',
                'description': 'If enabled, the path returns to the starting point (closed loop). Only used in automatic mode. In manual mode, path always goes from start to end point.',
            },
            
            # METADATA SETTINGS
            'include_path_length': {
                'type': 'bool',
                'default': True,
                'label': 'Include Path Length',
                'description': 'Add a field with the total path length in map units',
            },
            'include_point_count': {
                'type': 'bool',
                'default': True,
                'label': 'Include Point Count',
                'description': 'Add a field with the number of points visited',
            },
            'include_segment_lengths': {
                'type': 'bool',
                'default': False,
                'label': 'Include Segment Lengths',
                'description': 'Add a field with individual segment lengths (for debugging/analysis)',
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places for distance values',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created path layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after creating the path',
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
    
    def _generate_output_layer_name(self, template, source_layer_name):
        """
        Generate output layer name from template.
        
        Args:
            template (str): Name template
            source_layer_name (str): Source layer name
            
        Returns:
            str: Generated layer name
        """
        from datetime import datetime
        
        # Replace template variables
        name = template.replace('{source_layer}', source_layer_name)
        name = name.replace('{timestamp}', datetime.now().strftime('%Y%m%d_%H%M%S'))
        name = name.replace('{date}', datetime.now().strftime('%Y-%m-%d'))
        name = name.replace('{time}', datetime.now().strftime('%H:%M:%S'))
        
        return name
    
    def _calculate_distance(self, point1, point2):
        """
        Calculate Euclidean distance between two points.
        
        Args:
            point1 (QgsPointXY): First point
            point2 (QgsPointXY): Second point
            
        Returns:
            float: Distance between points
        """
        dx = point2.x() - point1.x()
        dy = point2.y() - point1.y()
        return math.sqrt(dx * dx + dy * dy)
    
    def _find_start_point(self, points, start_point_option):
        """
        Find the starting point index based on the option.
        
        Args:
            points (list): List of QgsPointXY points
            start_point_option (str): Start point option
            
        Returns:
            int: Index of starting point
        """
        if start_point_option == 'first':
            return 0
        elif start_point_option == 'last':
            return len(points) - 1
        elif start_point_option == 'northernmost':
            return max(range(len(points)), key=lambda i: points[i].y())
        elif start_point_option == 'southernmost':
            return min(range(len(points)), key=lambda i: points[i].y())
        elif start_point_option == 'easternmost':
            return max(range(len(points)), key=lambda i: points[i].x())
        elif start_point_option == 'westernmost':
            return min(range(len(points)), key=lambda i: points[i].x())
        elif start_point_option == 'closest_to_center':
            # Calculate center point
            if not points:
                return 0
            center_x = sum(p.x() for p in points) / len(points)
            center_y = sum(p.y() for p in points) / len(points)
            center = QgsPointXY(center_x, center_y)
            return min(range(len(points)), key=lambda i: self._calculate_distance(points[i], center))
        else:
            return 0
    
    def _nearest_neighbor_path(self, points, start_index):
        """
        Calculate path using nearest neighbor algorithm.
        
        Args:
            points (list): List of QgsPointXY points
            start_index (int): Index of starting point
            
        Returns:
            list: List of point indices in order of visitation
        """
        if len(points) <= 1:
            return list(range(len(points)))
        
        n = len(points)
        visited = [False] * n
        path = [start_index]
        visited[start_index] = True
        
        current = start_index
        
        # Visit all remaining points
        for _ in range(n - 1):
            nearest = None
            nearest_dist = float('inf')
            
            for i in range(n):
                if not visited[i]:
                    dist = self._calculate_distance(points[current], points[i])
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest = i
            
            if nearest is not None:
                path.append(nearest)
                visited[nearest] = True
                current = nearest
        
        return path
    
    def _two_opt_improvement(self, points, path):
        """
        Improve path using 2-opt algorithm.
        
        Args:
            points (list): List of QgsPointXY points
            path (list): Current path (list of indices)
            
        Returns:
            list: Improved path
        """
        if len(path) < 4:
            return path
        
        improved = True
        best_path = path[:]
        best_distance = self._calculate_path_distance(points, best_path)
        
        while improved:
            improved = False
            for i in range(1, len(best_path) - 2):
                for j in range(i + 1, len(best_path)):
                    if j - i == 1:
                        continue
                    
                    # Try reversing segment between i and j
                    new_path = best_path[:i] + best_path[i:j+1][::-1] + best_path[j+1:]
                    new_distance = self._calculate_path_distance(points, new_path)
                    
                    if new_distance < best_distance:
                        best_path = new_path
                        best_distance = new_distance
                        improved = True
        
        return best_path
    
    def _calculate_path_distance(self, points, path_indices):
        """
        Calculate total distance of a path.
        
        Args:
            points (list): List of QgsPointXY points
            path_indices (list): List of point indices in order
            
        Returns:
            float: Total path distance
        """
        if len(path_indices) < 2:
            return 0.0
        
        total = 0.0
        for i in range(len(path_indices) - 1):
            idx1 = path_indices[i]
            idx2 = path_indices[i + 1]
            total += self._calculate_distance(points[idx1], points[idx2])
        
        return total
    
    def _calculate_shortest_path(self, points, algorithm, start_index, end_index=None, return_to_start=False):
        """
        Calculate shortest path through all points.
        
        Args:
            points (list): List of QgsPointXY points
            algorithm (str): Algorithm to use
            start_index (int): Index to start from
            end_index (int, optional): Index to end at (if None and not return_to_start, uses all points)
            return_to_start (bool): Whether to return to start (only used if end_index is None)
            
        Returns:
            tuple: (path_indices, total_distance)
        """
        if len(points) < 2:
            return ([0], 0.0) if points else ([], 0.0)
        
        # If end_index is specified and different from start, ensure it's visited last
        if end_index is not None and end_index != start_index:
            # Create list of points to visit (excluding start and end)
            remaining_indices = [i for i in range(len(points)) if i != start_index and i != end_index]
            
            if not remaining_indices:
                # Only start and end points
                path = [start_index, end_index]
                total_distance = self._calculate_path_distance(points, path)
                return path, total_distance
            
            # Calculate path through remaining points
            # Use nearest neighbor starting from a point closest to start
            remaining_points = [points[i] for i in remaining_indices]
            
            # Find which remaining point is closest to start point
            closest_to_start_idx = 0
            closest_dist = self._calculate_distance(points[start_index], remaining_points[0])
            for i in range(1, len(remaining_points)):
                dist = self._calculate_distance(points[start_index], remaining_points[i])
                if dist < closest_dist:
                    closest_dist = dist
                    closest_to_start_idx = i
            
            # Calculate path through remaining points
            remaining_path = self._nearest_neighbor_path(remaining_points, closest_to_start_idx)
            
            # Apply 2-opt if requested
            if algorithm == 'nearest_neighbor_2opt':
                remaining_path = self._two_opt_improvement(remaining_points, remaining_path)
            
            # Map back to original indices and build full path
            path = [start_index]
            for idx in remaining_path:
                path.append(remaining_indices[idx])
            path.append(end_index)
            
            # Apply 2-opt to full path if requested (but keep start and end fixed)
            if algorithm == 'nearest_neighbor_2opt' and len(path) > 3:
                middle_path = path[1:-1]
                middle_points = [points[i] for i in middle_path]
                improved_middle = self._two_opt_improvement(middle_points, list(range(len(middle_path))))
                path = [path[0]] + [middle_path[i] for i in improved_middle] + [path[-1]]
        else:
            # No end point specified or end == start, use all points
            path = self._nearest_neighbor_path(points, start_index)
            
            # Apply 2-opt improvement if requested
            if algorithm == 'nearest_neighbor_2opt':
                path = self._two_opt_improvement(points, path)
            
            # Add return to start if requested (and end_index not specified)
            if return_to_start and end_index is None and len(path) > 1:
                # Add distance from last point back to first point
                total_distance = self._calculate_path_distance(points, path)
                total_distance += self._calculate_distance(points[path[-1]], points[path[0]])
                # Add start point to end of path for closed loop
                path = path + [path[0]]
                return path, total_distance
        
        # Calculate total distance
        total_distance = self._calculate_path_distance(points, path)
        
        return path, total_distance
    
    def _create_path_layer(self, layer_name, crs, include_path_length, include_point_count, 
                          include_segment_lengths, decimal_places):
        """
        Create a new line layer for the path.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            include_path_length (bool): Include path length field
            include_point_count (bool): Include point count field
            include_segment_lengths (bool): Include segment lengths field
            decimal_places (int): Decimal places for distances
            
        Returns:
            QgsVectorLayer: New line layer or None if failed
        """
        try:
            # Create memory layer
            layer_uri = f"LineString?crs={crs.authid()}"
            layer = QgsVectorLayer(layer_uri, layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int))
            
            if include_path_length:
                fields.append(QgsField('path_length', QVariant.Double))
            if include_point_count:
                fields.append(QgsField('point_count', QVariant.Int))
            if include_segment_lengths:
                fields.append(QgsField('segment_lengths', QVariant.String))
            
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create path layer: {str(e)}")
            return None
    
    def execute(self, context):
        """Execute the calculate shortest path action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
            layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
            add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
            algorithm = str(self.get_setting('algorithm', schema['algorithm']['default']))
            point_selection_mode = str(self.get_setting('point_selection_mode', schema['point_selection_mode']['default']))
            start_point = str(self.get_setting('start_point', schema['start_point']['default']))
            return_to_start = bool(self.get_setting('return_to_start', schema['return_to_start']['default']))
            include_path_length = bool(self.get_setting('include_path_length', schema['include_path_length']['default']))
            include_point_count = bool(self.get_setting('include_point_count', schema['include_point_count']['default']))
            include_segment_lengths = bool(self.get_setting('include_segment_lengths', schema['include_segment_lengths']['default']))
            decimal_places = int(self.get_setting('decimal_places', schema['decimal_places']['default']))
            zoom_to_layer = bool(self.get_setting('zoom_to_layer', schema['zoom_to_layer']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No point features found at this location")
            return
        
        # Get the layer from the first detected feature
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Validate that this is a point layer
        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "This action only works with point layers")
            return
        
        # Get all point features
        features = list(layer.getFeatures())
        if len(features) < 2:
            self.show_error("Error", "Layer must contain at least 2 points to calculate a path")
            return
        
        try:
            # Extract point coordinates
            points = []
            for feature in features:
                geometry = feature.geometry()
                if geometry and not geometry.isEmpty():
                    point = geometry.asPoint()
                    points.append(point)
            
            if len(points) < 2:
                self.show_error("Error", "Could not extract at least 2 valid points")
                return
            
            # Determine start and end points
            start_index = None
            end_index = None
            
            if point_selection_mode == 'manual':
                # Show dialog for user to select start and end points
                dialog = PointSelectionDialog(None, features, layer)
                if dialog.exec_() != QDialog.Accepted:
                    return  # User cancelled
                
                start_id, end_id = dialog.get_selected_indices()
                
                # Find indices in features list
                for i, feature in enumerate(features):
                    if feature.id() == start_id:
                        start_index = i
                    if feature.id() == end_id:
                        end_index = i
                
                if start_index is None or end_index is None:
                    self.show_error("Error", "Could not find selected points")
                    return
            else:
                # Automatic mode
                start_point_index = self._find_start_point(points, start_point)
                start_index = start_point_index
                
                if return_to_start:
                    end_index = start_index  # Will create closed loop
                else:
                    end_index = None  # Open path
            
            # Calculate shortest path
            path_indices, total_distance = self._calculate_shortest_path(
                points, algorithm, start_index, end_index, return_to_start
            )
            
            if not path_indices:
                self.show_error("Error", "Failed to calculate path")
                return
            
            # Generate output layer name
            source_layer_name = layer.name()
            output_layer_name = self._generate_output_layer_name(layer_name_template, source_layer_name)
            
            # Determine output path based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Path Layer As",
                    "",
                    "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                output_path = save_path
            else:
                output_path = None  # Temporary layer
            
            # Create path layer
            path_layer = self._create_path_layer(
                output_layer_name,
                layer.crs(),
                include_path_length,
                include_point_count,
                include_segment_lengths,
                decimal_places
            )
            
            if not path_layer:
                self.show_error("Error", "Failed to create path layer")
                return
            
            # Create polyline geometry from path
            path_points = [points[i] for i in path_indices]
            polyline_geom = QgsGeometry.fromPolylineXY(path_points)
            
            if polyline_geom.isEmpty():
                self.show_error("Error", "Failed to create path geometry")
                return
            
            # Calculate segment lengths if needed
            segment_lengths_str = ""
            if include_segment_lengths:
                segment_lengths = []
                for i in range(len(path_indices) - 1):
                    idx1 = path_indices[i]
                    idx2 = path_indices[i + 1]
                    dist = self._calculate_distance(points[idx1], points[idx2])
                    segment_lengths.append(f"{dist:.{decimal_places}f}")
                segment_lengths_str = "; ".join(segment_lengths)
            
            # Create feature
            path_layer.startEditing()
            feature = QgsFeature()
            feature.setGeometry(polyline_geom)
            
            # Set attributes
            attributes = [1]  # ID
            if include_path_length:
                attributes.append(round(total_distance, decimal_places))
            if include_point_count:
                attributes.append(len(points))
            if include_segment_lengths:
                attributes.append(segment_lengths_str)
            
            feature.setAttributes(attributes)
            path_layer.addFeature(feature)
            path_layer.commitChanges()
            
            # Save to file if permanent
            if layer_storage_type == 'permanent' and output_path:
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    path_layer,
                    output_path,
                    "UTF-8",
                    path_layer.crs(),
                    "GPKG" if output_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load saved layer
                saved_layer = QgsVectorLayer(output_path, output_layer_name, "ogr")
                if saved_layer.isValid():
                    path_layer = saved_layer
                else:
                    self.show_error("Error", "Failed to load saved layer")
                    return
            
            # Add to project if requested
            if add_to_project:
                QgsProject.instance().addMapLayer(path_layer)

                # Record create_layer undo entry so the user can remove the created layer
                try:
                    hm = get_history_manager()
                    layers_list = [self.create_layer_descriptor(path_layer)]

                    description = f"Created shortest path layer '{output_layer_name}' with {len(points)} points"
                    meta = {
                        'algorithm': algorithm,
                        'point_selection_mode': point_selection_mode,
                        'start_index': start_index,
                        'end_index': end_index,
                        'return_to_start': return_to_start,
                        'include_path_length': include_path_length,
                        'include_point_count': include_point_count,
                        'include_segment_lengths': include_segment_lengths,
                        'layer_storage_type': layer_storage_type
                    }

                    # Build layer definition (fields + features) so redo can recreate them
                    layer_definitions = []
                    try:
                        # Fields metadata
                        fields_meta = []
                        for f in path_layer.fields():
                            try:
                                qmeta = int(f.type())
                            except Exception:
                                qmeta = None
                            fields_meta.append({
                                'name': f.name(),
                                'qmeta_type': qmeta,
                                'length': getattr(f, 'length', None),
                                'precision': getattr(f, 'precision', None)
                            })

                        # Features backup
                        features_backup = []
                        try:
                            for feat in path_layer.getFeatures():
                                features_backup.append(self.create_feature_backup(feat, path_layer))
                        except Exception:
                            features_backup = []

                        # Capture simple renderer / symbology properties (first symbol layer) and full style if available
                        renderer_info = None
                        try:
                            renderer = path_layer.renderer()
                            symbol = None
                            try:
                                symbol = renderer.symbol()
                            except Exception:
                                symbol = None

                            sym_props = None
                            if symbol is not None:
                                try:
                                    sl = None
                                    try:
                                        sl = symbol.symbolLayer(0)
                                    except Exception:
                                        try:
                                            sll = symbol.symbolLayers()
                                            sl = sll[0] if sll else None
                                        except Exception:
                                            sl = None

                                    if sl is not None:
                                        try:
                                            sym_props = sl.properties()
                                        except Exception:
                                            sym_props = None
                                except Exception:
                                    sym_props = None

                            # Try to capture a serialized style string if available
                            style_str = None
                            try:
                                if hasattr(path_layer, 'saveStyleToString'):
                                    try:
                                        style_str = path_layer.saveStyleToString()
                                    except Exception:
                                        style_str = None
                                # Fallback: try renderer dump
                                if not style_str and renderer is not None and hasattr(renderer, 'dump'):
                                    try:
                                        style_str = renderer.dump()
                                    except Exception:
                                        style_str = None
                            except Exception:
                                style_str = None

                            renderer_info = {
                                'renderer_type': getattr(renderer, 'type', None) if renderer is not None else None,
                                'symbol_properties': sym_props,
                                'style': style_str
                            }
                        except Exception:
                            renderer_info = None

                        layer_definitions.append({
                            'layer_name': path_layer.name(),
                            'crs': path_layer.crs().authid() if path_layer.crs().isValid() else '',
                            'geometry_type': QgsWkbTypes.displayString(path_layer.wkbType()),
                            'wkb_type': int(path_layer.wkbType()),
                            'fields': fields_meta,
                            'features': features_backup,
                            'renderer': renderer_info
                        })
                    except Exception:
                        layer_definitions = []

                    hm.record(
                        action_id=self.action_id,
                        action_name=self.name,
                        description=description,
                        undo_type='create_layer',
                        can_undo=True,
                        undo_payload={'layer_definitions': layer_definitions},
                        layers=layers_list,
                        features=None,
                        atomic=True,
                        meta=meta
                    )
                except Exception:
                    # Non-fatal: history recording failure should not stop action
                    pass
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                try:
                    # Get layer extent
                    layer_extent = path_layer.extent()
                    
                    # Transform extent to canvas CRS if needed
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = path_layer.crs()
                    
                    if canvas_crs != layer_crs:
                        transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                        try:
                            layer_extent = transform.transformBoundingBox(layer_extent)
                        except Exception as e:
                            print(f"Warning: CRS transformation failed: {str(e)}")
                    
                    canvas.setExtent(layer_extent)
                    canvas.refresh()
                except Exception as zoom_error:
                    print(f"Warning: Could not zoom to layer: {str(zoom_error)}")
            
            # Show success message if requested
            if show_success_message:
                storage_info = "saved to disk" if layer_storage_type == 'permanent' else "created as temporary layer"
                if point_selection_mode == 'manual':
                    path_type = f"from point {start_index + 1} to point {end_index + 1}"
                else:
                    path_type = "closed loop" if return_to_start else "open path"
                self.show_info(
                    "Shortest Path Calculated",
                    f"Shortest path layer '{output_layer_name}' {storage_info} successfully.\n\n"
                    f"Points visited: {len(points)}\n"
                    f"Total path length: {total_distance:.{decimal_places}f} map units\n"
                    f"Path type: {path_type}\n"
                    f"Selection mode: {point_selection_mode.title()}\n"
                    f"Algorithm: {algorithm.replace('_', ' ').title()}"
                )
        
        except Exception as e:
            self.show_error("Error", f"Failed to calculate shortest path: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_shortest_path_through_points = CalculateShortestPathThroughPointsAction()

