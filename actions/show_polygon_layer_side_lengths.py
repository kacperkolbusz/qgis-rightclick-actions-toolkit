"""
Show Polygon Layer Side Lengths Action for Right-click Utilities and Shortcuts Hub

Displays the length of each side in all polygon features in a layer by creating
labeled points at the midpoint of each side showing the side length.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsPointXY,
    QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
import math


class ShowPolygonLayerSideLengthsAction(BaseAction):
    """Action to display side lengths for all polygons in a layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "show_polygon_layer_side_lengths"
        self.name = "Show Polygon Layer Side Lengths"
        self.category = "Information"
        self.description = "Display the length of each side in all polygon features in a layer. Creates labeled points at the midpoint of each side showing the side length in map units. Works with polygon and multipolygon layers."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
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
                'default': 'Side Lengths_{source_layer}',
                'label': 'Layer Name Template',
                'description': 'Template for the side lengths layer name. Available variables: {source_layer}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created side lengths layer to the project',
            },
            
            # PROCESSING SETTINGS
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'Only process selected polygon features (if any are selected)',
            },
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip polygons with invalid or empty geometries instead of showing an error',
            },
            
            # DISPLAY SETTINGS
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in length values',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            'label_size': {
                'type': 'float',
                'default': 10.0,
                'label': 'Label Size',
                'description': 'Text size for side length labels',
                'min': 6.0,
                'max': 24.0,
                'step': 0.5,
            },
            'label_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Label Color',
                'description': 'Text color for side length labels',
            },
            'label_placement': {
                'type': 'choice',
                'default': 'around',
                'label': 'Label Placement',
                'description': 'Placement of labels relative to side midpoints',
                'options': ['around', 'over'],
            },
            'include_side_index': {
                'type': 'bool',
                'default': False,
                'label': 'Include Side Index',
                'description': 'Include side index number in labels (e.g., "1: 123.45 m")',
            },
            'include_feature_id': {
                'type': 'bool',
                'default': False,
                'label': 'Include Feature ID',
                'description': 'Include feature ID in labels to identify which polygon the side belongs to',
            },
            'include_total_perimeter': {
                'type': 'bool',
                'default': True,
                'label': 'Include Total Perimeter',
                'description': 'Show total perimeter of all polygons in information message',
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created side lengths layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after creating the side lengths layer',
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
    
    def _calculate_distance(self, point1, point2, crs=None):
        """
        Calculate Euclidean distance between two points.
        If CRS is geographic, creates a temporary line geometry and uses length() method
        which handles CRS transformation automatically.
        
        Args:
            point1 (QgsPointXY): First point
            point2 (QgsPointXY): Second point
            crs: Coordinate reference system (optional, for CRS-aware calculation)
            
        Returns:
            float: Distance between points
        """
        # If CRS is provided and is geographic, use line geometry length() method
        # which handles CRS transformation properly
        if crs and crs.isGeographic():
            try:
                # Create temporary line geometry
                line_geometry = QgsGeometry.fromPolylineXY([point1, point2])
                
                if not line_geometry or line_geometry.isEmpty():
                    # Fallback to simple distance
                    dx = point2.x() - point1.x()
                    dy = point2.y() - point1.y()
                    return math.sqrt(dx * dx + dy * dy)
                
                # Transform to projected CRS for accurate length calculation
                from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
                
                # Use UTM zone if possible, otherwise Web Mercator
                try:
                    # Get centroid to determine UTM zone
                    centroid_x = (point1.x() + point2.x()) / 2.0
                    centroid_y = (point1.y() + point2.y()) / 2.0
                    utm_zone = int((centroid_x + 180) / 6) + 1
                    hemisphere = 'north' if centroid_y >= 0 else 'south'
                    utm_epsg = f"EPSG:{32600 + utm_zone}" if hemisphere == 'north' else f"EPSG:{32700 + utm_zone}"
                    projected_crs = QgsCoordinateReferenceSystem(utm_epsg)
                except:
                    # Fallback to Web Mercator
                    projected_crs = QgsCoordinateReferenceSystem("EPSG:3857")
                
                # Transform line geometry to projected CRS
                transform = QgsCoordinateTransform(crs, projected_crs, QgsProject.instance())
                line_geometry.transform(transform)
                
                # Calculate length in projected CRS (now in meters)
                length = line_geometry.length()
                return length
                
            except Exception as e:
                print(f"Warning: CRS-aware distance calculation failed: {str(e)}, using simple distance")
                # Fallback to simple Euclidean distance
                dx = point2.x() - point1.x()
                dy = point2.y() - point1.y()
                return math.sqrt(dx * dx + dy * dy)
        else:
            # For projected CRS or no CRS, use simple Euclidean distance
            dx = point2.x() - point1.x()
            dy = point2.y() - point1.y()
            return math.sqrt(dx * dx + dy * dy)
    
    def _get_polygon_sides(self, geometry, crs):
        """
        Extract all sides from a polygon geometry by finding corner points and creating lines between them.
        Uses the exact same approach as show_line_segment_lengths - extract points, create segments, calculate distances.
        
        Args:
            geometry (QgsGeometry): Polygon geometry
            crs: Coordinate reference system (not used, kept for compatibility)
            
        Returns:
            list: List of dictionaries with 'start_point', 'end_point', 'midpoint', and 'length' for each side
        """
        sides = []
        
        if not geometry or geometry.isEmpty():
            return sides
        
        # Try to make valid if needed
        try:
            if not geometry.isGeosValid():
                geometry = geometry.makeValid()
                if geometry.isEmpty():
                    return sides
        except Exception as e:
            print(f"Warning: Could not validate geometry: {str(e)}")
        
        # Extract corner points (vertices) from polygon
        points = []
        
        # Method 1: Use asPolygon() / asMultiPolygon() to get polygon structure directly
        try:
            if geometry.isMultipart():
                # Multi-part polygon
                multi_polygon = geometry.asMultiPolygon()
                if multi_polygon and len(multi_polygon) > 0:
                    # Use first polygon (exterior ring is first ring)
                    polygon = multi_polygon[0]
                    if polygon and len(polygon) > 0:
                        # First ring is exterior ring
                        exterior_ring_points = polygon[0]
                        if exterior_ring_points and len(exterior_ring_points) >= 2:
                            for point in exterior_ring_points:
                                try:
                                    points.append(QgsPointXY(point.x(), point.y()))
                                except Exception:
                                    continue
            else:
                # Single-part polygon
                polygon = geometry.asPolygon()
                if polygon and len(polygon) > 0:
                    # First element is exterior ring
                    exterior_ring_points = polygon[0]
                    if exterior_ring_points and len(exterior_ring_points) >= 2:
                        for point in exterior_ring_points:
                            try:
                                points.append(QgsPointXY(point.x(), point.y()))
                            except Exception:
                                continue
        except Exception as e:
            print(f"Warning: asPolygon()/asMultiPolygon() method failed: {str(e)}")
        
        # Method 2: Try using boundary() if available (some QGIS versions)
        if not points or len(points) < 2:
            try:
                if hasattr(geometry, 'boundary'):
                    boundary = geometry.boundary()
                    if boundary and not boundary.isEmpty():
                        # Extract points from boundary line
                        if boundary.isMultipart():
                            multi_polyline = boundary.asMultiPolyline()
                            if multi_polyline and len(multi_polyline) > 0:
                                polyline = multi_polyline[0]  # Use first part (exterior ring)
                                if len(polyline) >= 2:
                                    for point in polyline:
                                        points.append(QgsPointXY(point))
                        else:
                            polyline = boundary.asPolyline()
                            if polyline and len(polyline) >= 2:
                                for point in polyline:
                                    points.append(QgsPointXY(point))
            except Exception as e:
                print(f"Warning: Boundary method failed: {str(e)}")
        
        # Method 3: Try exteriorRing() if available (some QGIS versions)
        if not points or len(points) < 2:
            try:
                if geometry.type() == QgsWkbTypes.PolygonGeometry:
                    if hasattr(geometry, 'exteriorRing'):
                        if geometry.isMultipart():
                            # Multi-part polygon - get first part
                            collection = geometry.asGeometryCollection()
                            if collection:
                                for part in collection:
                                    if part and part.type() == QgsWkbTypes.PolygonGeometry:
                                        exterior_ring = part.exteriorRing()
                                        if exterior_ring:
                                            num_points = exterior_ring.numPoints()
                                            if num_points >= 2:
                                                for i in range(num_points):
                                                    try:
                                                        point = exterior_ring.pointN(i)
                                                        if point:
                                                            points.append(QgsPointXY(point.x(), point.y()))
                                                    except Exception:
                                                        continue
                                                break
                        else:
                            # Single-part polygon
                            exterior_ring = geometry.exteriorRing()
                            if exterior_ring:
                                num_points = exterior_ring.numPoints()
                                if num_points >= 2:
                                    for i in range(num_points):
                                        try:
                                            point = exterior_ring.pointN(i)
                                            if point:
                                                points.append(QgsPointXY(point.x(), point.y()))
                                        except Exception:
                                            continue
            except Exception as e:
                print(f"Warning: ExteriorRing method failed: {str(e)}")
        
        # Check if we have enough points
        if not points or len(points) < 2:
            print(f"Error: Could not extract enough points from polygon. Found {len(points)} points.")
            return sides
        
        # Remove duplicate last point if polygon is closed (first == last)
        # Polygons are closed, so the last vertex is the same as the first
        if len(points) > 2:
            first = points[0]
            last = points[-1]
            tolerance = 1e-10
            if abs(first.x() - last.x()) < tolerance and abs(first.y() - last.y()) < tolerance:
                points = points[:-1]  # Remove duplicate last point
        
        if len(points) < 2:
            print(f"Error: Not enough points after removing duplicate. Found {len(points)} points.")
            return sides
        
        # Create segments between consecutive corner points - EXACTLY like line action
        for i in range(len(points)):
            start_point = points[i]
            # Next point (wrap around for closed polygon)
            end_point = points[(i + 1) % len(points)]
            
            # Calculate length using CRS-aware distance calculation
            side_length = self._calculate_distance(start_point, end_point, crs)
            
            # Calculate midpoint
            midpoint = QgsPointXY(
                (start_point.x() + end_point.x()) / 2.0,
                (start_point.y() + end_point.y()) / 2.0
            )
            
            sides.append({
                'start_point': start_point,
                'end_point': end_point,
                'midpoint': midpoint,
                'length': side_length
            })
        
        return sides
    
    def _calculate_side_midpoint(self, start_point, end_point):
        """
        Calculate midpoint of a polygon side.
        
        Args:
            start_point (QgsPointXY): Start point of side
            end_point (QgsPointXY): End point of side
            
        Returns:
            QgsPointXY: Midpoint of the side
        """
        mid_x = (start_point.x() + end_point.x()) / 2.0
        mid_y = (start_point.y() + end_point.y()) / 2.0
        return QgsPointXY(mid_x, mid_y)
    
    def _create_side_lengths_layer(self, layer_name, crs, include_side_index, include_feature_id):
        """
        Create a point layer for displaying side lengths.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            include_side_index (bool): Whether to include side index field
            include_feature_id (bool): Whether to include feature ID field
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            # Create memory layer
            layer = QgsVectorLayer(f"Point?crs={crs.authid()}", layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('side_length', QVariant.Double))
            
            if include_side_index:
                fields.append(QgsField('side_index', QVariant.Int))
            
            if include_feature_id:
                fields.append(QgsField('feature_id', QVariant.Int))
            
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create side lengths layer: {str(e)}")
            return None
    
    def _enable_labeling(self, layer, length_field_name, decimal_places, label_size, label_color, label_placement, include_side_index, include_feature_id):
        """
        Enable labeling on the layer to show side lengths.
        
        Args:
            layer (QgsVectorLayer): Layer to enable labeling on
            length_field_name (str): Name of the length field
            decimal_places (int): Number of decimal places
            label_size (float): Label text size
            label_color (str): Label color (hex string)
            label_placement (str): Label placement option
            include_side_index (bool): Whether to include side index in label
            include_feature_id (bool): Whether to include feature ID in label
        """
        try:
            # Create labeling settings
            pal_layer_settings = QgsPalLayerSettings()
            pal_layer_settings.enabled = True
            
            # Create expression to format length
            parts = []
            if include_feature_id:
                parts.append('to_string("feature_id") || ": "')
            if include_side_index:
                parts.append('to_string("side_index") || ": "')
            
            parts.append(f'format_number("{length_field_name}", {decimal_places})')
            expression = ' || '.join(parts)
            
            pal_layer_settings.fieldName = expression
            pal_layer_settings.isExpression = True
            
            # Configure text format
            text_format = QgsTextFormat()
            text_format.setSize(label_size)
            
            # Parse color from hex string
            try:
                color = QColor(label_color)
                if not color.isValid():
                    color = QColor(0, 0, 0, 255)  # Default to black
            except:
                color = QColor(0, 0, 0, 255)  # Default to black
            
            text_format.setColor(color)
            pal_layer_settings.setFormat(text_format)
            
            # Set placement
            placement_map = {
                'around': QgsPalLayerSettings.AroundPoint,
                'over': QgsPalLayerSettings.OverPoint,
            }
            pal_layer_settings.placement = placement_map.get(label_placement, QgsPalLayerSettings.AroundPoint)
            
            # Apply labeling settings
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal_layer_settings))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
            
        except Exception as e:
            print(f"Warning: Could not enable labeling: {str(e)}")
            # Labeling is optional, so we don't fail if it doesn't work
    
    def _make_points_invisible(self, layer):
        """
        Make point symbols invisible so only labels are visible.
        
        Args:
            layer (QgsVectorLayer): Point layer to make invisible
        """
        try:
            from qgis.core import QgsMarkerSymbol, QgsSimpleMarkerSymbolLayer, QgsSingleSymbolRenderer
            from qgis.PyQt.QtGui import QColor
            
            # Create transparent marker symbol
            symbol_layer = QgsSimpleMarkerSymbolLayer()
            symbol_layer.setSize(0)  # Size 0 makes it invisible
            symbol_layer.setColor(QColor(255, 255, 255, 0))  # Transparent color
            
            # Create marker symbol
            symbol = QgsMarkerSymbol()
            symbol.changeSymbolLayer(0, symbol_layer)
            
            # Apply symbol to layer
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
        except Exception as e:
            print(f"Warning: Could not make points invisible: {str(e)}")
            # If styling fails, continue - labels will still work
    
    def execute(self, context):
        """Execute the show polygon layer side lengths action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
            layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
            add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
            process_selected_only = bool(self.get_setting('process_selected_only', schema['process_selected_only']['default']))
            skip_invalid_geometries = bool(self.get_setting('skip_invalid_geometries', schema['skip_invalid_geometries']['default']))
            decimal_places = int(self.get_setting('decimal_places', schema['decimal_places']['default']))
            label_size = float(self.get_setting('label_size', schema['label_size']['default']))
            label_color = str(self.get_setting('label_color', schema['label_color']['default']))
            label_placement = str(self.get_setting('label_placement', schema['label_placement']['default']))
            include_side_index = bool(self.get_setting('include_side_index', schema['include_side_index']['default']))
            include_feature_id = bool(self.get_setting('include_feature_id', schema['include_feature_id']['default']))
            include_total_perimeter = bool(self.get_setting('include_total_perimeter', schema['include_total_perimeter']['default']))
            zoom_to_layer = bool(self.get_setting('zoom_to_layer', schema['zoom_to_layer']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
            return
        
        # Get the layer from the first detected feature
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Validate that this is a polygon layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return
        
        try:
            # Get features to process
            if process_selected_only:
                features = list(layer.selectedFeatures())
                if not features:
                    self.show_warning("No Selection", "No features are selected. Please select features first or disable 'Process Selected Features Only' setting.")
                    return
            else:
                features = list(layer.getFeatures())
            
            if not features:
                self.show_error("Error", "No features found in layer")
                return
            
            # Process all features and collect side data
            all_side_data = []
            total_perimeter = 0.0
            features_processed = 0
            features_skipped = 0
            
            for feature in features:
                geometry = feature.geometry()
                
                if not geometry or geometry.isEmpty():
                    if skip_invalid_geometries:
                        features_skipped += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature ID {feature.id()} has invalid or empty geometry")
                        return
                
                # Extract all sides from the polygon (exterior ring only)
                # This method creates temporary line geometries to calculate accurate lengths
                try:
                    sides = self._get_polygon_sides(geometry, layer.crs())
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    print(f"Exception in _get_polygon_sides for feature ID {feature.id()}: {error_details}")
                    
                    if skip_invalid_geometries:
                        print(f"Warning: Failed to extract sides from feature ID {feature.id()}: {str(e)}")
                        features_skipped += 1
                        continue
                    else:
                        error_msg = (
                            f"Failed to extract sides from feature ID {feature.id()}.\n\n"
                            f"Error: {str(e)}\n\n"
                            f"Layer: {layer.name()}\n"
                            f"Geometry Type: {geometry.type()}\n"
                            f"Geometry Valid: {geometry.isGeosValid() if hasattr(geometry, 'isGeosValid') else 'Unknown'}\n"
                            f"Geometry Empty: {geometry.isEmpty()}\n\n"
                            f"Please check the QGIS Python console for detailed error messages."
                        )
                        self.show_error("Error", error_msg)
                        return
                
                if not sides:
                    # Get detailed diagnostic information
                    geometry_type = geometry.type()
                    is_empty = geometry.isEmpty()
                    is_valid = "Unknown"
                    try:
                        is_valid = str(geometry.isGeosValid())
                    except:
                        pass
                    
                    # Try to get more info
                    boundary_info = "Not attempted"
                    exterior_ring_info = "Not attempted"
                    points_found = 0
                    
                    try:
                        boundary = geometry.boundary()
                        if boundary:
                            boundary_info = f"Success (multipart: {boundary.isMultipart()}, empty: {boundary.isEmpty()})"
                            if not boundary.isEmpty():
                                if boundary.isMultipart():
                                    try:
                                        multi_polyline = boundary.asMultiPolyline()
                                        if multi_polyline:
                                            points_found = len(multi_polyline[0]) if len(multi_polyline) > 0 else 0
                                    except:
                                        pass
                                else:
                                    try:
                                        polyline = boundary.asPolyline()
                                        points_found = len(polyline) if polyline else 0
                                    except:
                                        pass
                        else:
                            boundary_info = "Returned None"
                    except Exception as e:
                        boundary_info = f"Failed: {str(e)}"
                    
                    try:
                        if geometry.type() == QgsWkbTypes.PolygonGeometry:
                            if geometry.isMultipart():
                                collection = geometry.asGeometryCollection()
                                if collection:
                                    for part in collection:
                                        if part and part.type() == QgsWkbTypes.PolygonGeometry:
                                            exterior_ring = part.exteriorRing()
                                            if exterior_ring:
                                                num_points = exterior_ring.numPoints()
                                                exterior_ring_info = f"Success (points: {num_points})"
                                                break
                                            else:
                                                exterior_ring_info = "Returned None"
                            else:
                                exterior_ring = geometry.exteriorRing()
                                if exterior_ring:
                                    num_points = exterior_ring.numPoints()
                                    exterior_ring_info = f"Success (points: {num_points})"
                                else:
                                    exterior_ring_info = "Returned None"
                    except Exception as e:
                        exterior_ring_info = f"Failed: {str(e)}"
                    
                    if skip_invalid_geometries:
                        print(f"Warning: Could not extract sides from feature ID {feature.id()}")
                        print(f"  Geometry Type: {geometry_type}, Empty: {is_empty}, Valid: {is_valid}")
                        print(f"  Boundary: {boundary_info}, Points: {points_found}")
                        print(f"  ExteriorRing: {exterior_ring_info}")
                        features_skipped += 1
                        continue
                    else:
                        error_msg = (
                            f"Could not extract sides from feature ID {feature.id()}.\n\n"
                            f"Diagnostic Information:\n"
                            f"Layer: {layer.name()}\n"
                            f"Geometry Type: {geometry_type}\n"
                            f"Geometry Empty: {is_empty}\n"
                            f"Geometry Valid: {is_valid}\n"
                            f"Is Multipart: {geometry.isMultipart()}\n\n"
                            f"Boundary Method: {boundary_info}\n"
                            f"Points from boundary: {points_found}\n"
                            f"ExteriorRing Method: {exterior_ring_info}\n\n"
                            f"Possible causes:\n"
                            f"- Invalid or corrupted geometry\n"
                            f"- Unsupported geometry type\n"
                            f"- Geometry has no vertices\n"
                            f"- CRS transformation issue\n\n"
                            f"Please check the QGIS Python console for detailed error messages."
                        )
                        self.show_error("Error", error_msg)
                        return
                
                # Process sides data
                for i, side_info in enumerate(sides):
                    side_length = side_info['length']
                    total_perimeter += side_length
                    
                    all_side_data.append({
                        'midpoint': side_info['midpoint'],
                        'length': side_length,
                        'side_index': i + 1,
                        'feature_id': feature.id()
                    })
                
                features_processed += 1
            
            if not all_side_data:
                self.show_error("Error", "No valid sides found in any features")
                return
            
            # Generate output layer name
            source_layer_name = layer.name()
            output_layer_name = self._generate_output_layer_name(layer_name_template, source_layer_name)
            
            # Determine output path based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Side Lengths Layer As",
                    "",
                    "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                output_path = save_path
            else:
                output_path = None  # Temporary layer
            
            # Create side lengths layer
            side_layer = self._create_side_lengths_layer(
                output_layer_name,
                layer.crs(),
                include_side_index,
                include_feature_id
            )
            
            if not side_layer:
                self.show_error("Error", "Failed to create side lengths layer")
                return
            
            # Add side points to layer
            side_layer.startEditing()
            
            for side_info in all_side_data:
                point_feature = QgsFeature()
                point_geometry = QgsGeometry.fromPointXY(side_info['midpoint'])
                point_feature.setGeometry(point_geometry)
                
                # Set attributes
                attributes = [round(side_info['length'], decimal_places)]
                if include_side_index:
                    attributes.append(side_info['side_index'])
                if include_feature_id:
                    attributes.append(side_info['feature_id'])
                
                point_feature.setAttributes(attributes)
                side_layer.addFeature(point_feature)
            
            side_layer.commitChanges()
            
            # Make points invisible (only labels visible)
            self._make_points_invisible(side_layer)
            
            # Enable labeling
            self._enable_labeling(
                side_layer,
                'side_length',
                decimal_places,
                label_size,
                label_color,
                label_placement,
                include_side_index,
                include_feature_id
            )
            
            # Save to file if permanent
            if layer_storage_type == 'permanent' and output_path:
                from qgis.core import QgsVectorFileWriter
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    side_layer,
                    output_path,
                    "UTF-8",
                    side_layer.crs(),
                    "GPKG" if output_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load saved layer
                saved_layer = QgsVectorLayer(output_path, output_layer_name, "ogr")
                if saved_layer.isValid():
                    # Make points invisible
                    self._make_points_invisible(saved_layer)
                    
                    # Copy labeling settings
                    self._enable_labeling(
                        saved_layer,
                        'side_length',
                        decimal_places,
                        label_size,
                        label_color,
                        label_placement,
                        include_side_index,
                        include_feature_id
                    )
                    side_layer = saved_layer
                else:
                    self.show_error("Error", "Failed to load saved layer")
                    return
            
            # Add to project if requested
            if add_to_project:
                QgsProject.instance().addMapLayer(side_layer)
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                try:
                    # Get layer extent
                    layer_extent = side_layer.extent()
                    
                    # Transform extent to canvas CRS if needed
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = side_layer.crs()
                    
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
                
                # Get unit name - if geographic CRS, we transformed to projected, so use meters
                crs = layer.crs()
                if crs.isGeographic():
                    # We transformed to UTM/Web Mercator, so use meters
                    unit_name = "meters"
                elif crs.isValid() and crs.mapUnits() != 0:
                    unit_name = crs.mapUnits().name().lower()
                else:
                    unit_name = "units"
                
                message = f"Side lengths layer '{output_layer_name}' {storage_info} successfully.\n\n"
                message += f"Features processed: {features_processed}\n"
                if features_skipped > 0:
                    message += f"Features skipped: {features_skipped}\n"
                message += f"Total sides: {len(all_side_data)}\n"
                
                if include_total_perimeter:
                    message += f"Total perimeter: {total_perimeter:.{decimal_places}f} {unit_name}\n"
                
                message += f"Labels displayed at side midpoints"
                
                self.show_info("Side Lengths Displayed", message)
        
        except Exception as e:
            self.show_error("Error", f"Failed to show side lengths: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
show_polygon_layer_side_lengths = ShowPolygonLayerSideLengthsAction()

