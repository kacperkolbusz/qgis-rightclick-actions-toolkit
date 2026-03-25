"""
Feature Detection Module for Right-click Utilities and Shortcuts Hub

This module provides smart feature detection at cursor position, supporting
multiple feature types and overlapping features detection.
"""

from qgis.core import (
    QgsVectorLayer, QgsFeatureRequest, QgsRectangle, QgsWkbTypes,
    QgsGeometry, QgsPointXY, QgsSpatialIndex, QgsProject, QgsCoordinateTransform
)
from qgis.gui import QgsMapMouseEvent
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DetectedFeature:
    """
    Represents a detected feature with its metadata.
    """
    feature: 'QgsFeature'
    layer: QgsVectorLayer
    geometry_type: str  # 'point', 'multipoint', 'line', 'multiline', 'polygon', 'multipolygon'
    distance: float  # Distance from click point (for prioritization)


class FeatureDetector:
    """
    Smart feature detector that identifies features at cursor position.
    
    Supports detection of:
    - Point features (with extended 10-pixel search area)
    - Multipoint features (with extended 10-pixel search area)
    - Line features (with extended 10-pixel search area for easier clicking)
    - Multiline features (with extended 10-pixel search area)
    - Polygon features (8-pixel tolerance with boundary detection for transparent fills)
    - Multipolygon features (8-pixel tolerance with boundary detection for transparent fills)
    - Multiple overlapping features
    """
    
    def __init__(self, canvas):
        """
        Initialize the feature detector.
        
        Args:
            canvas: QGIS map canvas instance
        """
        self.canvas = canvas
        self.point_search_radius = 10  # pixels - extended search for points and lines
        self.default_tolerance = 15  # pixels - default search tolerance for polygons (increased for better outline detection)
        
    def detect_features_at_point(self, event: QgsMapMouseEvent) -> List[DetectedFeature]:
        """
        Detect all features at the clicked point.
        
        Args:
            event: Mouse event containing click coordinates
            
        Returns:
            List of DetectedFeature objects, sorted by priority
        """
        click_pt = event.mapPoint()
        detected_features = []
        
        print(f"DEBUG: Click point: {click_pt.x()}, {click_pt.y()}")
        
        # Get all visible vector layers
        visible_layers = self._get_visible_vector_layers()
        
        print(f"DEBUG: Found {len(visible_layers)} visible vector layers")
        
        for layer in visible_layers:
            # Detect features in this layer
            layer_features = self._detect_features_in_layer(layer, click_pt)
            detected_features.extend(layer_features)
        
        print(f"DEBUG: Total detected features: {len(detected_features)}")
        
        # Sort by priority: points first (closest), then lines, then polygons
        return self._sort_features_by_priority(detected_features)
    
    def _get_visible_vector_layers(self) -> List[QgsVectorLayer]:
        """
        Get all visible vector layers in the project.
        
        Returns:
            List of visible vector layers
        """
        visible_layers = []
        project = QgsProject.instance()
        layer_tree_root = project.layerTreeRoot()
        
        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                # Check if layer is visible in the layer tree
                layer_tree_layer = layer_tree_root.findLayer(layer.id())
                if layer_tree_layer and layer_tree_layer.isVisible():
                    visible_layers.append(layer)
        
        return visible_layers
    
    def _detect_features_in_layer(self, layer: QgsVectorLayer, click_pt: QgsPointXY) -> List[DetectedFeature]:
        """
        Detect features in a specific layer at the click point.
        CRS-agnostic detection that works regardless of layer CRS differences.
        
        Args:
            layer: Vector layer to search in
            click_pt: Click point coordinates (in canvas CRS)
            
        Returns:
            List of detected features in this layer
        """
        detected_features = []
        geometry_type = layer.geometryType()
        
        # Debug: Print layer information
        print(f"DEBUG: Checking layer '{layer.name()}' - Geometry type: {geometry_type}")
        print(f"DEBUG: Layer CRS: {layer.crs().authid()}, Canvas CRS: {self.canvas.mapSettings().destinationCrs().authid()}")
        
        # Determine search tolerance based on geometry type
        if geometry_type == QgsWkbTypes.PointGeometry:
            # Use extended search radius for points
            tolerance = self.point_search_radius
        elif geometry_type == QgsWkbTypes.LineGeometry:
            # Use extended search radius for lines too (they're hard to click on)
            tolerance = self.point_search_radius  # Same as points
        else:
            tolerance = self.default_tolerance
        
        # Convert tolerance to map units (use canvas CRS for consistency)
        tolerance_map_units = tolerance * self.canvas.mapUnitsPerPixel()
        
        print(f"DEBUG: Using tolerance: {tolerance} pixels ({tolerance_map_units} map units)")
        
        # Create search rectangle in canvas CRS
        search_rect = QgsRectangle(
            click_pt.x() - tolerance_map_units,
            click_pt.y() - tolerance_map_units,
            click_pt.x() + tolerance_map_units,
            click_pt.y() + tolerance_map_units
        )
        
        # Find features using CRS-agnostic method
        if layer.featureCount() > 1000:
            features = self._find_features_with_spatial_index_crs_agnostic(layer, click_pt, search_rect)
        else:
            features = self._find_features_simple_crs_agnostic(layer, click_pt, search_rect)
        
        print(f"DEBUG: Found {len(features)} features in layer '{layer.name()}'")
        
        # Convert to DetectedFeature objects
        for feature in features:
            # Use detailed geometry type that includes multipoint detection
            geometry_type_str = self._get_detailed_geometry_type(feature)
            distance = self._calculate_distance_to_feature_crs_agnostic(feature, click_pt, layer)
            
            print(f"DEBUG: Feature ID {feature.id()} - Type: {geometry_type_str}, Distance: {distance}")
            
            detected_feature = DetectedFeature(
                feature=feature,
                layer=layer,
                geometry_type=geometry_type_str,
                distance=distance
            )
            detected_features.append(detected_feature)
        
        return detected_features
    
    def _find_features_simple_crs_agnostic(self, layer: QgsVectorLayer, click_pt: QgsPointXY, search_rect: QgsRectangle) -> List['QgsFeature']:
        """
        CRS-agnostic feature search for smaller layers.
        Works regardless of layer CRS differences.
        
        Args:
            layer: Vector layer to search in
            click_pt: Click point coordinates (in canvas CRS)
            search_rect: Search rectangle (in canvas CRS)
            
        Returns:
            List of features at the click point
        """
        features = []
        
        # Transform click point and search rect to layer CRS if needed
        layer_crs = layer.crs()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        
        if layer_crs != canvas_crs:
            # Transform coordinates to layer CRS
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            try:
                click_pt_layer = transform.transform(click_pt)
                search_rect_layer = transform.transformBoundingBox(search_rect)
            except Exception as e:
                print(f"DEBUG: CRS transformation failed: {e}")
                return []
        else:
            click_pt_layer = click_pt
            search_rect_layer = search_rect
        
        # Create feature request in layer CRS
        req = QgsFeatureRequest().setFilterRect(search_rect_layer)
        pt_geom_layer = QgsGeometry.fromPointXY(click_pt_layer)
        
        for feature in layer.getFeatures(req):
            geometry = feature.geometry()
            if not geometry:
                continue
            
            try:
                if self._feature_contains_point_crs_agnostic(feature, click_pt_layer, pt_geom_layer, layer):
                    features.append(feature)
            except Exception as e:
                print(f"DEBUG: Feature detection error: {e}")
                continue
        
        return features
    
    def _find_features_simple(self, layer: QgsVectorLayer, click_pt: QgsPointXY, search_rect: QgsRectangle) -> List['QgsFeature']:
        """
        Simple feature search for smaller layers (legacy method).
        
        Args:
            layer: Vector layer to search in
            click_pt: Click point coordinates
            search_rect: Search rectangle
            
        Returns:
            List of features at the click point
        """
        return self._find_features_simple_crs_agnostic(layer, click_pt, search_rect)
    
    def _find_features_with_spatial_index_crs_agnostic(self, layer: QgsVectorLayer, click_pt: QgsPointXY, search_rect: QgsRectangle) -> List['QgsFeature']:
        """
        CRS-agnostic feature search using spatial index for better performance on large layers.
        Works regardless of layer CRS differences.
        
        Args:
            layer: Vector layer to search in
            click_pt: Click point coordinates (in canvas CRS)
            search_rect: Search rectangle (in canvas CRS)
            
        Returns:
            List of features at the click point
        """
        try:
            # Transform coordinates to layer CRS if needed
            layer_crs = layer.crs()
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            
            if layer_crs != canvas_crs:
                # Transform coordinates to layer CRS
                transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
                try:
                    click_pt_layer = transform.transform(click_pt)
                    search_rect_layer = transform.transformBoundingBox(search_rect)
                except Exception as e:
                    print(f"DEBUG: CRS transformation failed: {e}")
                    return []
            else:
                click_pt_layer = click_pt
                search_rect_layer = search_rect
            
            # Build spatial index
            spatial_index = QgsSpatialIndex(layer.getFeatures())
            
            # Query spatial index for candidate features
            candidate_fids = spatial_index.intersects(search_rect_layer)
            
            if not candidate_fids:
                return []
            
            # Get features by their IDs
            req = QgsFeatureRequest().setFilterFids(candidate_fids)
            pt_geom_layer = QgsGeometry.fromPointXY(click_pt_layer)
            features = []
            
            for feature in layer.getFeatures(req):
                geometry = feature.geometry()
                if not geometry:
                    continue
                
                try:
                    if self._feature_contains_point_crs_agnostic(feature, click_pt_layer, pt_geom_layer, layer):
                        features.append(feature)
                except Exception as e:
                    print(f"DEBUG: Feature detection error: {e}")
                    continue
            
            return features
            
        except Exception as e:
            print(f"DEBUG: Spatial index search failed: {e}")
            # Fallback to simple search if spatial index fails
            return self._find_features_simple_crs_agnostic(layer, click_pt, search_rect)
    
    def _find_features_with_spatial_index(self, layer: QgsVectorLayer, click_pt: QgsPointXY, search_rect: QgsRectangle) -> List['QgsFeature']:
        """
        Feature search using spatial index for better performance on large layers (legacy method).
        
        Args:
            layer: Vector layer to search in
            click_pt: Click point coordinates
            search_rect: Search rectangle
            
        Returns:
            List of features at the click point
        """
        return self._find_features_with_spatial_index_crs_agnostic(layer, click_pt, search_rect)
    
    def _feature_contains_point_crs_agnostic(self, feature: 'QgsFeature', click_pt: QgsPointXY, pt_geom: QgsGeometry, layer: QgsVectorLayer) -> bool:
        """
        CRS-agnostic check if a feature contains or intersects the clicked point.
        Works regardless of layer CRS differences.
        
        Args:
            feature: Feature to check
            click_pt: Click point coordinates (in layer CRS)
            pt_geom: Point geometry for the click point (in layer CRS)
            layer: Layer containing the feature
            
        Returns:
            True if feature contains the point
        """
        geometry = feature.geometry()
        geometry_type = geometry.type()
        
        # Calculate tolerance in layer CRS
        layer_crs = layer.crs()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        
        if layer_crs != canvas_crs:
            # Transform tolerance from canvas CRS to layer CRS
            try:
                # Create a small rectangle in canvas CRS and transform it to get scale factor
                canvas_tolerance = self.default_tolerance * self.canvas.mapUnitsPerPixel()
                test_rect = QgsRectangle(0, 0, canvas_tolerance, canvas_tolerance)
                transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
                transformed_rect = transform.transformBoundingBox(test_rect)
                tolerance_map_units = max(transformed_rect.width(), transformed_rect.height())
            except Exception:
                # Fallback: use a reasonable default tolerance
                tolerance_map_units = self.default_tolerance * 0.001  # Rough approximation
        else:
            tolerance_map_units = self.default_tolerance * self.canvas.mapUnitsPerPixel()
        
        if geometry_type == QgsWkbTypes.PointGeometry:
            # For points, check if click is within tolerance
            feature_point = geometry.asPoint()
            distance = click_pt.distance(feature_point)
            point_tolerance = self.point_search_radius * (tolerance_map_units / self.default_tolerance)
            return distance <= point_tolerance
        elif geometry_type == QgsWkbTypes.LineGeometry:
            # For lines, check if click is within tolerance distance
            distance = geometry.distance(pt_geom)
            line_tolerance = self.point_search_radius * (tolerance_map_units / self.default_tolerance)
            return distance <= line_tolerance
        else:
            # For polygons, use multiple detection methods for better reliability
            # This helps with transparent polygons where users click on the outline
            
            # Method 1: Check if point is inside polygon
            if geometry.contains(pt_geom):
                return True
            
            # Method 2: Check if point intersects polygon (for boundary cases)
            if geometry.intersects(pt_geom):
                return True
            
            # Method 3: Check if point is within tolerance of polygon boundary
            # This is crucial for transparent polygons where users click on outlines
            try:
                distance = geometry.distance(pt_geom)
                return distance <= tolerance_map_units
            except Exception:
                # Fallback: if distance calculation fails, use intersects as last resort
                return geometry.intersects(pt_geom)
    
    def _feature_contains_point(self, feature: 'QgsFeature', click_pt: QgsPointXY, pt_geom: QgsGeometry) -> bool:
        """
        Check if a feature contains or intersects the clicked point (legacy method).
        
        Args:
            feature: Feature to check
            click_pt: Click point coordinates
            pt_geom: Point geometry for the click point
            
        Returns:
            True if feature contains the point
        """
        # This is a simplified version for backward compatibility
        geometry = feature.geometry()
        geometry_type = geometry.type()
        
        if geometry_type == QgsWkbTypes.PointGeometry:
            # For points, check if click is within tolerance
            feature_point = geometry.asPoint()
            distance = click_pt.distance(feature_point)
            tolerance_map_units = self.point_search_radius * self.canvas.mapUnitsPerPixel()
            return distance <= tolerance_map_units
        elif geometry_type == QgsWkbTypes.LineGeometry:
            # For lines, check if click is within tolerance distance
            distance = geometry.distance(pt_geom)
            tolerance_map_units = self.point_search_radius * self.canvas.mapUnitsPerPixel()
            return distance <= tolerance_map_units
        else:
            # For polygons, use multiple detection methods for better reliability
            # This helps with transparent polygons where users click on the outline
            
            # Method 1: Check if point is inside polygon
            if geometry.contains(pt_geom):
                return True
            
            # Method 2: Check if point intersects polygon (for boundary cases)
            if geometry.intersects(pt_geom):
                return True
            
            # Method 3: Check if point is within tolerance of polygon boundary
            # This is crucial for transparent polygons where users click on outlines
            try:
                distance = geometry.distance(pt_geom)
                tolerance_map_units = self.default_tolerance * self.canvas.mapUnitsPerPixel()
                return distance <= tolerance_map_units
            except Exception:
                # Fallback: if distance calculation fails, use intersects as last resort
                return geometry.intersects(pt_geom)
    
    def _get_geometry_type_string(self, geometry_type: QgsWkbTypes.GeometryType) -> str:
        """
        Convert QGIS geometry type to string.
        
        Args:
            geometry_type: QGIS geometry type
            
        Returns:
            String representation of geometry type
        """
        if geometry_type == QgsWkbTypes.PointGeometry:
            return 'point'
        elif geometry_type == QgsWkbTypes.LineGeometry:
            return 'line'
        elif geometry_type == QgsWkbTypes.PolygonGeometry:
            return 'polygon'
        else:
            return 'unknown'
    
    def _get_detailed_geometry_type(self, feature: 'QgsFeature') -> str:
        """
        Get detailed geometry type including multipoint detection.
        
        Args:
            feature: Feature to analyze
            
        Returns:
            Detailed geometry type string
        """
        geometry = feature.geometry()
        if not geometry:
            return 'unknown'
        
        geometry_type = geometry.type()
        
        if geometry_type == QgsWkbTypes.PointGeometry:
            # Check if it's a multipoint
            if geometry.isMultipart():
                return 'multipoint'
            else:
                return 'point'
        elif geometry_type == QgsWkbTypes.LineGeometry:
            # Check if it's a multilinestring
            if geometry.isMultipart():
                return 'multiline'
            else:
                return 'line'
        elif geometry_type == QgsWkbTypes.PolygonGeometry:
            # Check if it's a multipolygon
            if geometry.isMultipart():
                return 'multipolygon'
            else:
                return 'polygon'
        else:
            return 'unknown'
    
    def _calculate_distance_to_feature_crs_agnostic(self, feature: 'QgsFeature', click_pt: QgsPointXY, layer: QgsVectorLayer) -> float:
        """
        CRS-agnostic calculation of distance from click point to feature.
        Works regardless of layer CRS differences.
        
        Args:
            feature: Feature to calculate distance to
            click_pt: Click point coordinates (in layer CRS)
            layer: Layer containing the feature
            
        Returns:
            Distance in map units
        """
        geometry = feature.geometry()
        if not geometry:
            return float('inf')
        
        try:
            if geometry.type() == QgsWkbTypes.PointGeometry:
                # For points, calculate direct distance
                feature_point = geometry.asPoint()
                return click_pt.distance(feature_point)
            else:
                # For lines and polygons, calculate distance to geometry
                pt_geom = QgsGeometry.fromPointXY(click_pt)
                return geometry.distance(pt_geom)
        except Exception as e:
            print(f"DEBUG: Distance calculation error: {e}")
            return float('inf')
    
    def _calculate_distance_to_feature(self, feature: 'QgsFeature', click_pt: QgsPointXY) -> float:
        """
        Calculate distance from click point to feature (legacy method).
        
        Args:
            feature: Feature to calculate distance to
            click_pt: Click point coordinates
            
        Returns:
            Distance in map units
        """
        geometry = feature.geometry()
        if not geometry:
            return float('inf')
        
        try:
            if geometry.type() == QgsWkbTypes.PointGeometry:
                # For points, calculate direct distance
                feature_point = geometry.asPoint()
                return click_pt.distance(feature_point)
            else:
                # For lines and polygons, calculate distance to geometry
                pt_geom = QgsGeometry.fromPointXY(click_pt)
                return geometry.distance(pt_geom)
        except Exception:
            return float('inf')
    
    def _sort_features_by_priority(self, features: List[DetectedFeature]) -> List[DetectedFeature]:
        """
        Sort features by priority: points first (closest), then lines, then polygons.
        
        Args:
            features: List of detected features
            
        Returns:
            Sorted list of features
        """
        def priority_key(feature: DetectedFeature) -> Tuple[int, float]:
            # Priority order: points (0), multipoints (0), lines (1), multilines (1), polygons (2), multipolygons (2)
            type_priority = {
                'point': 0, 'multipoint': 0,
                'line': 1, 'multiline': 1,
                'polygon': 2, 'multipolygon': 2
            }.get(feature.geometry_type, 3)
            return (type_priority, feature.distance)
        
        return sorted(features, key=priority_key)
    
    def get_click_context(self, event: QgsMapMouseEvent) -> Dict:
        """
        Get complete click context including detected features and click type.
        
        Args:
            event: Mouse event containing click coordinates
            
        Returns:
            Dictionary containing click context information
        """
        try:
            click_pt = event.mapPoint()
            detected_features = self.detect_features_at_point(event)
            
            # Determine click type
            if not detected_features:
                click_type = 'canvas'
            else:
                # Group features by type
                feature_types = set(f.geometry_type for f in detected_features)
                if len(feature_types) == 1:
                    click_type = list(feature_types)[0]
                else:
                    click_type = 'mixed'
            
            return {
                'click_point': click_pt,
                'click_type': click_type,
                'detected_features': detected_features,
                'has_features': len(detected_features) > 0,
                'feature_count': len(detected_features)
            }
        except Exception as e:
            # Return a safe fallback context in case of errors
            print(f"Error in get_click_context: {e}")
            return {
                'click_point': event.mapPoint() if event else None,
                'click_type': 'canvas',
                'detected_features': [],
                'has_features': False,
                'feature_count': 0,
                'error': str(e)
            }
