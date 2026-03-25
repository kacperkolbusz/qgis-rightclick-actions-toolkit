"""
Analyze Point Distribution Pattern Action for Right-click Utilities and Shortcuts Hub

Analyzes the spatial distribution pattern of points in a point layer using spatial statistics.
Detects clustering, randomness, or regular/uniform distribution patterns.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsWkbTypes, QgsPointXY, QgsGeometry,
    QgsProject, QgsCoordinateTransform, QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant
import math


class AnalyzePointDistributionPatternAction(BaseAction):
    """Action to analyze point distribution patterns using spatial statistics."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "analyze_point_distribution_pattern"
        self.name = "Analyze Point Distribution Pattern"
        self.category = "Analysis"
        self.description = "Analyze the spatial distribution pattern of points in a point layer using spatial statistics. Detects clustering (points grouped together), random distribution, or regular/uniform patterns (evenly spaced points). Provides statistical measures and pattern interpretation."
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
            # ANALYSIS SETTINGS
            'analysis_method': {
                'type': 'choice',
                'default': 'nearest_neighbor',
                'label': 'Analysis Method',
                'description': 'Method to use for pattern analysis. Nearest Neighbor Analysis is most common and reliable.',
                'options': ['nearest_neighbor', 'standard_distance', 'both'],
            },
            'significance_level': {
                'type': 'float',
                'default': 0.05,
                'label': 'Significance Level',
                'description': 'Statistical significance level for pattern detection (0.01 = 1%, 0.05 = 5%, 0.10 = 10%)',
                'min': 0.01,
                'max': 0.10,
                'step': 0.01,
            },
            'include_detailed_stats': {
                'type': 'bool',
                'default': True,
                'label': 'Include Detailed Statistics',
                'description': 'Show detailed statistical measures in the results',
            },
            'include_interpretation': {
                'type': 'bool',
                'default': True,
                'label': 'Include Pattern Interpretation',
                'description': 'Provide interpretation of detected patterns with explanations',
            },
            
            # BEHAVIOR SETTINGS
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Analysis Results',
                'description': 'Display analysis results in information dialog',
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

    def supports_undo(self) -> bool:
        """Informational action — no undo support required."""
        return False

    def get_undo_category(self) -> str:
        """Return undo category for documentation/audit purposes."""
        return 'informational'
    
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
    
    def _get_nearest_neighbor_distance(self, points, point_index):
        """
        Get distance to nearest neighbor for a specific point.
        
        Args:
            points (list): List of QgsPointXY points
            point_index (int): Index of point to analyze
            
        Returns:
            float: Distance to nearest neighbor
        """
        if len(points) < 2:
            return 0.0
        
        point = points[point_index]
        min_distance = float('inf')
        
        for i, other_point in enumerate(points):
            if i != point_index:
                distance = self._calculate_distance(point, other_point)
                if distance < min_distance:
                    min_distance = distance
        
        return min_distance if min_distance != float('inf') else 0.0
    
    def _nearest_neighbor_analysis(self, points, area, significance_level=0.05):
        """
        Perform Nearest Neighbor Analysis.
        
        Args:
            points (list): List of QgsPointXY points
            area (float): Area of the study region
            significance_level (float): Statistical significance level (default 0.05)
            
        Returns:
            dict: Analysis results with R statistic, z-score, p-value, and pattern
        """
        n = len(points)
        if n < 2:
            return {
                'r_statistic': 0.0,
                'z_score': 0.0,
                'p_value': 1.0,
                'pattern': 'Insufficient points',
                'observed_mean': 0.0,
                'expected_mean': 0.0,
                'interpretation': 'Need at least 2 points for analysis'
            }
        
        # Calculate observed mean nearest neighbor distance
        observed_distances = []
        for i in range(n):
            nn_dist = self._get_nearest_neighbor_distance(points, i)
            if nn_dist > 0:
                observed_distances.append(nn_dist)
        
        if not observed_distances:
            return {
                'r_statistic': 0.0,
                'z_score': 0.0,
                'p_value': 1.0,
                'pattern': 'Unable to calculate',
                'observed_mean': 0.0,
                'expected_mean': 0.0,
                'interpretation': 'Could not calculate nearest neighbor distances'
            }
        
        observed_mean = sum(observed_distances) / len(observed_distances)
        
        # Calculate expected mean for random distribution
        # Expected = 0.5 / sqrt(density) = 0.5 * sqrt(area / n)
        density = n / area if area > 0 else 0
        expected_mean = 0.5 / math.sqrt(density) if density > 0 else 0.0
        
        # Calculate R statistic (Nearest Neighbor Ratio)
        # R = observed_mean / expected_mean
        # R < 1: Clustered
        # R = 1: Random
        # R > 1: Regular/Uniform
        r_statistic = observed_mean / expected_mean if expected_mean > 0 else 0.0
        
        # Calculate z-score for significance testing
        # Standard error = 0.26136 / sqrt(n^2 / area)
        se = 0.26136 / math.sqrt((n * n) / area) if area > 0 and n > 0 else 0.0
        z_score = (observed_mean - expected_mean) / se if se > 0 else 0.0
        
        # Determine pattern based on R statistic and z-score
        # Calculate z-score threshold based on significance level
        # For two-tailed test: 0.01 = 2.58, 0.05 = 1.96, 0.10 = 1.65
        if significance_level <= 0.01:
            significance_z = 2.58
        elif significance_level <= 0.05:
            significance_z = 1.96
        else:  # 0.10
            significance_z = 1.65
        
        if r_statistic < 0.8 and z_score < -significance_z:
            pattern = 'Clustered'
            interpretation = 'Points are significantly clustered together. The observed nearest neighbor distances are smaller than expected for a random distribution.'
        elif r_statistic > 1.2 and z_score > significance_z:
            pattern = 'Regular/Uniform'
            interpretation = 'Points show a regular or uniform distribution. The observed nearest neighbor distances are larger than expected for a random distribution, indicating even spacing.'
        elif abs(z_score) <= significance_z:
            pattern = 'Random'
            interpretation = 'Points show a random distribution. The observed pattern is not significantly different from what would be expected by chance.'
        else:
            # Borderline cases
            if r_statistic < 1.0:
                pattern = 'Slightly Clustered'
                interpretation = 'Points show a tendency toward clustering, but the pattern is not statistically significant at the chosen significance level.'
            else:
                pattern = 'Slightly Regular'
                interpretation = 'Points show a tendency toward regular spacing, but the pattern is not statistically significant at the chosen significance level.'
        
        # Calculate p-value (two-tailed test)
        # Using normal distribution approximation
        # Simplified calculation without scipy dependency
        try:
            # Approximate p-value using error function
            # For z > 0: p = 2 * (1 - Φ(z)) where Φ is CDF of standard normal
            # Using approximation: Φ(z) ≈ 0.5 * (1 + erf(z/√2))
            z_abs = abs(z_score)
            if z_abs > 6:
                p_value = 0.0
            else:
                # Approximation using error function
                erf_approx = math.erf(z_abs / math.sqrt(2))
                cdf_approx = 0.5 * (1 + erf_approx)
                p_value = 2 * (1 - cdf_approx)
        except:
            # Fallback calculation
            if abs(z_score) > 2.58:  # 99% confidence
                p_value = 0.01
            elif abs(z_score) > 1.96:  # 95% confidence
                p_value = 0.05
            elif abs(z_score) > 1.65:  # 90% confidence
                p_value = 0.10
            else:
                p_value = 1.0
        
        return {
            'r_statistic': r_statistic,
            'z_score': z_score,
            'p_value': p_value,
            'pattern': pattern,
            'observed_mean': observed_mean,
            'expected_mean': expected_mean,
            'interpretation': interpretation,
            'n': n,
            'area': area,
            'density': density
        }
    
    def _standard_distance_analysis(self, points):
        """
        Perform Standard Distance analysis (measures dispersion).
        
        Args:
            points (list): List of QgsPointXY points
            
        Returns:
            dict: Analysis results with standard distance and ellipse parameters
        """
        n = len(points)
        if n < 2:
            return {
                'standard_distance': 0.0,
                'mean_center_x': 0.0,
                'mean_center_y': 0.0,
                'interpretation': 'Need at least 2 points for analysis'
            }
        
        # Calculate mean center
        mean_x = sum(p.x() for p in points) / n
        mean_y = sum(p.y() for p in points) / n
        mean_center = QgsPointXY(mean_x, mean_y)
        
        # Calculate standard distance (root mean square distance from mean center)
        squared_distances = []
        for point in points:
            dist = self._calculate_distance(point, mean_center)
            squared_distances.append(dist * dist)
        
        standard_distance = math.sqrt(sum(squared_distances) / n) if squared_distances else 0.0
        
        # Interpretation
        if standard_distance == 0:
            interpretation = 'All points are at the same location (perfect clustering).'
        else:
            # Compare to expected for random distribution
            # For random distribution, standard distance relates to area
            interpretation = f'Standard distance: {standard_distance:.2f} map units. Lower values indicate clustering, higher values indicate dispersion.'
        
        return {
            'standard_distance': standard_distance,
            'mean_center_x': mean_x,
            'mean_center_y': mean_y,
            'interpretation': interpretation,
            'n': n
        }
    
    def _calculate_study_area(self, points):
        """
        Calculate study area from point extent with buffer.
        
        Args:
            points (list): List of QgsPointXY points
            
        Returns:
            float: Study area
        """
        if not points:
            return 0.0
        
        # Get extent
        x_coords = [p.x() for p in points]
        y_coords = [p.y() for p in points]
        
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        
        # Add 10% buffer to avoid edge effects
        width = max_x - min_x
        height = max_y - min_y
        buffer_x = width * 0.1
        buffer_y = height * 0.1
        
        area = (width + 2 * buffer_x) * (height + 2 * buffer_y)
        
        return area
    
    def execute(self, context):
        """Execute the analyze point distribution pattern action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            analysis_method = str(self.get_setting('analysis_method', schema['analysis_method']['default']))
            significance_level = float(self.get_setting('significance_level', schema['significance_level']['default']))
            include_detailed_stats = bool(self.get_setting('include_detailed_stats', schema['include_detailed_stats']['default']))
            include_interpretation = bool(self.get_setting('include_interpretation', schema['include_interpretation']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
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
            self.show_error("Error", "Layer must contain at least 2 points for pattern analysis")
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
            
            # Calculate study area
            study_area = self._calculate_study_area(points)
            
            if study_area <= 0:
                self.show_error("Error", "Could not calculate valid study area")
                return
            
            # Perform analysis based on selected method
            results = []
            
            if analysis_method in ['nearest_neighbor', 'both']:
                nna_results = self._nearest_neighbor_analysis(points, study_area, significance_level)
                results.append(('Nearest Neighbor Analysis', nna_results))
            
            if analysis_method in ['standard_distance', 'both']:
                sd_results = self._standard_distance_analysis(points)
                results.append(('Standard Distance Analysis', sd_results))
            
            # Build result message
            result_lines = []
            result_lines.append(f"Point Distribution Pattern Analysis")
            result_lines.append(f"Layer: {layer.name()}")
            result_lines.append(f"Number of points: {len(points)}")
            result_lines.append("")
            
            for method_name, method_results in results:
                result_lines.append(f"=== {method_name} ===")
                
                if method_name == 'Nearest Neighbor Analysis':
                    result_lines.append(f"Pattern: {method_results['pattern']}")
                    result_lines.append("")
                    
                    if include_interpretation:
                        result_lines.append(f"Interpretation: {method_results['interpretation']}")
                        result_lines.append("")
                    
                    if include_detailed_stats:
                        result_lines.append(f"R Statistic: {method_results['r_statistic']:.4f}")
                        result_lines.append(f"  (R < 1.0 = Clustered, R = 1.0 = Random, R > 1.0 = Regular)")
                        result_lines.append(f"Z-Score: {method_results['z_score']:.4f}")
                        result_lines.append(f"P-Value: {method_results['p_value']:.4f}")
                        result_lines.append(f"Observed Mean NN Distance: {method_results['observed_mean']:.4f} map units")
                        result_lines.append(f"Expected Mean NN Distance: {method_results['expected_mean']:.4f} map units")
                        result_lines.append(f"Point Density: {method_results['density']:.6f} points per unit area")
                        result_lines.append("")
                
                elif method_name == 'Standard Distance Analysis':
                    if include_interpretation:
                        result_lines.append(f"{method_results['interpretation']}")
                        result_lines.append("")
                    
                    if include_detailed_stats:
                        result_lines.append(f"Standard Distance: {method_results['standard_distance']:.4f} map units")
                        result_lines.append(f"Mean Center: ({method_results['mean_center_x']:.4f}, {method_results['mean_center_y']:.4f})")
                        result_lines.append("")
            
            # Add summary
            result_lines.append("=== Summary ===")
            if analysis_method in ['nearest_neighbor', 'both']:
                nna = results[0][1] if results else None
                if nna:
                    result_lines.append(f"Primary Pattern: {nna['pattern']}")
                    if nna['pattern'] == 'Clustered':
                        result_lines.append("→ Points are grouped together in clusters")
                    elif nna['pattern'] == 'Regular/Uniform':
                        result_lines.append("→ Points are evenly spaced across the area")
                    elif nna['pattern'] == 'Random':
                        result_lines.append("→ Points show no significant spatial pattern")
                    else:
                        result_lines.append(f"→ {nna['interpretation']}")
            
            result_text = "\n".join(result_lines)
            
            # Show results if requested
            if show_success_message:
                self.show_info("Point Distribution Pattern Analysis", result_text)

            # Record as informational in the History Manager (no undo)
            try:
                primary_pattern = None
                if analysis_method in ['nearest_neighbor', 'both'] and results:
                    primary_pattern = results[0][1].get('pattern')
                elif analysis_method == 'standard_distance' and results:
                    primary_pattern = results[-1][1].get('interpretation')

                self.record_informational(
                    description=f"Analyzed point distribution for layer '{layer.name()}': {primary_pattern or 'N/A'}",
                    meta={
                        'layer_id': layer.id(),
                        'layer_name': layer.name(),
                        'num_points': len(points),
                        'analysis_method': analysis_method,
                        'primary_pattern': primary_pattern,
                    }
                )
            except Exception:
                pass
        
        except Exception as e:
            self.show_error("Error", f"Failed to analyze point distribution pattern: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
analyze_point_distribution_pattern = AnalyzePointDistributionPatternAction()

