"""
Generate Points in Polygon Action for Right-click Utilities and Shortcuts Hub

Generates a specified number of points inside polygon features using various distribution algorithms.
Supports multiple generation methods including uniform random, Gaussian, quasi-random sequences, clustering, and edge-biased distributions.
"""

import random
import math
from .base_action import BaseAction
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsField, QgsFields, QgsProject, QgsVectorFileWriter
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QPushButton, QFormLayout, QGroupBox


class PointGenerationDialog(QDialog):
    """Interactive dialog for configuring point generation parameters."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Points in Polygon")
        self.setModal(True)
        self.resize(400, 300)
        
        # Initialize values
        self.point_count = 100
        self.generation_method = 'uniform_random'
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Main parameters group
        main_group = QGroupBox("Point Generation Parameters")
        main_layout = QFormLayout()
        
        # Number of points
        self.point_count_spinbox = QSpinBox()
        self.point_count_spinbox.setRange(1, 10000)
        self.point_count_spinbox.setValue(100)
        self.point_count_spinbox.setSuffix(" points")
        main_layout.addRow("Number of Points:", self.point_count_spinbox)
        
        # Generation method
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Uniform Random",
            "Gaussian Distribution", 
            "Halton/Sobol Sequences",
            "Clustering",
            "Centroid-based"
        ])
        self.method_combo.setCurrentText("Uniform Random")
        main_layout.addRow("Generation Method:", self.method_combo)
        
        main_group.setLayout(main_layout)
        layout.addWidget(main_group)
        
        # Method descriptions
        desc_group = QGroupBox("Method Description")
        desc_layout = QVBoxLayout()
        
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        desc_layout.addWidget(self.description_label)
        
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Generate Points")
        self.ok_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Connect signals
        self.method_combo.currentTextChanged.connect(self.update_description)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        # Set initial description
        self.update_description()
    
    def update_description(self):
        """Update the method description based on selection."""
        method = self.method_combo.currentText()
        descriptions = {
            "Uniform Random": "Points are chosen independently with equal probability everywhere inside the polygon.",
            "Gaussian Distribution": "Points are generated with Gaussian noise around a center point. Configure center and standard deviation in action settings.",
            "Halton/Sobol Sequences": "Low-discrepancy sequences that fill the space more evenly than pure random. Better for uniform coverage.",
            "Clustering": "First picks cluster centers randomly, then scatters additional points around them. Configure cluster count and radius in settings.",
            "Centroid-based": "Points distributed based on distance from polygon centroid. Configure distribution parameters in action settings."
        }
        self.description_label.setText(descriptions.get(method, ""))
    
    def get_values(self):
        """Get the selected values."""
        method_map = {
            "Uniform Random": "uniform_random",
            "Gaussian Distribution": "gaussian",
            "Halton/Sobol Sequences": "halton_sobol", 
            "Clustering": "clustering",
            "Centroid-based": "centroid_based"
        }
        
        return {
            'point_count': self.point_count_spinbox.value(),
            'generation_method': method_map[self.method_combo.currentText()]
        }


class GeneratePointsInPolygonAction(BaseAction):
    """
    Action to generate points inside polygon features using various distribution algorithms.
    
    This action creates a new point layer with generated points inside the selected polygon.
    Supports multiple generation methods for different use cases and research scenarios.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "generate_points_in_polygon"
        self.name = "Generate Points in Polygon"
        self.category = "Geometry"
        self.description = "Generate a specified number of points inside the selected polygon feature using various distribution algorithms. Creates a new point layer with the generated points. Supports uniform random, Gaussian, quasi-random, clustering, and edge-biased distributions."
        self.enabled = True
        
        # Action scoping - works on individual polygon features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # GAUSSIAN DISTRIBUTION SETTINGS
            'gaussian_center_x': {
                'type': 'float',
                'default': 0.5,
                'label': 'Gaussian Center X',
                'description': 'X coordinate of Gaussian distribution center (0.0-1.0, relative to polygon bounds)',
                'min': 0.0,
                'max': 1.0,
                'step': 0.01,
            },
            'gaussian_center_y': {
                'type': 'float',
                'default': 0.5,
                'label': 'Gaussian Center Y',
                'description': 'Y coordinate of Gaussian distribution center (0.0-1.0, relative to polygon bounds)',
                'min': 0.0,
                'max': 1.0,
                'step': 0.01,
            },
            'gaussian_std_dev': {
                'type': 'float',
                'default': 0.2,
                'label': 'Gaussian Standard Deviation',
                'description': 'Standard deviation for Gaussian distribution (0.01-1.0)',
                'min': 0.01,
                'max': 1.0,
                'step': 0.01,
            },
            
            # CLUSTERING SETTINGS
            'cluster_count': {
                'type': 'int',
                'default': 3,
                'label': 'Number of Clusters',
                'description': 'Number of cluster centers for clustering distribution',
                'min': 1,
                'max': 20,
                'step': 1,
            },
            'cluster_radius': {
                'type': 'float',
                'default': 0.1,
                'label': 'Cluster Radius',
                'description': 'Radius around cluster centers (0.01-0.5, relative to polygon size)',
                'min': 0.01,
                'max': 0.5,
                'step': 0.01,
            },
            
            # CENTROID-BASED SETTINGS
            'centroid_distribution_type': {
                'type': 'choice',
                'default': 'distance_weighted',
                'label': 'Centroid Distribution Type',
                'description': 'How points are distributed relative to the centroid',
                'options': ['distance_weighted', 'radial_rings', 'spiral_pattern'],
            },
            'centroid_bias_strength': {
                'type': 'float',
                'default': 0.5,
                'label': 'Centroid Bias Strength',
                'description': 'Strength of centroid bias (0.0 = uniform, 1.0 = maximum bias toward/away from centroid)',
                'min': 0.0,
                'max': 1.0,
                'step': 0.01,
            },
            'centroid_bias_direction': {
                'type': 'choice',
                'default': 'toward_centroid',
                'label': 'Centroid Bias Direction',
                'description': 'Whether to bias points toward or away from the centroid',
                'options': ['toward_centroid', 'away_from_centroid'],
            },
            
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
                'default': 'Generated Points',
                'label': 'Output Layer Name',
                'description': 'Name for the new point layer containing generated points',
            },
            'add_generation_info': {
                'type': 'bool',
                'default': True,
                'label': 'Add Generation Info',
                'description': 'Add attributes to generated points with generation method and parameters',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when points are generated successfully',
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
        Execute the generate points in polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Show interactive dialog for main parameters
        dialog = PointGenerationDialog()
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get values from dialog
        dialog_values = dialog.get_values()
        point_count = dialog_values['point_count']
        generation_method = dialog_values['generation_method']
        
        # Get other settings with proper type conversion
        try:
            gaussian_center_x = float(self.get_setting('gaussian_center_x', 0.5))
            gaussian_center_y = float(self.get_setting('gaussian_center_y', 0.5))
            gaussian_std_dev = float(self.get_setting('gaussian_std_dev', 0.2))
            cluster_count = int(self.get_setting('cluster_count', 3))
            cluster_radius = float(self.get_setting('cluster_radius', 0.1))
            centroid_distribution_type = str(self.get_setting('centroid_distribution_type', 'distance_weighted'))
            centroid_bias_strength = float(self.get_setting('centroid_bias_strength', 0.5))
            centroid_bias_direction = str(self.get_setting('centroid_bias_direction', 'toward_centroid'))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Generated Points'))
            add_generation_info = bool(self.get_setting('add_generation_info', True))
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
            
            # Get polygon bounds
            bounds = geometry.boundingBox()
            min_x, min_y = bounds.xMinimum(), bounds.yMinimum()
            max_x, max_y = bounds.xMaximum(), bounds.yMaximum()
            
            # Generate points based on selected method
            points = []
            
            if generation_method == 'uniform_random':
                points = self._generate_uniform_random_points(
                    geometry, point_count, min_x, min_y, max_x, max_y
                )
            elif generation_method == 'gaussian':
                points = self._generate_gaussian_points(
                    geometry, point_count, min_x, min_y, max_x, max_y,
                    gaussian_center_x, gaussian_center_y, gaussian_std_dev
                )
            elif generation_method == 'halton_sobol':
                points = self._generate_halton_sobol_points(
                    geometry, point_count, min_x, min_y, max_x, max_y
                )
            elif generation_method == 'clustering':
                points = self._generate_clustering_points(
                    geometry, point_count, min_x, min_y, max_x, max_y,
                    cluster_count, cluster_radius
                )
            elif generation_method == 'centroid_based':
                points = self._generate_centroid_based_points(
                    geometry, point_count, min_x, min_y, max_x, max_y,
                    centroid_distribution_type, centroid_bias_strength, centroid_bias_direction
                )
            else:
                self.show_error("Error", f"Unknown generation method: {generation_method}")
                return
            
            if not points:
                self.show_error("Error", "No points were generated")
                return
            
            # Create new point layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Points Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer = self._create_point_layer(
                    output_layer_name, points, add_generation_info,
                    generation_method, point_count, layer.crs()
                )
                
                if not temp_layer:
                    self.show_error("Error", "Failed to create temporary layer")
                    return
                
                # Save temporary layer to file
                from qgis.core import QgsVectorFileWriter
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
            else:
                # Create temporary in-memory layer
                output_layer = self._create_point_layer(
                    output_layer_name, points, add_generation_info,
                    generation_method, point_count, layer.crs()
                )
            

            if output_layer:
                # Add layer to project
                QgsProject.instance().addMapLayer(output_layer)

                # Prepare full layer definition and features for undo/redo
                fields_def = []
                for field in output_layer.fields():
                    fields_def.append({
                        'name': field.name(),
                        'qmeta_type': int(field.type())
                    })

                features_def = []
                for feat in output_layer.getFeatures():
                    backup = self.create_feature_backup(feat, output_layer)
                    features_def.append(backup)

                layer_def = {
                    'layer_name': output_layer.name(),
                    'crs': output_layer.crs().authid() if output_layer.crs().isValid() else '',
                    'geometry_type': output_layer.wkbType(),
                    'fields': fields_def,
                    'features': features_def,
                    'is_temporary': output_layer.dataProvider().name() == 'memory',
                }

                self.record_to_history(
                    description=f"Generated {len(points)} points in polygon using {generation_method} method.",
                    undo_type="generate_points_in_polygon",
                    can_undo=True,
                    layers=[self.create_layer_descriptor(output_layer)],
                    features=[],
                    undo_payload={
                        "output_layer_id": output_layer.id(),
                        "output_layer_name": output_layer.name(),
                        "storage_type": layer_storage_type,
                        "layer_definition": layer_def
                    }
                )

                if show_success_message:
                    method_display_names = {
                        'uniform_random': 'Uniform Random',
                        'gaussian': 'Gaussian Distribution',
                        'halton_sobol': 'Halton/Sobol Sequences',
                        'clustering': 'Clustering',
                        'centroid_based': 'Centroid-based'
                    }
                    method_display = method_display_names.get(generation_method, generation_method)
                    self.show_info(
                        "Success",
                        f"Generated {len(points)} points using {method_display} method.\n"
                        f"New layer '{output_layer_name}' added to project."
                    )
            else:
                self.show_error("Error", "Failed to create output layer")

        except Exception as e:
            self.show_error("Error", f"Failed to generate points: {str(e)}")
    
    def _generate_uniform_random_points(self, geometry, count, min_x, min_y, max_x, max_y):
        """Generate points using uniform random distribution."""
        points = []
        attempts = 0
        max_attempts = count * 10  # Prevent infinite loops
        
        while len(points) < count and attempts < max_attempts:
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            point = QgsPointXY(x, y)
            
            if geometry.contains(QgsGeometry.fromPointXY(point)):
                points.append(point)
            
            attempts += 1
        
        return points
    
    def _generate_gaussian_points(self, geometry, count, min_x, min_y, max_x, max_y, center_x, center_y, std_dev):
        """Generate points using Gaussian distribution."""
        points = []
        attempts = 0
        max_attempts = count * 10
        
        # Convert relative coordinates to absolute
        center_abs_x = min_x + center_x * (max_x - min_x)
        center_abs_y = min_y + center_y * (max_y - min_y)
        std_dev_abs = std_dev * min(max_x - min_x, max_y - min_y)
        
        while len(points) < count and attempts < max_attempts:
            x = random.gauss(center_abs_x, std_dev_abs)
            y = random.gauss(center_abs_y, std_dev_abs)
            point = QgsPointXY(x, y)
            
            if geometry.contains(QgsGeometry.fromPointXY(point)):
                points.append(point)
            
            attempts += 1
        
        return points
    
    def _generate_halton_sobol_points(self, geometry, count, min_x, min_y, max_x, max_y):
        """Generate points using Halton sequence (quasi-random)."""
        points = []
        attempts = 0
        max_attempts = count * 10
        
        # Simple Halton sequence implementation
        def halton(index, base):
            result = 0.0
            f = 1.0 / base
            i = index
            while i > 0:
                result += f * (i % base)
                i = i // base
                f = f / base
            return result
        
        while len(points) < count and attempts < max_attempts:
            # Use different bases for x and y to avoid correlation
            x_rel = halton(attempts + 1, 2)  # Base 2
            y_rel = halton(attempts + 1, 3)  # Base 3
            
            x = min_x + x_rel * (max_x - min_x)
            y = min_y + y_rel * (max_y - min_y)
            point = QgsPointXY(x, y)
            
            if geometry.contains(QgsGeometry.fromPointXY(point)):
                points.append(point)
            
            attempts += 1
        
        return points
    
    def _generate_clustering_points(self, geometry, count, min_x, min_y, max_x, max_y, cluster_count, cluster_radius):
        """Generate points using clustering distribution."""
        points = []
        
        # Generate cluster centers
        cluster_centers = []
        attempts = 0
        max_attempts = cluster_count * 10
        
        while len(cluster_centers) < cluster_count and attempts < max_attempts:
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            center = QgsPointXY(x, y)
            
            if geometry.contains(QgsGeometry.fromPointXY(center)):
                cluster_centers.append(center)
            
            attempts += 1
        
        if not cluster_centers:
            return []
        
        # Generate points around cluster centers
        points_per_cluster = count // len(cluster_centers)
        remaining_points = count % len(cluster_centers)
        
        cluster_radius_abs = cluster_radius * min(max_x - min_x, max_y - min_y)
        
        for i, center in enumerate(cluster_centers):
            cluster_points = points_per_cluster
            if i < remaining_points:
                cluster_points += 1
            
            for _ in range(cluster_points):
                # Generate point in circle around cluster center
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(0, cluster_radius_abs)
                
                x = center.x() + distance * math.cos(angle)
                y = center.y() + distance * math.sin(angle)
                point = QgsPointXY(x, y)
                
                if geometry.contains(QgsGeometry.fromPointXY(point)):
                    points.append(point)
        
        return points
    
    def _generate_centroid_based_points(self, geometry, count, min_x, min_y, max_x, max_y, distribution_type, bias_strength, bias_direction):
        """Generate points with bias based on distance from polygon centroid."""
        points = []
        attempts = 0
        max_attempts = count * 20
        
        # Get polygon centroid
        centroid = geometry.centroid()
        if centroid.isEmpty():
            # Fallback to uniform random if centroid calculation fails
            return self._generate_uniform_random_points(geometry, count, min_x, min_y, max_x, max_y)
        
        centroid_point = centroid.asPoint()
        
        if distribution_type == 'distance_weighted':
            # Distance-weighted distribution
            while len(points) < count and attempts < max_attempts:
                x = random.uniform(min_x, max_x)
                y = random.uniform(min_y, max_y)
                point = QgsPointXY(x, y)
                
                if geometry.contains(QgsGeometry.fromPointXY(point)):
                    # Calculate distance from centroid
                    distance_from_centroid = math.sqrt(
                        (point.x() - centroid_point.x())**2 + 
                        (point.y() - centroid_point.y())**2
                    )
                    
                    # Calculate maximum possible distance (from centroid to corner of bounding box)
                    max_distance = math.sqrt(
                        (max_x - min_x)**2 + (max_y - min_y)**2
                    ) / 2
                    
                    if max_distance > 0:
                        # Normalize distance (0 = at centroid, 1 = at maximum distance)
                        normalized_distance = distance_from_centroid / max_distance
                        
                        # Calculate weight based on bias direction and strength
                        if bias_direction == 'toward_centroid':
                            # Higher weight for points closer to centroid
                            weight = (1.0 - normalized_distance) ** (1.0 + bias_strength * 2.0)
                        else:  # away_from_centroid
                            # Higher weight for points farther from centroid
                            weight = normalized_distance ** (1.0 + bias_strength * 2.0)
                        
                        # Accept point based on weight
                        if random.random() < weight:
                            points.append(point)
                    else:
                        # Fallback: accept all points
                        points.append(point)
                
                attempts += 1
        
        elif distribution_type == 'radial_rings':
            # Radial ring distribution
            # Calculate number of rings based on point count
            num_rings = max(3, int(math.sqrt(count / 10)))
            points_per_ring = count // num_rings
            remaining_points = count % num_rings
            
            for ring in range(num_rings):
                ring_points = points_per_ring
                if ring < remaining_points:
                    ring_points += 1
                
                # Calculate ring radius (from centroid to edge)
                ring_radius = (ring + 1) / num_rings
                
                for _ in range(ring_points):
                    # Generate random angle
                    angle = random.uniform(0, 2 * math.pi)
                    
                    # Calculate distance from centroid based on bias
                    if bias_direction == 'toward_centroid':
                        # Points closer to centroid
                        distance_factor = (1.0 - bias_strength) + bias_strength * (1.0 - ring_radius)
                    else:  # away_from_centroid
                        # Points farther from centroid
                        distance_factor = bias_strength + (1.0 - bias_strength) * ring_radius
                    
                    # Calculate actual distance
                    max_radius = min(
                        centroid_point.x() - min_x,
                        max_x - centroid_point.x(),
                        centroid_point.y() - min_y,
                        max_y - centroid_point.y()
                    )
                    distance = distance_factor * max_radius
                    
                    # Calculate point coordinates
                    x = centroid_point.x() + distance * math.cos(angle)
                    y = centroid_point.y() + distance * math.sin(angle)
                    point = QgsPointXY(x, y)
                    
                    # Check if point is inside polygon
                    if geometry.contains(QgsGeometry.fromPointXY(point)):
                        points.append(point)
        
        elif distribution_type == 'spiral_pattern':
            # Spiral pattern distribution
            # Calculate spiral parameters
            max_radius = min(
                centroid_point.x() - min_x,
                max_x - centroid_point.x(),
                centroid_point.y() - min_y,
                max_y - centroid_point.y()
            )
            
            for i in range(count):
                # Calculate spiral parameters
                t = i / count
                
                # Spiral radius based on bias
                if bias_direction == 'toward_centroid':
                    radius = max_radius * (1.0 - bias_strength * t)
                else:  # away_from_centroid
                    radius = max_radius * (bias_strength + (1.0 - bias_strength) * t)
                
                # Spiral angle
                angle = t * 4 * math.pi  # Multiple turns
                
                # Calculate point coordinates
                x = centroid_point.x() + radius * math.cos(angle)
                y = centroid_point.y() + radius * math.sin(angle)
                point = QgsPointXY(x, y)
                
                # Check if point is inside polygon
                if geometry.contains(QgsGeometry.fromPointXY(point)):
                    points.append(point)
        
        return points
    
    
    def _create_point_layer(self, layer_name, points, add_generation_info, generation_method, point_count, crs):
        """Create a new point layer with the generated points."""
        try:
            # Create memory layer
            layer = QgsVectorLayer("Point", layer_name, "memory")
            layer.setCrs(crs)
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField("id", QVariant.Int))
            
            if add_generation_info:
                fields.append(QgsField("method", QVariant.String))
                fields.append(QgsField("total_points", QVariant.Int))
                fields.append(QgsField("generated_at", QVariant.String))
            
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            
            # Add features
            layer.startEditing()
            
            for i, point in enumerate(points):
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                
                attributes = [i + 1]  # ID
                
                if add_generation_info:
                    from datetime import datetime
                    attributes.extend([
                        generation_method,
                        point_count,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ])
                
                feature.setAttributes(attributes)
                layer.addFeature(feature)
            
            layer.commitChanges()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create point layer: {str(e)}")
            return None


# REQUIRED: Create global instance for automatic discovery
generate_points_in_polygon_action = GeneratePointsInPolygonAction()
