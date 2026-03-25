"""
Calculate Polygon Angles Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the interior angles at each vertex of a polygon feature.
Creates a point layer with angle measurements at each vertex location.
"""

import math
from .base_action import BaseAction
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsField, QgsFields, QgsProject, QgsWkbTypes, QgsVectorFileWriter
from qgis.PyQt.QtCore import QVariant


class CalculatePolygonAnglesAction(BaseAction):
    """
    Action to calculate and display interior angles at polygon vertices.
    
    This action extracts all vertices from a polygon feature, calculates the interior
    angle at each vertex, and creates a point layer with angle measurements.
    Works with both single and multipart polygons.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_polygon_angles"
        self.name = "Show Polygon Angles"
        self.category = "Analysis"
        self.description = "Calculate and display the interior angles at each vertex of the selected polygon feature. Creates a point layer with angle measurements at each vertex location. Works with both single and multipart polygons."
        self.enabled = True
        
        # Action scoping - works on individual polygon features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def supports_undo(self) -> bool:
        """This action supports undo for created output layers (remove layer)."""
        return True

    def get_undo_category(self) -> str:
        return 'complex'

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
                'default': 'Polygon Angles',
                'label': 'Output Layer Name',
                'description': 'Name for the new point layer containing angle measurements',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the new point layer to the current project',
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
        
        # Create vectors along the polygon edges (not from vertex)
        # Edge 1: from p1 to p2
        v1_x = p2.x() - p1.x()
        v1_y = p2.y() - p1.y()
        # Edge 2: from p2 to p3
        v2_x = p3.x() - p2.x()
        v2_y = p3.y() - p2.y()
        
        # Calculate magnitudes
        mag1 = math.sqrt(v1_x * v1_x + v1_y * v1_y)
        mag2 = math.sqrt(v2_x * v2_x + v2_y * v2_y)
        
        # Avoid division by zero
        if mag1 < 1e-10 or mag2 < 1e-10:
            return 0.0
        
        # Calculate dot product
        dot_product = v1_x * v2_x + v1_y * v2_y
        
        # Calculate angle using arccos
        cos_angle = dot_product / (mag1 * mag2)
        
        # Clamp to valid range for arccos
        cos_angle = max(-1.0, min(1.0, cos_angle))
        
        # Calculate angle using arccos (this gives us the angle between vectors, 0 to π)
        angle = math.acos(cos_angle)
        
        # Calculate cross product to determine which side of the angle is interior
        # Cross product: v1 × v2 = v1_x * v2_y - v1_y * v2_x
        cross_product = v1_x * v2_y - v1_y * v2_x
        
        # For interior angles:
        # - If polygon is counter-clockwise (positive area), cross product > 0 means interior angle
        # - If polygon is clockwise (negative area), cross product < 0 means interior angle
        # The cross product tells us which side of the angle is "inside" the polygon
        
        # The angle from arccos is always between 0 and π (0 to 180°)
        # For interior angles, we want the angle that is inside the polygon
        # If the cross product is negative, we're measuring the exterior angle, so we need 2π - angle
        # But wait, interior angles are always < 180°, so if angle > 180°, we have the wrong one
        
        # Actually, the issue is simpler: we need to check if we're getting the interior or exterior angle
        # The cross product sign tells us the orientation, but for interior angles, we always want
        # the smaller angle (which is what arccos gives us, 0 to π)
        
        # However, if the cross product indicates we're on the "outside", we need to take 2π - angle
        # But interior angles are always ≤ 180°, so if angle > π, we have the exterior angle
        
        # Actually, let me reconsider: arccos always gives 0 to π, which is the smaller angle
        # between the two vectors. For a polygon vertex, this is the interior angle if the polygon
        # is convex. For concave vertices, the interior angle might be > 180° (reflex angle).
        
        # The key insight: we need to determine if the angle we calculated is interior or exterior
        # The cross product of the edge vectors tells us the turning direction
        
        # For a counter-clockwise polygon:
        # - Left turn (interior) = positive cross product
        # - Right turn (exterior) = negative cross product
        # For interior angles, if cross product is negative, we have the exterior angle (2π - angle)
        
        # But wait, interior angles can be > 180° (reflex angles). So we need to check:
        # If cross product < 0, we're measuring the exterior angle, so interior = 2π - angle
        # If cross product > 0, we're measuring the interior angle directly
        
        # However, for most polygons, interior angles are < 180°, so if we get > 180°, it's likely wrong
        
        # Let's use a simpler approach: check if the calculated angle makes sense
        # For interior angles in simple polygons, they're typically < 180°
        # If cross product suggests we're on the wrong side, use 2π - angle
        
        # Actually, the real issue: we want the angle INSIDE the polygon
        # The cross product of edge vectors tells us the turning direction
        # If we're turning right (negative cross), and the angle is < 180°, we might have the exterior
        # But for interior angles, we want the angle that's inside
        
        # Let me use a geometric approach: calculate both possible angles and choose the interior one
        # The interior angle is the one that's inside the polygon
        
        # For now, let's assume that if the angle is > 180° (π), we should use 2π - angle
        # But arccos always gives ≤ π, so we need a different approach
        
        # The correct approach: use the cross product to determine if we need to flip
        # If cross product < 0, the interior angle is 2π - angle (for reflex angles)
        # But for most cases, interior angles are < 180°, so we should use the smaller angle
        
        # Actually, I think the real fix is simpler: we need to ensure we're measuring
        # the angle that's inside the polygon. The cross product of the edge vectors
        # (v1 × v2) tells us the signed area, which indicates which side is interior
        
        # For a properly oriented polygon (counter-clockwise outer ring):
        # - Positive cross product = left turn = interior angle
        # - Negative cross product = right turn = might be exterior
        
        # But wait, if the polygon is clockwise, the logic reverses
        
        # Let's use a more robust method: calculate the angle and check if it's the interior
        # by using the polygon's area sign to determine orientation
        
        # For now, let's fix it by ensuring we get the interior angle:
        # If cross product < 0 and angle < π, we might have the exterior angle
        # So interior = 2π - angle
        # But interior angles are typically < 180°, so this would give > 180°
        
        # Actually, I realize the issue: we're using vectors pointing FROM the vertex,
        # but we should be using vectors ALONG the edges. Let me recalculate:
        
        # Edge vectors (already correct above):
        # v1: from p1 to p2 (edge 1)
        # v2: from p2 to p3 (edge 2)
        
        # The angle between these vectors is what we want, but we need to ensure
        # we're getting the interior angle, not the exterior
        
        # The cross product v1 × v2 tells us the turning direction:
        # - Positive: turning left (counter-clockwise) - likely interior
        # - Negative: turning right (clockwise) - might be exterior
        
        # For interior angles, if we're turning right (negative cross), the interior
        # angle might be 2π - angle (for reflex angles > 180°)
        # But for most polygons, interior angles are < 180°
        
        # Let's use a simpler fix: if the angle seems wrong (too small for what we see),
        # we might need to use 2π - angle. But without knowing the expected value,
        # we can't do that.
        
        # The real fix: ensure we're calculating the angle correctly by using
        # the edge direction vectors and checking the polygon orientation
        
        # For now, let's assume that if cross product is negative, we might need to adjust
        # But actually, for interior angles in simple polygons, the angle from arccos
        # should be correct. The issue might be that we're using the wrong vectors.
        
        # Let me verify: we have p1, p2, p3 in order along the polygon boundary
        # Edge 1: p1 -> p2, vector = (p2 - p1) ✓
        # Edge 2: p2 -> p3, vector = (p3 - p2) ✓
        # Angle between these vectors = interior angle at p2 ✓
        
        # So the vectors are correct. The issue must be in how we interpret the result.
        # The angle from arccos is always 0 to π, which is the smaller angle.
        # For interior angles < 180°, this is correct.
        # For reflex angles > 180°, we need 2π - angle.
        
        # But how do we know if it's reflex? The cross product can help:
        # If cross product < 0 and the polygon is counter-clockwise, it's a reflex angle
        # But we don't know the polygon orientation easily.
        
        # Let's use a heuristic: if the angle is very small (< 30°) but the cross product
        # suggests we should have a larger angle, we might have the wrong one.
        # But this is not reliable.
        
        # The real solution: calculate the angle correctly by ensuring we use the right
        # side. Since we want the interior angle, and interior angles are typically
        # the smaller angle for convex vertices, the arccos result should be correct.
        # For reflex angles, we need 2π - angle.
        
        # Let's check: if cross product < 0, it might indicate a reflex angle
        # For a reflex angle, interior = 2π - exterior, and exterior = angle (from arccos)
        # So interior = 2π - angle
        
        # But we need to know if it's actually a reflex angle. One way: if the angle
        # from arccos is < 90° but the visual angle looks > 270°, it's reflex.
        # But we can't determine this from the math alone.
        
        # Actually, I think the issue is simpler: we're getting the exterior angle
        # because of how we're calculating. Let me check the vector directions again.
        
        # If we have p1, p2, p3 and we want the interior angle at p2:
        # - We need the angle between the incoming edge (p1->p2) and outgoing edge (p2->p3)
        # - But we're measuring the angle between vectors from p2, which gives the exterior
        
        # The fix: use vectors along the edges, but reverse one so they both point from p2
        # OR: use the angle between the reversed vectors
        
        # Actually, I think I see it now: we want the angle INSIDE the polygon.
        # The vectors v1 (p2-p1) and v2 (p3-p2) both point away from p1 and p2 respectively.
        # To get the interior angle, we need the angle between these vectors as they
        # appear from inside the polygon.
        
        # The simplest fix: if the cross product suggests we're on the wrong side,
        # use 2π - angle for the interior angle (but only if angle < π, otherwise
        # angle is already > 180° which is wrong for most cases)
        
        # Let me try a different approach: use atan2 to get the angle of each edge,
        # then calculate the difference, accounting for the interior side.
        
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
        Execute the calculate polygon angles action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Polygon Angles'))
            add_to_project = bool(self.get_setting('add_to_project', True))
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
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get feature geometry
            geometry = feature.geometry()
            if not geometry or geometry.isEmpty():
                self.show_error("Error", "Feature has no valid geometry")
                return
            
            # Validate geometry type
            if geometry.type() != QgsWkbTypes.PolygonGeometry:
                self.show_error("Error", "This action only works with polygon features")
                return
            
            # Extract vertices and calculate angles
            vertices_with_angles = self._extract_vertices_and_angles(geometry)
            
            if not vertices_with_angles:
                self.show_error("Error", "Could not extract vertices from polygon")
                return
            
            # Calculate auto arc radius if needed
            if show_angle_arcs and arc_radius == 0.0:
                # Auto-calculate radius based on polygon size
                bounds = geometry.boundingBox()
                width = bounds.width()
                height = bounds.height()
                avg_size = (width + height) / 2.0
                arc_radius = avg_size * 0.1  # 10% of average dimension
            
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
                
                for vertex_point, angle_rad, vertex_idx, p1, p3 in vertices_with_angles:
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
                        new_feature.setAttribute(attr_idx, feature.id())
                    
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
                
                for vertex_point, angle_rad, vertex_idx, p1, p3 in vertices_with_angles:
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
                        new_feature.setAttribute(attr_idx, feature.id())
                    
                    features_to_add.append(new_feature)
                
                provider.addFeatures(features_to_add)
                output_layer.updateExtents()
                
                # Enable labeling to show angle values
                self._enable_labeling(output_layer, angle_field_name, angle_unit)
            
            # Create arc layer if requested
            arc_layer = None
            if show_angle_arcs:
                arc_layer_name = f"{output_layer_name} - Arcs"
                
                if layer_storage_type == 'permanent':
                    # For permanent layers, arcs will be saved separately if needed
                    # For now, create temporary arc layer
                    arc_layer = self._create_arc_layer(arc_layer_name, layer.crs())
                else:
                    arc_layer = self._create_arc_layer(arc_layer_name, layer.crs())
                
                if arc_layer:
                    provider = arc_layer.dataProvider()
                    arc_features = []
                    
                    for vertex_point, angle_rad, vertex_idx, p1, p3 in vertices_with_angles:
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
            
                # Record create_layer undo entry so the user can remove the created layers
                try:
                    from ..history_manager import get_history_manager
                    hm = get_history_manager()

                    layers_list = [hm.create_layer_descriptor(output_layer)]
                    if arc_layer:
                        layers_list.append(hm.create_layer_descriptor(arc_layer))

                    description = f"Created angle layer '{output_layer_name}' with {len(vertices_with_angles)} vertices"
                    meta = {
                        'angle_unit': angle_unit,
                        'decimal_places': decimal_places,
                        'arc_radius': arc_radius,
                        'include_vertex_index': include_vertex_index,
                        'include_feature_id': include_feature_id,
                        'num_angles': len(vertices_with_angles),
                        'layer_storage_type': layer_storage_type
                    }

                    # Build full layer definitions (fields + features) so redo can recreate them
                    layer_definitions = []
                    for lyr in layers_list:
                        try:
                            layer_obj = QgsProject.instance().mapLayer(lyr.get('layer_id'))
                            if not layer_obj:
                                continue

                            # Fields metadata
                            fields_meta = []
                            for f in layer_obj.fields():
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
                                for feat in layer_obj.getFeatures():
                                    features_backup.append(self.create_feature_backup(feat, layer_obj))
                            except Exception:
                                features_backup = []

                            # Capture simple renderer / symbology properties (first symbol layer)
                            renderer_info = None
                            try:
                                renderer = layer_obj.renderer()
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
                                                # Some symbol layers expose 'properties' differently
                                                try:
                                                    sym_props = {k: sl.property(k) for k in []}
                                                except Exception:
                                                    sym_props = None
                                    except Exception:
                                        sym_props = None

                                renderer_info = {
                                    'renderer_type': getattr(renderer, 'type', None) if renderer is not None else None,
                                    'symbol_properties': sym_props
                                }
                            except Exception:
                                renderer_info = None

                            # Capture basic labeling settings if present
                            labeling_info = None
                            try:
                                labeling_mgr = layer_obj.labeling()
                                if labeling_mgr is not None and layer_obj.labelsEnabled():
                                    try:
                                        settings = labeling_mgr.settings()
                                    except Exception:
                                        settings = None

                                    if settings is not None:
                                        try:
                                            field_name = getattr(settings, 'fieldName', None)
                                            is_expr = getattr(settings, 'isExpression', False)
                                            placement = getattr(settings, 'placement', None)
                                        except Exception:
                                            field_name = None
                                            is_expr = False
                                            placement = None

                                        # Try to extract text size/color if available
                                        size = None
                                        color = None
                                        try:
                                            fmt = settings.format() if callable(getattr(settings, 'format', None)) else getattr(settings, 'format', None)
                                            if fmt is not None:
                                                size = getattr(fmt, 'size', None) if not callable(getattr(fmt, 'size', None)) else None
                                        except Exception:
                                            size = None

                                        labeling_info = {
                                            'enabled': True,
                                            'fieldName': field_name,
                                            'isExpression': bool(is_expr),
                                            'placement': placement,
                                            'size': size,
                                        }
                            except Exception:
                                labeling_info = None

                            layer_definitions.append({
                                'layer_name': layer_obj.name(),
                                'crs': layer_obj.crs().authid() if layer_obj.crs().isValid() else '',
                                'geometry_type': QgsWkbTypes.displayString(layer_obj.wkbType()),
                                'wkb_type': int(layer_obj.wkbType()),
                                'fields': fields_meta,
                                'features': features_backup,
                                'labeling': labeling_info,
                                'renderer': renderer_info
                            })
                        except Exception:
                            continue

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
            # Show success message
            if show_success_message:
                unit_display = "degrees" if angle_unit == 'degrees' else "radians"
                self.show_info("Angles Calculated",
                    f"Successfully calculated {len(vertices_with_angles)} angles.\n"
                    f"New layer: {output_layer_name}\n"
                    f"Angle unit: {unit_display}\n"
                    f"Added to project: {'Yes' if add_to_project else 'No'}")
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate polygon angles: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_polygon_angles_action = CalculatePolygonAnglesAction()

