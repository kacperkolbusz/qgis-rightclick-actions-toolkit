"""
Generate Random Lines in Polygon Action for Right-click Utilities and Shortcuts Hub

Generates a specified number of random lines inside polygon features using various distribution algorithms.
Supports random and Gaussian distribution methods with configurable line length ranges.
"""

import random
import math
from .base_action import BaseAction
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsField, QgsFields, QgsProject, QgsWkbTypes, QgsVectorFileWriter
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QPushButton, QFormLayout, QGroupBox, QDoubleSpinBox, QCheckBox


class LineGenerationDialog(QDialog):
    """Interactive dialog for configuring line generation parameters."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Random Lines in Polygon")
        self.setModal(True)
        self.resize(450, 350)
        
        # Initialize values
        self.line_count = 10
        self.min_length = 10.0
        self.max_length = 50.0
        self.distribution_method = 'random'
        self.prevent_crossings = False
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Main parameters group
        main_group = QGroupBox("Line Generation Parameters")
        main_layout = QFormLayout()
        
        # Number of lines
        self.line_count_spinbox = QSpinBox()
        self.line_count_spinbox.setRange(1, 99999)
        self.line_count_spinbox.setValue(10)
        self.line_count_spinbox.setSuffix(" lines")
        main_layout.addRow("Number of Lines:", self.line_count_spinbox)
        
        # Line length range
        length_layout = QHBoxLayout()
        self.min_length_spinbox = QDoubleSpinBox()
        self.min_length_spinbox.setRange(0.1, 10000.0)
        self.min_length_spinbox.setValue(10.0)
        self.min_length_spinbox.setSuffix(" units")
        self.min_length_spinbox.setDecimals(1)
        
        self.max_length_spinbox = QDoubleSpinBox()
        self.max_length_spinbox.setRange(0.1, 10000.0)
        self.max_length_spinbox.setValue(50.0)
        self.max_length_spinbox.setSuffix(" units")
        self.max_length_spinbox.setDecimals(1)
        
        length_layout.addWidget(QLabel("Min Length:"))
        length_layout.addWidget(self.min_length_spinbox)
        length_layout.addWidget(QLabel("Max Length:"))
        length_layout.addWidget(self.max_length_spinbox)
        main_layout.addRow("Line Length Range:", length_layout)
        
        # Distribution method
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Random",
            "Gaussian Distribution"
        ])
        self.method_combo.setCurrentText("Random")
        main_layout.addRow("Distribution Method:", self.method_combo)
        
        # Prevent crossings option
        self.prevent_crossings_checkbox = QCheckBox("Prevent line crossings")
        self.prevent_crossings_checkbox.setChecked(False)
        self.prevent_crossings_checkbox.setToolTip("When enabled, generated lines will not intersect with each other")
        main_layout.addRow("Line Behavior:", self.prevent_crossings_checkbox)
        
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
        self.ok_button = QPushButton("Generate Lines")
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
            "Random": "Lines are placed randomly inside the polygon with random orientations and lengths within the specified range.",
            "Gaussian Distribution": "Lines are generated with Gaussian distribution around a center point. Configure center and standard deviation in action settings."
        }
        self.description_label.setText(descriptions.get(method, ""))
    
    def get_values(self):
        """Get the selected values."""
        method_map = {
            "Random": "random",
            "Gaussian Distribution": "gaussian"
        }
        
        return {
            'line_count': self.line_count_spinbox.value(),
            'min_length': self.min_length_spinbox.value(),
            'max_length': self.max_length_spinbox.value(),
            'distribution_method': method_map[self.method_combo.currentText()],
            'prevent_crossings': self.prevent_crossings_checkbox.isChecked()
        }


class GenerateRandomLinesInPolygonAction(BaseAction):
    """
    Action to generate random lines inside polygon features using various distribution algorithms.
    
    This action creates a new line layer with generated lines inside the selected polygon.
    Supports random and Gaussian distribution methods with configurable line parameters.
    """
    def __init__(self):
        super().__init__()

        # Required properties
        self.action_id = "generate_random_lines_in_polygon"
        self.name = "Generate Random Lines in Polygon"
        self.category = "Geometry"
        self.description = "Generate a specified number of random lines inside the selected polygon feature using various distribution algorithms. Creates a new line layer with the generated lines. Supports random and Gaussian distribution methods with configurable line length ranges."
        self.enabled = True

        # Action scoping - works on individual polygon features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def supports_undo(self) -> bool:
        """This action supports undo: creating a new layer with generated lines."""
        return True

    def get_undo_category(self) -> str:
        """Trivial undo: undo = delete created layer/features"""
        return 'trivial'
    
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
            
            # LINE GENERATION SETTINGS
            'max_attempts_multiplier': {
                'type': 'int',
                'default': 20,
                'label': 'Max Attempts Multiplier',
                'description': 'Maximum attempts per line (multiplied by line count) to prevent infinite loops',
                'min': 5,
                'max': 100,
                'step': 1,
            },
            'ensure_lines_inside': {
                'type': 'bool',
                'default': True,
                'label': 'Ensure Lines Inside Polygon',
                'description': 'Only generate lines that are completely inside the polygon',
            },
            'allow_partial_lines': {
                'type': 'bool',
                'default': False,
                'label': 'Allow Partial Lines',
                'description': 'Allow lines that extend outside the polygon (clipped at polygon boundary)',
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
                'default': 'Generated Lines',
                'label': 'Output Layer Name',
                'description': 'Name for the new line layer containing generated lines',
            },
            'add_generation_info': {
                'type': 'bool',
                'default': True,
                'label': 'Add Generation Info',
                'description': 'Add attributes to generated lines with generation method and parameters',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when lines are generated successfully',
            },
            'default_prevent_crossings': {
                'type': 'bool',
                'default': False,
                'label': 'Default Prevent Crossings',
                'description': 'Default value for preventing line crossings in the dialog',
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
        Execute the generate random lines in polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get default setting for prevent crossings
        try:
            default_prevent_crossings = bool(self.get_setting('default_prevent_crossings', False))
        except (ValueError, TypeError):
            default_prevent_crossings = False
        
        # Show interactive dialog for main parameters
        dialog = LineGenerationDialog()
        dialog.prevent_crossings_checkbox.setChecked(default_prevent_crossings)
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get values from dialog
        dialog_values = dialog.get_values()
        line_count = dialog_values['line_count']
        min_length = dialog_values['min_length']
        max_length = dialog_values['max_length']
        distribution_method = dialog_values['distribution_method']
        prevent_crossings = dialog_values['prevent_crossings']
        
        # Validate length range
        if min_length >= max_length:
            self.show_error("Error", "Minimum length must be less than maximum length")
            return
        
        # Get other settings with proper type conversion
        try:
            gaussian_center_x = float(self.get_setting('gaussian_center_x', 0.5))
            gaussian_center_y = float(self.get_setting('gaussian_center_y', 0.5))
            gaussian_std_dev = float(self.get_setting('gaussian_std_dev', 0.2))
            max_attempts_multiplier = int(self.get_setting('max_attempts_multiplier', 20))
            ensure_lines_inside = bool(self.get_setting('ensure_lines_inside', True))
            allow_partial_lines = bool(self.get_setting('allow_partial_lines', False))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Generated Lines'))
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
            
            # Generate lines based on selected method
            lines = []
            
            if distribution_method == 'random':
                lines = self._generate_random_lines(
                    geometry, line_count, min_length, max_length, min_x, min_y, max_x, max_y,
                    max_attempts_multiplier, ensure_lines_inside, allow_partial_lines, prevent_crossings
                )
            elif distribution_method == 'gaussian':
                lines = self._generate_gaussian_lines(
                    geometry, line_count, min_length, max_length, min_x, min_y, max_x, max_y,
                    gaussian_center_x, gaussian_center_y, gaussian_std_dev,
                    max_attempts_multiplier, ensure_lines_inside, allow_partial_lines, prevent_crossings
                )
            else:
                self.show_error("Error", f"Unknown distribution method: {distribution_method}")
                return
            
            if not lines:
                self.show_error("Error", "No lines were generated")
                return
            
            # Create new line layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Lines Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer, created_backups = self._create_line_layer(
                    output_layer_name, lines, add_generation_info,
                    distribution_method, line_count, min_length, max_length, layer.crs()
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

                # Recreate backups from saved layer features (permanent layers get new FIDs)
                try:
                    created_backups = []
                    for f in output_layer.getFeatures():
                        try:
                            created_backups.append(self.create_feature_backup(f, output_layer))
                        except Exception:
                            pass
                except Exception:
                    created_backups = []
            else:
                # Create temporary in-memory layer
                output_layer, created_backups = self._create_line_layer(
                    output_layer_name, lines, add_generation_info,
                    distribution_method, line_count, min_length, max_length, layer.crs()
                )
            
            if output_layer:
                # Add layer to project
                QgsProject.instance().addMapLayer(output_layer)
                
                if show_success_message:
                    method_display_names = {
                        'random': 'Random',
                        'gaussian': 'Gaussian Distribution'
                    }
                    method_display = method_display_names.get(distribution_method, distribution_method)
                    crossing_info = " (no crossings)" if prevent_crossings else ""
                    self.show_info(
                        "Success",
                        f"Generated {len(lines)} lines using {method_display} method{crossing_info}.\n"
                        f"New layer '{output_layer_name}' added to project."
                    )
                # Record history for created layer and features
                try:
                    backups = created_backups if 'created_backups' in locals() and created_backups else []
                    if not backups:
                        for f in output_layer.getFeatures():
                            try:
                                backups.append(self.create_feature_backup(f, output_layer))
                            except Exception:
                                pass

                    if backups:
                        self.record_to_history(
                            description=f"Generated {len(backups)} lines in layer '{output_layer_name}'",
                            undo_type='create_feature',
                            can_undo=True,
                            layers=[self.create_layer_descriptor(output_layer)],
                            features=backups,
                            meta={'layer_was_created': True}
                        )
                except Exception:
                    pass
            else:
                self.show_error("Error", "Failed to create output layer")
                
        except Exception as e:
            self.show_error("Error", f"Failed to generate lines: {str(e)}")
    
    def _generate_random_lines(self, geometry, count, min_length, max_length, min_x, min_y, max_x, max_y, max_attempts_multiplier, ensure_lines_inside, allow_partial_lines, prevent_crossings):
        """Generate lines using random distribution."""
        lines = []
        attempts = 0
        max_attempts = count * max_attempts_multiplier
        
        while len(lines) < count and attempts < max_attempts:
            # Generate random start point
            start_x = random.uniform(min_x, max_x)
            start_y = random.uniform(min_y, max_y)
            start_point = QgsPointXY(start_x, start_y)
            
            # Check if start point is inside polygon
            if not geometry.contains(QgsGeometry.fromPointXY(start_point)):
                attempts += 1
                continue
            
            # Generate random length and direction
            length = random.uniform(min_length, max_length)
            angle = random.uniform(0, 2 * math.pi)
            
            # Calculate end point
            end_x = start_x + length * math.cos(angle)
            end_y = start_y + length * math.sin(angle)
            end_point = QgsPointXY(end_x, end_y)
            
            # Create line geometry
            line_geometry = QgsGeometry.fromPolylineXY([start_point, end_point])
            
            # Check if line meets polygon requirements
            valid_line = None
            if ensure_lines_inside:
                # Check if entire line is inside polygon
                if geometry.contains(line_geometry):
                    valid_line = line_geometry
            elif allow_partial_lines:
                # Allow lines that extend outside, but clip them
                intersection = geometry.intersection(line_geometry)
                if not intersection.isEmpty() and intersection.type() == QgsWkbTypes.LineGeometry:
                    valid_line = intersection
            else:
                # Only accept lines that are completely inside
                if geometry.contains(line_geometry):
                    valid_line = line_geometry
            
            # If we have a valid line, check for crossings if required
            if valid_line and not valid_line.isEmpty():
                if prevent_crossings:
                    # Check if this line intersects with any existing lines
                    if not self._line_intersects_existing(valid_line, lines):
                        lines.append(valid_line)
                else:
                    # No crossing prevention, add the line
                    lines.append(valid_line)
            
            attempts += 1
        
        return lines
    
    def _generate_gaussian_lines(self, geometry, count, min_length, max_length, min_x, min_y, max_x, max_y, center_x, center_y, std_dev, max_attempts_multiplier, ensure_lines_inside, allow_partial_lines, prevent_crossings):
        """Generate lines using Gaussian distribution."""
        lines = []
        attempts = 0
        max_attempts = count * max_attempts_multiplier
        
        # Convert relative coordinates to absolute
        center_abs_x = min_x + center_x * (max_x - min_x)
        center_abs_y = min_y + center_y * (max_y - min_y)
        std_dev_abs = std_dev * min(max_x - min_x, max_y - min_y)
        
        while len(lines) < count and attempts < max_attempts:
            # Generate start point using Gaussian distribution
            start_x = random.gauss(center_abs_x, std_dev_abs)
            start_y = random.gauss(center_abs_y, std_dev_abs)
            start_point = QgsPointXY(start_x, start_y)
            
            # Check if start point is inside polygon
            if not geometry.contains(QgsGeometry.fromPointXY(start_point)):
                attempts += 1
                continue
            
            # Generate random length and direction
            length = random.uniform(min_length, max_length)
            angle = random.uniform(0, 2 * math.pi)
            
            # Calculate end point
            end_x = start_x + length * math.cos(angle)
            end_y = start_y + length * math.sin(angle)
            end_point = QgsPointXY(end_x, end_y)
            
            # Create line geometry
            line_geometry = QgsGeometry.fromPolylineXY([start_point, end_point])
            
            # Check if line meets polygon requirements
            valid_line = None
            if ensure_lines_inside:
                # Check if entire line is inside polygon
                if geometry.contains(line_geometry):
                    valid_line = line_geometry
            elif allow_partial_lines:
                # Allow lines that extend outside, but clip them
                intersection = geometry.intersection(line_geometry)
                if not intersection.isEmpty() and intersection.type() == QgsWkbTypes.LineGeometry:
                    valid_line = intersection
            else:
                # Only accept lines that are completely inside
                if geometry.contains(line_geometry):
                    valid_line = line_geometry
            
            # If we have a valid line, check for crossings if required
            if valid_line and not valid_line.isEmpty():
                if prevent_crossings:
                    # Check if this line intersects with any existing lines
                    if not self._line_intersects_existing(valid_line, lines):
                        lines.append(valid_line)
                else:
                    # No crossing prevention, add the line
                    lines.append(valid_line)
            
            attempts += 1
        
        return lines
    
    def _line_intersects_existing(self, new_line, existing_lines):
        """
        Check if a new line intersects with any existing lines.
        
        Args:
            new_line (QgsGeometry): The new line to check
            existing_lines (list): List of existing line geometries
            
        Returns:
            bool: True if the new line intersects with any existing line, False otherwise
        """
        for existing_line in existing_lines:
            if new_line.intersects(existing_line):
                # Check if the intersection is more than just touching at endpoints
                intersection = new_line.intersection(existing_line)
                if not intersection.isEmpty():
                    # If intersection is a point, check if it's not just an endpoint
                    if intersection.type() == QgsWkbTypes.PointGeometry:
                        # Get the intersection point
                        intersection_point = intersection.asPoint()
                        
                        # Get start and end points of both lines
                        new_points = new_line.asPolyline()
                        existing_points = existing_line.asPolyline()
                        
                        # Check if intersection point is not an endpoint of either line
                        new_start = new_points[0]
                        new_end = new_points[-1]
                        existing_start = existing_points[0]
                        existing_end = existing_points[-1]
                        
                        # Calculate tolerance for endpoint comparison
                        tolerance = 1e-10
                        
                        # Check if intersection point is not an endpoint
                        is_new_start = abs(intersection_point.x() - new_start.x()) < tolerance and abs(intersection_point.y() - new_start.y()) < tolerance
                        is_new_end = abs(intersection_point.x() - new_end.x()) < tolerance and abs(intersection_point.y() - new_end.y()) < tolerance
                        is_existing_start = abs(intersection_point.x() - existing_start.x()) < tolerance and abs(intersection_point.y() - existing_start.y()) < tolerance
                        is_existing_end = abs(intersection_point.x() - existing_end.x()) < tolerance and abs(intersection_point.y() - existing_end.y()) < tolerance
                        
                        # If intersection is not at endpoints, it's a real crossing
                        if not (is_new_start or is_new_end or is_existing_start or is_existing_end):
                            return True
                    else:
                        # If intersection is a line, it's definitely a crossing
                        return True
        
        return False
    
    def _create_line_layer(self, layer_name, lines, add_generation_info, distribution_method, line_count, min_length, max_length, crs):
        """Create a new line layer with the generated lines."""
        try:
            # Create memory layer
            layer = QgsVectorLayer("LineString", layer_name, "memory")
            layer.setCrs(crs)
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField("id", QVariant.Int))
            
            if add_generation_info:
                fields.append(QgsField("method", QVariant.String))
                fields.append(QgsField("total_lines", QVariant.Int))
                fields.append(QgsField("min_length", QVariant.Double))
                fields.append(QgsField("max_length", QVariant.Double))
                fields.append(QgsField("length", QVariant.Double))
                fields.append(QgsField("generated_at", QVariant.String))
            
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            
            # Add features using data provider and capture backups
            provider = layer.dataProvider()
            features_to_add = []

            for i, line_geometry in enumerate(lines):
                feature = QgsFeature()
                feature.setGeometry(line_geometry)

                attributes = [i + 1]  # ID

                if add_generation_info:
                    from datetime import datetime
                    line_length = line_geometry.length()
                    attributes.extend([
                        distribution_method,
                        line_count,
                        min_length,
                        max_length,
                        line_length,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ])

                feature.setAttributes(attributes)
                features_to_add.append(feature)

            created_backups = []
            try:
                success, added = provider.addFeatures(features_to_add)
                layer.updateExtents()

                if success and added:
                    # added is a list of features with assigned IDs
                    for f in added:
                        try:
                            created_backups.append(self.create_feature_backup(f, layer))
                        except Exception:
                            pass
                else:
                    # Fallback: create backups by iterating current layer features
                    for f in layer.getFeatures():
                        try:
                            created_backups.append(self.create_feature_backup(f, layer))
                        except Exception:
                            pass

            except Exception as e:
                # On error, try to collect whatever was added
                for f in layer.getFeatures():
                    try:
                        created_backups.append(self.create_feature_backup(f, layer))
                    except Exception:
                        pass

            return layer, created_backups
            
        except Exception as e:
            self.show_error("Error", f"Failed to create line layer: {str(e)}")
            return None, []


# REQUIRED: Create global instance for automatic discovery
generate_random_lines_in_polygon_action = GenerateRandomLinesInPolygonAction()
