"""
Generate Points on Line Action for Right-click Utilities and Shortcuts Hub

Creates points along a line feature with user-configurable placement options.
Supports random placement, equal distance spacing, and custom distance spacing.
User chooses point count and placement method interactively for each execution.
"""

import random
import math
from .base_action import BaseAction
from qgis.core import QgsPoint, QgsGeometry, QgsFeature, QgsField, QgsFields, QgsVectorLayer, QgsWkbTypes, QgsCoordinateTransform, QgsProject, QgsVectorFileWriter
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QDoubleSpinBox, QCheckBox, QPushButton, QGroupBox, QFormLayout, QLineEdit


class GeneratePointsDialog(QDialog):
    """Dialog for user to choose point generation options."""
    
    def __init__(self, parent=None, default_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Points on Line")
        self.setModal(True)
        self.resize(400, 300)
        
        # Default settings
        self.default_settings = default_settings or {}
        
        self.setup_ui()
        self.load_defaults()
    
    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout()
        
        # Point Generation Group
        point_group = QGroupBox("Point Generation")
        point_layout = QFormLayout()
        
        # Number of points
        self.point_count_label = QLabel("Number of Points:")
        self.point_count_spin = QSpinBox()
        self.point_count_spin.setRange(1, 1000)
        self.point_count_spin.setValue(5)
        point_layout.addRow(self.point_count_label, self.point_count_spin)
        
        # Placement method
        self.placement_combo = QComboBox()
        self.placement_combo.addItems(["Random", "Equal Distance", "Custom Distance"])
        self.placement_combo.currentTextChanged.connect(self.on_placement_changed)
        point_layout.addRow("Placement Method:", self.placement_combo)
        
        # Custom distance
        self.custom_distance_spin = QDoubleSpinBox()
        self.custom_distance_spin.setRange(0.1, 10000.0)
        self.custom_distance_spin.setDecimals(2)
        self.custom_distance_spin.setValue(100.0)
        self.custom_distance_spin.setSuffix(" map units")
        point_layout.addRow("Distance Between Points:", self.custom_distance_spin)
        
        # Start offset for custom distance
        self.start_offset_spin = QDoubleSpinBox()
        self.start_offset_spin.setRange(0.0, 10000.0)
        self.start_offset_spin.setDecimals(2)
        self.start_offset_spin.setValue(0.0)
        self.start_offset_spin.setSuffix(" map units")
        point_layout.addRow("Start Offset:", self.start_offset_spin)
        
        # Include start/end points
        self.include_start_check = QCheckBox("Include start point")
        self.include_start_check.setChecked(True)
        point_layout.addRow(self.include_start_check)
        
        self.include_end_check = QCheckBox("Include end point")
        self.include_end_check.setChecked(True)
        point_layout.addRow(self.include_end_check)
        
        point_group.setLayout(point_layout)
        layout.addWidget(point_group)
        
        # Output Group
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()
        
        # Layer name
        self.layer_name_edit = QLineEdit()
        self.layer_name_edit.setText("Generated Points")
        output_layout.addRow("Layer Name:", self.layer_name_edit)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Generate Points")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Initially hide custom distance
        self.on_placement_changed()
    
    def load_defaults(self):
        """Load default settings."""
        if not self.default_settings:
            return
        
        self.point_count_spin.setValue(int(self.default_settings.get('default_point_count', 5)))
        
        method_map = {
            'random': 'Random',
            'equal_distance': 'Equal Distance',
            'custom_distance': 'Custom Distance'
        }
        default_method = self.default_settings.get('default_placement_method', 'equal_distance')
        method_text = method_map.get(default_method, 'Equal Distance')
        self.placement_combo.setCurrentText(method_text)
        
        self.custom_distance_spin.setValue(float(self.default_settings.get('default_custom_distance', 100.0)))
        self.start_offset_spin.setValue(float(self.default_settings.get('default_start_offset', 0.0)))
        self.include_start_check.setChecked(bool(self.default_settings.get('default_include_start_point', True)))
        self.include_end_check.setChecked(bool(self.default_settings.get('default_include_end_point', True)))
    
    def on_placement_changed(self):
        """Handle placement method change."""
        method = self.placement_combo.currentText()
        is_custom_distance = method == "Custom Distance"
        
        # Show/hide relevant controls
        self.custom_distance_spin.setVisible(is_custom_distance)
        self.start_offset_spin.setVisible(is_custom_distance)
        
        # Hide point count for custom distance (number of points is determined by distance)
        self.point_count_label.setVisible(not is_custom_distance)
        self.point_count_spin.setVisible(not is_custom_distance)
    
    def get_settings(self):
        """Get the current dialog settings."""
        method_map = {
            'Random': 'random',
            'Equal Distance': 'equal_distance',
            'Custom Distance': 'custom_distance'
        }
        
        return {
            'point_count': self.point_count_spin.value(),
            'placement_method': method_map[self.placement_combo.currentText()],
            'custom_distance': self.custom_distance_spin.value(),
            'start_offset': self.start_offset_spin.value(),
            'include_start_point': self.include_start_check.isChecked(),
            'include_end_point': self.include_end_check.isChecked(),
            'layer_name': self.layer_name_edit.text().strip() or "Generated Points"
        }


class GeneratePointsOnLineAction(BaseAction):
    """
    Action to generate points along a line feature.
    
    This action creates points on the selected line feature with three placement options:
    1. Random placement - points placed randomly along the line
    2. Equal distance - points spaced equally along the line
    3. Custom distance - points placed at specified distance intervals
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "generate_points_on_line"
        self.name = "Generate Points on Line"
        self.category = "Geometry"
        self.description = "Generate points along the selected line feature. Choose from random placement, equal distance spacing, or custom distance intervals. Creates a new point layer with the generated points."
        self.enabled = True
        
        # Action scoping configuration
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # ADVANCED POINT GENERATION SETTINGS
            'default_point_count': {
                'type': 'int',
                'default': 5,
                'label': 'Default Point Count',
                'description': 'Default number of points to suggest in the dialog',
                'min': 1,
                'max': 1000,
                'step': 1,
            },
            'default_placement_method': {
                'type': 'choice',
                'default': 'equal_distance',
                'label': 'Default Placement Method',
                'description': 'Default placement method to suggest in the dialog',
                'options': ['random', 'equal_distance', 'custom_distance'],
            },
            'default_custom_distance': {
                'type': 'float',
                'default': 100.0,
                'label': 'Default Custom Distance',
                'description': 'Default distance value to suggest for custom distance method (in map units)',
                'min': 0.1,
                'max': 10000.0,
                'step': 0.1,
            },
            'default_start_offset': {
                'type': 'float',
                'default': 0.0,
                'label': 'Default Start Offset',
                'description': 'Default start offset for custom distance method (in map units)',
                'min': 0.0,
                'max': 10000.0,
                'step': 0.1,
            },
            'default_include_start_point': {
                'type': 'bool',
                'default': True,
                'label': 'Default Include Start Point',
                'description': 'Default setting for including the starting point of the line',
            },
            'default_include_end_point': {
                'type': 'bool',
                'default': True,
                'label': 'Default Include End Point',
                'description': 'Default setting for including the ending point of the line',
            },
            
            # OUTPUT SETTINGS
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'output_layer_name_template': {
                'type': 'str',
                'default': 'Points on Line {timestamp}',
                'label': 'Output Layer Name Template',
                'description': 'Template for naming the new point layer. Use {timestamp} for current date/time, {line_id} for line feature ID',
            },
            'add_distance_attribute': {
                'type': 'bool',
                'default': True,
                'label': 'Add Distance Attribute',
                'description': 'Add an attribute showing the distance along the line for each point',
            },
            'add_point_index_attribute': {
                'type': 'bool',
                'default': True,
                'label': 'Add Point Index Attribute',
                'description': 'Add an attribute showing the sequential index of each point',
            },
            'add_line_id_attribute': {
                'type': 'bool',
                'default': True,
                'label': 'Add Line ID Attribute',
                'description': 'Add an attribute showing the ID of the source line feature',
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_result': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Result',
                'description': 'Automatically zoom to show the generated points after creation',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message showing how many points were created',
            },
            'remember_last_settings': {
                'type': 'bool',
                'default': True,
                'label': 'Remember Last Settings',
                'description': 'Remember the last used settings for the next execution',
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
        Execute the generate points on line action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get advanced settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            add_distance_attribute = bool(self.get_setting('add_distance_attribute', True))
            add_point_index_attribute = bool(self.get_setting('add_point_index_attribute', True))
            add_line_id_attribute = bool(self.get_setting('add_line_id_attribute', True))
            zoom_to_result = bool(self.get_setting('zoom_to_result', True))
            show_success_message = bool(self.get_setting('show_success_message', True))
            remember_last_settings = bool(self.get_setting('remember_last_settings', True))
            
            # Get default settings for dialog
            default_settings = {
                'default_point_count': int(self.get_setting('default_point_count', 5)),
                'default_placement_method': str(self.get_setting('default_placement_method', 'equal_distance')),
                'default_custom_distance': float(self.get_setting('default_custom_distance', 100.0)),
                'default_start_offset': float(self.get_setting('default_start_offset', 0.0)),
                'default_include_start_point': bool(self.get_setting('default_include_start_point', True)),
                'default_include_end_point': bool(self.get_setting('default_include_end_point', True)),
            }
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Show dialog for user input
        dialog = GeneratePointsDialog(parent=canvas, default_settings=default_settings)
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get user choices from dialog
        user_settings = dialog.get_settings()
        point_count = user_settings['point_count']
        placement_method = user_settings['placement_method']
        custom_distance = user_settings['custom_distance']
        start_offset = user_settings['start_offset']
        include_start_point = user_settings['include_start_point']
        include_end_point = user_settings['include_end_point']
        output_layer_name = user_settings['layer_name']
        
        # Remember settings if enabled
        if remember_last_settings:
            self._save_last_settings(user_settings)
        
        try:
            # Get feature geometry
            geometry = feature.geometry()
            if not geometry:
                self.show_error("Error", "Feature has no geometry")
                return
            
            # Handle CRS transformation if needed
            canvas_crs = canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            
            if canvas_crs != layer_crs:
                transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                try:
                    geometry.transform(transform)
                except Exception as e:
                    self.show_error("Error", f"CRS transformation failed: {str(e)}")
                    return
            
            # Generate points based on placement method
            points = self._generate_points_on_line(
                geometry, point_count, placement_method, custom_distance, start_offset,
                include_start_point, include_end_point
            )
            
            if not points:
                self.show_error("Error", "No points could be generated on this line")
                return
            
            # Create output layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Points Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer = self._create_output_layer(
                    output_layer_name, layer_crs, add_distance_attribute, add_point_index_attribute, add_line_id_attribute
                )
                
                if not temp_layer:
                    self.show_error("Error", "Failed to create temporary layer")
                    return
                
                # Add points to temporary layer
                self._add_points_to_layer(
                    temp_layer, points, feature.id(), add_distance_attribute, add_point_index_attribute, add_line_id_attribute
                )
                
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
                output_layer = self._create_output_layer(
                    output_layer_name, layer_crs, add_distance_attribute, add_point_index_attribute, add_line_id_attribute
                )
                
                if not output_layer:
                    self.show_error("Error", "Failed to create output layer")
                    return
                
                # Add points to the layer
                self._add_points_to_layer(
                    output_layer, points, feature.id(), add_distance_attribute, add_point_index_attribute, add_line_id_attribute
                )
            
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
                description=f"Generated {len(points)} points on line feature ID {feature.id()}.",
                undo_type="generate_points_on_line",
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

            # Zoom to result if requested
            if zoom_to_result:
                self._zoom_to_layer(canvas, output_layer, layer_crs)

            # Show success message
            if show_success_message:
                self.show_info("Success", 
                    f"Generated {len(points)} points on line feature ID {feature.id()}\n"
                    f"Output layer: {output_layer_name}")

        except Exception as e:
            self.show_error("Error", f"Failed to generate points: {str(e)}")
    
    def _save_last_settings(self, user_settings):
        """Save the last used settings for next execution."""
        try:
            from qgis.PyQt.QtCore import QSettings
            settings = QSettings()
            
            # Map user settings to default settings keys
            settings.setValue(f"RightClickUtilities/{self.action_id}/default_point_count", user_settings['point_count'])
            settings.setValue(f"RightClickUtilities/{self.action_id}/default_placement_method", user_settings['placement_method'])
            settings.setValue(f"RightClickUtilities/{self.action_id}/default_custom_distance", user_settings['custom_distance'])
            settings.setValue(f"RightClickUtilities/{self.action_id}/default_start_offset", user_settings['start_offset'])
            settings.setValue(f"RightClickUtilities/{self.action_id}/default_include_start_point", user_settings['include_start_point'])
            settings.setValue(f"RightClickUtilities/{self.action_id}/default_include_end_point", user_settings['include_end_point'])
        except Exception:
            pass  # Fail silently
    
    def _generate_points_on_line(self, geometry, point_count, placement_method, custom_distance, start_offset,
                                include_start_point, include_end_point):
        """
        Generate points along a line geometry.
        
        Args:
            geometry: QgsGeometry of the line
            point_count: Number of points to generate
            placement_method: Method for placing points
            custom_distance: Distance for custom distance method
            include_start_point: Whether to include start point
            include_end_point: Whether to include end point
            
        Returns:
            list: List of (QgsPoint, distance_along_line) tuples
        """
        points = []
        
        # Get line length
        line_length = geometry.length()
        if line_length <= 0:
            return points
        
        # Get start and end points
        start_point = geometry.interpolate(0).asPoint()
        end_point = geometry.interpolate(line_length).asPoint()
        
        # Add start and end points if requested
        if include_start_point:
            points.append((start_point, 0.0))
        if include_end_point and not (include_start_point and start_point == end_point):
            points.append((end_point, line_length))
        
        # Generate intermediate points based on method
        if placement_method == 'random':
            points.extend(self._generate_random_points(geometry, point_count, line_length))
        elif placement_method == 'equal_distance':
            points.extend(self._generate_equal_distance_points(geometry, point_count, line_length))
        elif placement_method == 'custom_distance':
            points.extend(self._generate_custom_distance_points(geometry, custom_distance, start_offset, line_length))
        
        # Sort points by distance along line
        points.sort(key=lambda x: x[1])
        
        return points
    
    def _generate_random_points(self, geometry, point_count, line_length):
        """Generate randomly placed points along the line."""
        points = []
        for _ in range(point_count):
            distance = random.uniform(0, line_length)
            point = geometry.interpolate(distance).asPoint()
            points.append((point, distance))
        return points
    
    def _generate_equal_distance_points(self, geometry, point_count, line_length):
        """Generate equally spaced points along the line."""
        points = []
        if point_count <= 0:
            return points
        
        # Calculate spacing
        if point_count == 1:
            distances = [line_length / 2]
        else:
            spacing = line_length / (point_count + 1)
            distances = [spacing * (i + 1) for i in range(point_count)]
        
        for distance in distances:
            point = geometry.interpolate(distance).asPoint()
            points.append((point, distance))
        
        return points
    
    def _generate_custom_distance_points(self, geometry, custom_distance, start_offset, line_length):
        """Generate points at custom distance intervals along the line."""
        points = []
        if custom_distance <= 0:
            return points
        
        # Start from the start offset
        current_distance = start_offset
        
        # Generate points at fixed intervals
        while current_distance <= line_length:
            point = geometry.interpolate(current_distance).asPoint()
            points.append((point, current_distance))
            current_distance += custom_distance
        
        return points
    
    def _create_output_layer(self, layer_name, crs, add_distance_attribute, add_point_index_attribute, add_line_id_attribute):
        """Create the output point layer."""
        try:
            # Create fields
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int))
            
            if add_distance_attribute:
                fields.append(QgsField('distance', QVariant.Double))
            
            if add_point_index_attribute:
                fields.append(QgsField('point_index', QVariant.Int))
            
            if add_line_id_attribute:
                fields.append(QgsField('line_id', QVariant.Int))
            
            # Create layer
            layer = QgsVectorLayer(f"Point?crs={crs.authid()}", layer_name, "memory")
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create output layer: {str(e)}")
            return None
    
    def _add_points_to_layer(self, layer, points, line_id, add_distance_attribute, add_point_index_attribute, add_line_id_attribute):
        """Add points to the output layer."""
        try:
            layer.startEditing()
            
            for i, (point, distance) in enumerate(points):
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                
                # Set attributes
                attributes = [i + 1]  # id
                
                if add_distance_attribute:
                    attributes.append(distance)
                
                if add_point_index_attribute:
                    attributes.append(i + 1)
                
                if add_line_id_attribute:
                    attributes.append(line_id)
                
                feature.setAttributes(attributes)
                layer.addFeature(feature)
            
            layer.commitChanges()
            
        except Exception as e:
            layer.rollBack()
            self.show_error("Error", f"Failed to add points to layer: {str(e)}")
    
    def _zoom_to_layer(self, canvas, layer, layer_crs):
        """Zoom to the output layer extent."""
        try:
            # Get layer extent
            layer_extent = layer.extent()
            
            # Transform to canvas CRS if needed
            canvas_crs = canvas.mapSettings().destinationCrs()
            if canvas_crs != layer_crs:
                transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                try:
                    layer_extent = transform.transformBoundingBox(layer_extent)
                except Exception:
                    pass  # Use original extent if transformation fails
            
            # Add buffer and zoom
            buffer_percentage = 10.0
            buffer = layer_extent.width() * buffer_percentage / 100.0
            layer_extent.grow(buffer)
            
            canvas.setExtent(layer_extent)
            canvas.refresh()
            
        except Exception:
            pass  # Fail silently for zoom operations


# REQUIRED: Create global instance for automatic discovery
generate_points_on_line = GeneratePointsOnLineAction()
