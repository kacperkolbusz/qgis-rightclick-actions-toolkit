"""
Show Polygon Layer Angles Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the interior angles at each vertex of all polygon features in a layer.
Creates a point layer with angle measurements at each vertex location for all polygons.
"""

import math
from .base_action import BaseAction
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsField, QgsFields, QgsProject, QgsWkbTypes, QgsVectorFileWriter
from qgis.PyQt.QtCore import QVariant


class ShowPolygonLayerAnglesAction(BaseAction):
    """
    Action to calculate and display interior angles at polygon vertices for all features in a layer.
    
    This action processes all polygon features in the selected layer, extracts all vertices from each polygon,
    calculates the interior angle at each vertex, and creates a point layer with angle measurements.
    Works with both single and multipart polygons.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "show_polygon_layer_angles"
        self.name = "Show Polygon Layer Angles"
        self.category = "Analysis"
        self.description = "Calculate and display the interior angles at each vertex of all polygon features in the selected layer. Creates a point layer with angle measurements at each vertex location for all polygons. Works with both single and multipart polygons."
        self.enabled = True
        
        # Action scoping - works on entire polygon layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # OUTPUT SETTINGS
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'output_layer_name': {
                'type': 'str',
                'default': 'Polygon Layer Angles',
                'label': 'Output Layer Name',
                'description': 'Name for the new point layer containing angle measurements',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the new point layer to the current project',
            },
            
            # PROCESSING SETTINGS
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'If enabled, only process selected polygon features. If disabled, process all features in the layer.',
            },
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip features with invalid or empty geometries instead of showing an error',
            },
            
            # ANGLE SETTINGS
            'angle_unit': {
                'type': 'choice',
                'default': 'degrees',
                'label': 'Angle Unit',
                'description': 'Unit for angle measurements',
                'options': ['degrees', 'radians'],
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places for angle values',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            'show_angle_arcs': {
                'type': 'bool',
                'default': True,
                'label': 'Show Angle Arcs',
                'description': 'Create visual arc indicators (bows) showing the angles at each vertex',
            },
            'arc_radius': {
                'type': 'float',
                'default': 0.0,
                'label': 'Arc Radius',
                'description': 'Radius of angle arcs in map units (0 = auto-calculate based on polygon size)',
                'min': 0.0,
                'max': 10000.0,
                'step': 0.1,
            },
            'include_vertex_index': {
                'type': 'bool',
                'default': True,
                'label': 'Include Vertex Index',
                'description': 'Add a field with the vertex index number',
            },
            'include_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Include Feature ID',
                'description': 'Add a field with the source feature ID',
            },
            
            # BEHAVIOR SETTINGS
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when angle calculation completes',
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
    
    def _calculate_angle(self, p1, p2, p3):
        """
        Calculate the interior angle at point p2 formed by points p1, p2, p3.
        
        Args:
            p1 (QgsPointXY): First point (previous vertex)
            p2 (QgsPointXY): Vertex point (angle is calculated here)
            p3 (QgsPointXY): Third point (next vertex)
            
        Returns:
            float: Interior angle in radians
        """
        # Check for duplicate points
        if (abs(p1.x() - p2.x()) < 1e-10 and abs(p1.y() - p2.y()) < 1e-10) or \
           (abs(p3.x() - p2.x()) < 1e-10 and abs(p3.y() - p2.y()) < 1e-10) or \
           (abs(p1.x() - p3.x()) < 1e-10 and abs(p1.y() - p3.y()) < 1e-10):
            # Duplicate points - cannot calculate angle
            return 0.0
        
        # Create vectors along the polygon edges
        # Edge 1: from p1 to p2 (incoming edge)
        v1_x = p2.x() - p1.x()
        v1_y = p2.y() - p1.y()
        # Edge 2: from p2 to p3 (outgoing edge)
        v2_x = p3.x() - p2.x()
        v2_y = p3.y() - p2.y()
        
        # Calculate magnitudes
        mag1 = math.sqrt(v1_x * v1_x + v1_y * v1_y)
        mag2 = math.sqrt(v2_x * v2_x + v2_y * v2_y)
        
        # Avoid division by zero
        if mag1 < 1e-10 or mag2 < 1e-10:
            return 0.0
        
        # Calculate angles of the edges
        angle1 = math.atan2(v1_y, v1_x)  # Angle of edge from p1 to p2
        angle2 = math.atan2(v2_y, v2_x)  # Angle of edge from p2 to p3
        
        # Calculate the turning angle (how much we turn at p2)
        turn_angle = angle2 - angle1
        
        # Normalize to [-π, π]
        while turn_angle > math.pi:
            turn_angle -= 2 * math.pi
        while turn_angle < -math.pi:
            turn_angle += 2 * math.pi
        
        # The interior angle is π - turn_angle
        interior_angle = math.pi - turn_angle
        if interior_angle < 0:
            interior_angle += 2 * math.pi
        if interior_angle > 2 * math.pi:
            interior_angle -= 2 * math.pi
        
        # Convert to the correct interior angle: 360° - calculated_angle
        interior_angle = 2 * math.pi - interior_angle
        
        return interior_angle
    
    def _extract_vertices_and_angles(self, geometry):
        """
        Extract vertices and calculate angles from polygon geometry.
        
        Args:
            geometry (QgsGeometry): Polygon geometry
            
        Returns:
            list: List of tuples (vertex_point, angle_radians, vertex_index, p1, p3)
                  where p1 and p3 are adjacent points for arc creation
        """
        vertices_with_angles = []
        
        # Handle multipart polygons
        if geometry.isMultipart():
            multi_polygon = geometry.asMultiPolygon()
            vertex_index = 0
            
            for polygon in multi_polygon:
                for ring in polygon:
                    ring_points = ring
                    if len(ring_points) < 3:
                        continue
                    
                    # Check if polygon is closed (first and last points are the same)
                    is_closed = (abs(ring_points[0].x() - ring_points[-1].x()) < 1e-10 and 
                                abs(ring_points[0].y() - ring_points[-1].y()) < 1e-10)
                    
                    # Number of vertices to process (exclude duplicate last point if closed)
                    num_vertices = len(ring_points) - 1 if is_closed else len(ring_points)
                    
                    # Process each vertex in the ring
                    for i in range(num_vertices):
                        # Get three consecutive points (with proper wrapping)
                        curr_idx = i
                        
                        # Previous point (with wrapping)
                        if i == 0:
                            prev_idx = num_vertices - 1
                        else:
                            prev_idx = i - 1
                        
                        # Next point (with wrapping)
                        if i == num_vertices - 1:
                            next_idx = 0
                        else:
                            next_idx = i + 1
                        
                        p1 = ring_points[prev_idx]
                        p2 = ring_points[curr_idx]
                        p3 = ring_points[next_idx]
                        
                        # Skip if points are too close (duplicate)
                        if (abs(p1.x() - p2.x()) < 1e-10 and abs(p1.y() - p2.y()) < 1e-10) or \
                           (abs(p3.x() - p2.x()) < 1e-10 and abs(p3.y() - p2.y()) < 1e-10):
                            continue
                        
                        # Calculate angle at p2
                        angle = self._calculate_angle(p1, p2, p3)
                        if angle > 0:  # Only add if angle is valid
                            vertices_with_angles.append((QgsPointXY(p2), angle, vertex_index, QgsPointXY(p1), QgsPointXY(p3)))
                            vertex_index += 1
        else:
            # Single polygon
            polygon = geometry.asPolygon()
            vertex_index = 0
            
            for ring in polygon:
                ring_points = ring
                if len(ring_points) < 3:
                    continue
                
                # Check if polygon is closed (first and last points are the same)
                is_closed = (abs(ring_points[0].x() - ring_points[-1].x()) < 1e-10 and 
                            abs(ring_points[0].y() - ring_points[-1].y()) < 1e-10)
                
                # Number of vertices to process (exclude duplicate last point if closed)
                num_vertices = len(ring_points) - 1 if is_closed else len(ring_points)
                
                # Process each vertex in the ring
                for i in range(num_vertices):
                    # Get three consecutive points (with proper wrapping)
                    curr_idx = i
                    
                    # Previous point (with wrapping)
                    if i == 0:
                        prev_idx = num_vertices - 1
                    else:
                        prev_idx = i - 1
                    
                    # Next point (with wrapping)
                    if i == num_vertices - 1:
                        next_idx = 0
                    else:
                        next_idx = i + 1
                    
                    p1 = ring_points[prev_idx]
                    p2 = ring_points[curr_idx]
                    p3 = ring_points[next_idx]
                    
                    # Skip if points are too close (duplicate)
                    if (abs(p1.x() - p2.x()) < 1e-10 and abs(p1.y() - p2.y()) < 1e-10) or \
                       (abs(p3.x() - p2.x()) < 1e-10 and abs(p3.y() - p2.y()) < 1e-10):
                        continue
                    
                    # Calculate angle at p2
                    angle = self._calculate_angle(p1, p2, p3)
                    if angle > 0:  # Only add if angle is valid
                        vertices_with_angles.append((QgsPointXY(p2), angle, vertex_index, QgsPointXY(p1), QgsPointXY(p3)))
                        vertex_index += 1
        
        return vertices_with_angles
    
    def _create_arc_geometry(self, p1, vertex, p3, angle_rad, radius):
        """
        Create an arc geometry showing the interior angle at a vertex.
        
        Args:
            p1 (QgsPointXY): First adjacent point
            vertex (QgsPointXY): Vertex point where angle is measured
            p3 (QgsPointXY): Second adjacent point
            angle_rad (float): Interior angle in radians
            radius (float): Arc radius in map units
            
        Returns:
            QgsGeometry: Arc line geometry or None if failed
        """
        try:
            # Calculate vectors from vertex to adjacent points
            v1 = QgsPointXY(p1.x() - vertex.x(), p1.y() - vertex.y())
            v2 = QgsPointXY(p3.x() - vertex.x(), p3.y() - vertex.y())
            
            # Calculate angles of the two vectors
            angle1 = math.atan2(v1.y(), v1.x())
            angle2 = math.atan2(v2.y(), v2.x())
            
            # Normalize angles
            while angle1 < 0:
                angle1 += 2 * math.pi
            while angle2 < 0:
                angle2 += 2 * math.pi
            
            # Determine start and end angles for the interior angle
            # We want the arc that shows the interior angle (smaller angle between the two vectors)
            start_angle = angle1
            end_angle = angle2
            
            # Calculate angle difference
            angle_diff = (end_angle - start_angle) % (2 * math.pi)
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff
                # Swap if needed to get the interior angle
                start_angle, end_angle = end_angle, start_angle
                angle_diff = (end_angle - start_angle) % (2 * math.pi)
            
            # Create points along the arc
            num_points = max(10, int(angle_rad * 180 / math.pi))  # More points for larger angles
            arc_points = []
            
            for i in range(num_points + 1):
                t = i / num_points
                # Interpolate angle from start to end
                if angle_diff <= math.pi:
                    current_angle = start_angle + t * angle_diff
                else:
                    # Handle wrap-around case
                    current_angle = start_angle + t * (angle_diff - 2 * math.pi)
                
                x = vertex.x() + radius * math.cos(current_angle)
                y = vertex.y() + radius * math.sin(current_angle)
                arc_points.append(QgsPointXY(x, y))
            
            # Create line geometry
            return QgsGeometry.fromPolylineXY(arc_points)
            
        except Exception as e:
            print(f"Error creating arc geometry: {str(e)}")
            return None
    
    def _create_arc_layer(self, layer_name, crs):
        """
        Create a new line layer for storing angle arcs.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            # Create temporary memory layer
            layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            # Add fields
            provider = layer.dataProvider()
            fields = QgsFields()
            fields.append(QgsField('angle_deg', QVariant.Double))
            fields.append(QgsField('vertex_idx', QVariant.Int))
            fields.append(QgsField('feature_id', QVariant.Int))
            
            provider.addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            print(f"Error creating arc layer: {str(e)}")
            return None
    
    def _enable_labeling(self, layer, angle_field_name, angle_unit='degrees'):
        """
        Enable labeling on a layer to show angle values.
        
        Args:
            layer (QgsVectorLayer): Layer to enable labeling on
            angle_field_name (str): Name of the field to use for labeling
            angle_unit (str): 'degrees' or 'radians' - used to add unit symbol
        """
        try:
            from qgis.core import QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
            from qgis.PyQt.QtGui import QColor
            
            # Create labeling settings
            pal_layer_settings = QgsPalLayerSettings()
            pal_layer_settings.enabled = True
            
            # Create expression to format angle with unit symbol
            if angle_unit == 'degrees':
                # Format as: "67°" or "132°" using QGIS expression
                pal_layer_settings.fieldName = f'to_string("{angle_field_name}") || \'°\''
                pal_layer_settings.isExpression = True
            else:
                # For radians, just show the value
                pal_layer_settings.fieldName = angle_field_name
                pal_layer_settings.isExpression = False
            
            # Configure text format
            text_format = QgsTextFormat()
            text_format.setSize(12)
            text_format.setColor(QColor(0, 0, 0, 255))
            pal_layer_settings.setFormat(text_format)
            
            # Set placement for point layers - place labels around the point
            pal_layer_settings.placement = QgsPalLayerSettings.AroundPoint
            
            # Apply labeling settings
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal_layer_settings))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
            
        except Exception as e:
            print(f"Error enabling labeling: {str(e)}")
            # Labeling is optional, so we don't fail if it doesn't work
    
    def _create_angle_layer(self, layer_name, crs, angle_unit, include_vertex_index, include_feature_id):
        """
        Create a new point layer for storing angle measurements.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            angle_unit (str): 'degrees' or 'radians'
            include_vertex_index (bool): Whether to include vertex index field
            include_feature_id (bool): Whether to include feature ID field
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            # Create temporary memory layer
            layer = QgsVectorLayer(f"Point?crs={crs.authid()}", layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            # Add fields
            provider = layer.dataProvider()
            fields = QgsFields()
            
            # Angle field
            angle_field_name = 'angle_deg' if angle_unit == 'degrees' else 'angle_rad'
            fields.append(QgsField(angle_field_name, QVariant.Double))
            
            # Optional fields
            if include_vertex_index:
                fields.append(QgsField('vertex_idx', QVariant.Int))
            
            if include_feature_id:
                fields.append(QgsField('feature_id', QVariant.Int))
            
            provider.addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            print(f"Error creating angle layer: {str(e)}")
            return None
    
    def execute(self, context):
        """
        Execute the show polygon layer angles action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Polygon Layer Angles'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            process_selected_only = bool(self.get_setting('process_selected_only', False))
            skip_invalid_geometries = bool(self.get_setting('skip_invalid_geometries', True))
            angle_unit = str(self.get_setting('angle_unit', 'degrees'))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_angle_arcs = bool(self.get_setting('show_angle_arcs', True))
            arc_radius = float(self.get_setting('arc_radius', 0.0))
            include_vertex_index = bool(self.get_setting('include_vertex_index', True))
            include_feature_id = bool(self.get_setting('include_feature_id', True))
            show_success_message = bool(self.get_setting('show_success_message', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements - for layer actions, get the layer
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        # Get the layer from the first detected feature
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Validate layer geometry type
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return
        
        try:
            # Get features to process
            if process_selected_only and layer.selectedFeatureCount() > 0:
                features = layer.selectedFeatures()
                total_features = layer.selectedFeatureCount()
            else:
                features = layer.getFeatures()
                total_features = layer.featureCount()
            
            if total_features == 0:
                self.show_error("Error", "No features to process in the layer")
                return
            
            # Collect all vertices with angles from all features
            all_vertices_with_angles = []
            processed_features = 0
            error_count = 0
            
            for feature in features:
                geometry = feature.geometry()
                
                if not geometry or geometry.isEmpty():
                    if skip_invalid_geometries:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature {feature.id()} has invalid geometry")
                        return
                
                # Validate geometry type
                if geometry.type() != QgsWkbTypes.PolygonGeometry:
                    if skip_invalid_geometries:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature {feature.id()} is not a polygon")
                        return
                
                # Extract vertices and calculate angles
                vertices_with_angles = self._extract_vertices_and_angles(geometry)
                
                # Add feature ID to each vertex tuple
                for vertex_data in vertices_with_angles:
                    vertex_point, angle_rad, vertex_idx, p1, p3 = vertex_data
                    all_vertices_with_angles.append((vertex_point, angle_rad, vertex_idx, p1, p3, feature.id()))
                
                processed_features += 1
            
            if not all_vertices_with_angles:
                self.show_error("Error", "Could not extract vertices from any polygons")
                return
            
            # Calculate auto arc radius if needed (based on layer extent)
            if show_angle_arcs and arc_radius == 0.0:
                layer_extent = layer.extent()
                width = layer_extent.width()
                height = layer_extent.height()
                avg_size = (width + height) / 2.0
                arc_radius = avg_size * 0.05  # 5% of average dimension for layer-wide processing
            
            # Create output layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Angles Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer = self._create_angle_layer(
                    output_layer_name, layer.crs(), angle_unit, include_vertex_index, include_feature_id
                )
                
                if not temp_layer:
                    self.show_error("Error", "Failed to create temporary layer")
                    return
                
                # Add features to temporary layer
                provider = temp_layer.dataProvider()
                features_to_add = []
                
                angle_field_name = 'angle_deg' if angle_unit == 'degrees' else 'angle_rad'
                
                for vertex_point, angle_rad, vertex_idx, p1, p3, feature_id in all_vertices_with_angles:
                    # Convert angle if needed
                    if angle_unit == 'degrees':
                        angle_value = math.degrees(angle_rad)
                    else:
                        angle_value = angle_rad
                    
                    # Round to specified decimal places
                    angle_value = round(angle_value, decimal_places)
                    
                    # Create feature
                    new_feature = QgsFeature(temp_layer.fields())
                    new_feature.setGeometry(QgsGeometry.fromPointXY(vertex_point))
                    
                    # Set attributes
                    attr_idx = 0
                    new_feature.setAttribute(attr_idx, angle_value)
                    attr_idx += 1
                    
                    if include_vertex_index:
                        new_feature.setAttribute(attr_idx, vertex_idx)
                        attr_idx += 1
                    
                    if include_feature_id:
                        new_feature.setAttribute(attr_idx, feature_id)
                    
                    features_to_add.append(new_feature)
                
                provider.addFeatures(features_to_add)
                temp_layer.updateExtents()
                
                # Enable labeling to show angle values
                self._enable_labeling(temp_layer, angle_field_name, angle_unit)
                
                # Save temporary layer to file
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    temp_layer, save_path, "UTF-8", temp_layer.crs(), "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer to file: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load the saved layer
                output_layer = QgsVectorLayer(save_path, output_layer_name, "ogr")
                if not output_layer.isValid():
                    self.show_error("Error", "Failed to load saved layer")
                    return
                
                # Enable labeling on the loaded layer
                self._enable_labeling(output_layer, angle_field_name, angle_unit)
            else:
                # Create temporary in-memory layer
                output_layer = self._create_angle_layer(
                    output_layer_name, layer.crs(), angle_unit, include_vertex_index, include_feature_id
                )
                
                if not output_layer:
                    self.show_error("Error", "Failed to create output layer")
                    return
                
                # Add features to layer
                provider = output_layer.dataProvider()
                features_to_add = []
                
                angle_field_name = 'angle_deg' if angle_unit == 'degrees' else 'angle_rad'
                
                for vertex_point, angle_rad, vertex_idx, p1, p3, feature_id in all_vertices_with_angles:
                    # Convert angle if needed
                    if angle_unit == 'degrees':
                        angle_value = math.degrees(angle_rad)
                    else:
                        angle_value = angle_rad
                    
                    # Round to specified decimal places
                    angle_value = round(angle_value, decimal_places)
                    
                    # Create feature
                    new_feature = QgsFeature(output_layer.fields())
                    new_feature.setGeometry(QgsGeometry.fromPointXY(vertex_point))
                    
                    # Set attributes
                    attr_idx = 0
                    new_feature.setAttribute(attr_idx, angle_value)
                    attr_idx += 1
                    
                    if include_vertex_index:
                        new_feature.setAttribute(attr_idx, vertex_idx)
                        attr_idx += 1
                    
                    if include_feature_id:
                        new_feature.setAttribute(attr_idx, feature_id)
                    
                    features_to_add.append(new_feature)
                
                provider.addFeatures(features_to_add)
                output_layer.updateExtents()
                
                # Enable labeling to show angle values
                self._enable_labeling(output_layer, angle_field_name, angle_unit)
            
            # Create arc layer if requested
            arc_layer = None
            if show_angle_arcs:
                arc_layer_name = f"{output_layer_name} - Arcs"
                arc_layer = self._create_arc_layer(arc_layer_name, layer.crs())
                
                if arc_layer:
                    provider = arc_layer.dataProvider()
                    arc_features = []
                    
                    for vertex_point, angle_rad, vertex_idx, p1, p3, feature_id in all_vertices_with_angles:
                        # Create arc geometry
                        arc_geom = self._create_arc_geometry(p1, vertex_point, p3, angle_rad, arc_radius)
                        
                        if arc_geom and not arc_geom.isEmpty():
                            # Convert angle for display
                            if angle_unit == 'degrees':
                                angle_value = round(math.degrees(angle_rad), decimal_places)
                            else:
                                angle_value = round(angle_rad, decimal_places)
                            
                            # Create feature
                            arc_feature = QgsFeature(arc_layer.fields())
                            arc_feature.setGeometry(arc_geom)
                            arc_feature.setAttribute(0, angle_value)
                            arc_feature.setAttribute(1, vertex_idx)
                            arc_feature.setAttribute(2, feature_id)
                            arc_features.append(arc_feature)
                    
                    if arc_features:
                        provider.addFeatures(arc_features)
                        arc_layer.updateExtents()
            
            # Add layers to project if requested
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(output_layer)
                if arc_layer:
                    project.addMapLayer(arc_layer)
            
            # Show success message
            if show_success_message:
                unit_display = "degrees" if angle_unit == 'degrees' else "radians"
                self.show_info("Angles Calculated",
                    f"Successfully calculated angles for {processed_features} polygon(s).\n"
                    f"Total vertices processed: {len(all_vertices_with_angles)}\n"
                    f"New layer: {output_layer_name}\n"
                    f"Angle unit: {unit_display}\n"
                    f"Added to project: {'Yes' if add_to_project else 'No'}"
                    + (f"\nSkipped {error_count} invalid feature(s)." if error_count > 0 else ""))
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate polygon layer angles: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
show_polygon_layer_angles_action = ShowPolygonLayerAnglesAction()

