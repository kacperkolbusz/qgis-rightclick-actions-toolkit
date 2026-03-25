"""
Create Voronoi Diagram from Points Action for Right-click Utilities and Shortcuts Hub

Creates a Voronoi diagram from all points in the selected point layer.
The boundary can be determined in two ways:
1. Polygon boundary: Automatically finds polygons that contain all points and lets user
   choose which one to use as the boundary. If no suitable polygon is found, falls back
   to buffer method (if in auto mode).
2. Buffer method: Creates a convex hull around all points and adds a user-specified
   buffer to define the boundary.

Individual Voronoi polygons are created within the selected boundary.
"""

from .base_action import BaseAction
from qgis.core import QgsVectorLayer, QgsProject, QgsGeometry, QgsFeature, QgsField, QgsFields, QgsApplication, QgsCoordinateTransform, QgsVectorFileWriter
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QInputDialog


class CreateVoronoiDiagramFromPointsAction(BaseAction):
    """
    Action to create a Voronoi diagram from all points in a point layer.
    
    This action takes all points from the selected point layer and creates a Voronoi
    diagram. The user specifies a buffer distance to define the main boundary, and
    individual Voronoi polygons are created within this boundary. A new polygon layer
    is created to store the result.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_voronoi_diagram_from_points"
        self.name = "Create Voronoi Diagram from Points"
        self.category = "Geometry"
        self.description = "Create a Voronoi diagram from all points in the selected point layer. Can use either a buffered convex hull boundary or a polygon boundary from an existing layer that contains all points. Creates individual Voronoi polygons within the selected boundary."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with point features
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    # Undo support: this action creates a new layer, so enable undo
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        # Creating a new layer requires payload-style undo (store layer definition)
        return 'payload'
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # LAYER SETTINGS - Control the output layer creation
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'output_layer_name': {
                'type': 'str',
                'default': 'Voronoi Diagram from {source_layer}',
                'label': 'Output Layer Name Template',
                'description': 'Template for the output polygon layer name. Use {source_layer} for the source layer name, {timestamp} for current date/time.',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the generated polygon layer to the current QGIS project',
            },
            'zoom_to_result': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Result',
                'description': 'Zoom the map to show the generated Voronoi diagram',
            },
            
            # BOUNDARY METHOD SETTINGS - Control how boundary is determined
            'boundary_method': {
                'type': 'choice',
                'default': 'auto',
                'label': 'Boundary Method',
                'description': 'Method to determine Voronoi diagram boundary. "Auto" asks user to choose between polygon boundary or buffer method when polygons are found. "Polygon" uses polygon boundary only (fails if none found). "Buffer" uses buffered convex hull only.',
                'options': ['auto', 'polygon', 'buffer'],
            },
            
            # BUFFER SETTINGS - Control buffer behavior (used when boundary_method is "buffer" or "auto" fallback)
            'default_buffer_distance': {
                'type': 'float',
                'default': 100.0,
                'label': 'Default Buffer Distance',
                'description': 'Default buffer distance in map units to add around the convex hull boundary',
                'min': 0.1,
                'max': 10000.0,
                'step': 1.0,
            },
            'buffer_unit_label': {
                'type': 'str',
                'default': 'map units',
                'label': 'Buffer Unit Label',
                'description': 'Label for buffer distance units (e.g., "meters", "feet", "map units")',
            },
            'ask_for_buffer_distance': {
                'type': 'bool',
                'default': True,
                'label': 'Ask for Buffer Distance',
                'description': 'Always ask user for buffer distance to add around the convex hull boundary',
            },
            
            # ATTRIBUTE SETTINGS - Control what attributes to include
            'include_source_info': {
                'type': 'bool',
                'default': True,
                'label': 'Include Source Information',
                'description': 'Add attributes with information about the source point layer',
            },
            'include_point_id': {
                'type': 'bool',
                'default': True,
                'label': 'Include Point ID',
                'description': 'Add attribute showing the ID of the nearest point for each Voronoi polygon',
            },
            'include_polygon_area': {
                'type': 'bool',
                'default': True,
                'label': 'Include Polygon Area',
                'description': 'Add attribute showing the area of each Voronoi polygon',
            },
            'include_creation_timestamp': {
                'type': 'bool',
                'default': True,
                'label': 'Include Creation Timestamp',
                'description': 'Add attribute showing when the Voronoi diagram was created',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'confirm_creation': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Creation',
                'description': 'Show confirmation dialog before creating the Voronoi diagram',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when Voronoi diagram is created successfully',
            },
            'show_detailed_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Detailed Information',
                'description': 'Display detailed information about the created Voronoi diagram',
            },
            'minimum_points_required': {
                'type': 'int',
                'default': 3,
                'label': 'Minimum Points Required',
                'description': 'Minimum number of points required to create a valid Voronoi diagram',
                'min': 3,
                'max': 1000,
                'step': 1,
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
        Execute the create Voronoi diagram from points action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Voronoi Diagram from {source_layer}'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_result = bool(self.get_setting('zoom_to_result', True))
            boundary_method = str(self.get_setting('boundary_method', 'auto'))
            default_buffer_distance = float(self.get_setting('default_buffer_distance', 100.0))
            buffer_unit_label = str(self.get_setting('buffer_unit_label', 'map units'))
            ask_for_buffer_distance = bool(self.get_setting('ask_for_buffer_distance', True))
            include_source_info = bool(self.get_setting('include_source_info', True))
            include_point_id = bool(self.get_setting('include_point_id', True))
            include_polygon_area = bool(self.get_setting('include_polygon_area', True))
            include_creation_timestamp = bool(self.get_setting('include_creation_timestamp', True))
            confirm_creation = bool(self.get_setting('confirm_creation', False))
            show_success_message = bool(self.get_setting('show_success_message', True))
            show_detailed_info = bool(self.get_setting('show_detailed_info', True))
            minimum_points_required = int(self.get_setting('minimum_points_required', 3))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No point features found at this location")
            return
        
        # Get the clicked feature to determine the point layer
        detected_feature = detected_features[0]
        point_layer = detected_feature.layer
        
        # Check if the layer is a vector layer
        if not isinstance(point_layer, QgsVectorLayer):
            self.show_error("Error", "Selected layer is not a vector layer")
            return
        
        # Check if the layer has point geometry
        if point_layer.geometryType() not in [0, 4]:  # 0 = Point, 4 = MultiPoint
            self.show_error("Error", "Selected layer is not a point layer")
            return
        
        try:
            # Get all points from the point layer
            point_features = list(point_layer.getFeatures())
            if not point_features:
                self.show_warning("No Points", f"No point features found in layer '{point_layer.name()}'")
                return
            
            # Check minimum points requirement
            if len(point_features) < minimum_points_required:
                self.show_error("Insufficient Points", 
                    f"At least {minimum_points_required} points are required to create a Voronoi diagram. "
                    f"Found only {len(point_features)} points in layer '{point_layer.name()}'.")
                return
            
            # Determine boundary method and get boundary geometry
            boundary_geometry = None
            boundary_description = ""
            use_polygon_boundary = False
            
            if boundary_method in ['auto', 'polygon']:
                # Try to find polygons containing all points
                containing_polygons = self._find_polygons_containing_all_points(point_features, point_layer)
                
                if containing_polygons:
                    # In 'auto' mode, ask user which method they want to use
                    should_use_polygon = True
                    if boundary_method == 'auto':
                        user_choice = self._ask_boundary_method_choice(len(containing_polygons))
                        if user_choice is None:
                            return  # User cancelled
                        if user_choice == 'buffer':
                            # User chose buffer method, skip polygon selection
                            should_use_polygon = False
                        # If user chose 'polygon', should_use_polygon stays True
                    
                    # If using polygon method (either forced or chosen by user)
                    if should_use_polygon:
                        # User needs to choose which polygon to use
                        selected_polygon = self._select_polygon_from_list(containing_polygons)
                        if selected_polygon:
                            # Get polygon geometry and transform to point layer CRS if needed
                            polygon_layer = selected_polygon['layer']
                            polygon_geometry = QgsGeometry(selected_polygon['geometry'])
                            
                            polygon_crs = polygon_layer.crs()
                            point_crs = point_layer.crs()
                            
                            transform_success = True
                            if polygon_crs != point_crs:
                                try:
                                    transform = QgsCoordinateTransform(polygon_crs, point_crs, QgsProject.instance())
                                    polygon_geometry.transform(transform)
                                except Exception as e:
                                    self.show_error("CRS Transformation Error", 
                                        f"Failed to transform polygon geometry to point layer CRS: {str(e)}")
                                    transform_success = False
                                    if boundary_method == 'polygon':
                                        return
                                    # Will fall through to buffer method for 'auto'
                            
                            if transform_success:
                                boundary_geometry = polygon_geometry
                                boundary_description = f"Polygon boundary from layer '{selected_polygon['layer_name']}', feature ID {selected_polygon['feature_id']}"
                                use_polygon_boundary = True
                        else:
                            # User cancelled polygon selection
                            if boundary_method == 'polygon':
                                return  # Must use polygon, user cancelled
                            # Fall through to buffer method for 'auto'
                    # If should_use_polygon is False, we'll fall through to buffer method
                else:
                    # No polygons found containing all points
                    if boundary_method == 'polygon':
                        self.show_error("No Suitable Polygon", 
                            "No polygon found that contains all points. "
                            "Please ensure all points are within a single polygon feature, or use the buffer method instead.")
                        return
                    # Fall through to buffer method for 'auto'
            
            # Use buffer method if polygon boundary not available
            if not use_polygon_boundary:
                # Ask user for buffer distance
                buffer_distance = self._get_buffer_distance_from_user(
                    default_buffer_distance, buffer_unit_label, ask_for_buffer_distance, point_layer.name()
                )
                if buffer_distance is None:
                    return  # User cancelled
                
                # Create buffered boundary
                convex_hull_geometry = self._create_convex_hull_geometry(point_features)
                if not convex_hull_geometry or convex_hull_geometry.isEmpty():
                    self.show_error("Error", "Failed to create convex hull geometry")
                    return
                
                boundary_geometry = convex_hull_geometry.buffer(buffer_distance, 10)
                if not boundary_geometry or boundary_geometry.isEmpty():
                    self.show_error("Error", "Failed to create buffered boundary")
                    return
                
                boundary_description = f"Buffered convex hull (buffer: {buffer_distance} {buffer_unit_label})"
            
            # Show confirmation if requested
            if confirm_creation:
                confirmation_text = f"Create a Voronoi diagram from {len(point_features)} points in layer '{point_layer.name()}'?\n\n"
                confirmation_text += f"Boundary Method: {boundary_description}\n"
                confirmation_text += f"Process:\n"
                confirmation_text += f"1. Create Voronoi polygons\n"
                confirmation_text += f"2. Clip to boundary\n\n"
                confirmation_text += f"This will create a new polygon layer with individual Voronoi polygons."
                
                if not self.confirm_action("Create Voronoi Diagram", confirmation_text):
                    return
            
            # Create Voronoi diagram
            voronoi_polygons = self._create_voronoi_diagram(point_features, point_layer, boundary_geometry)
            if not voronoi_polygons:
                self.show_error("Error", "Failed to create Voronoi diagram")
                return
            
            # Create output layer name
            output_name = self._generate_output_layer_name(output_layer_name, point_layer.name())
            
            # Create the output polygon layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Voronoi Diagram Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first to build features
                temp_layer = self._create_output_layer(output_name, point_layer.crs())
                if not temp_layer:
                    self.show_error("Error", "Failed to create temporary layer")
                    return
                
                # Add Voronoi polygons to the temporary layer
                feature_backups = self._add_voronoi_polygons_to_layer(
                    temp_layer, voronoi_polygons, point_features, point_layer,
                    include_source_info, include_point_id, include_polygon_area, include_creation_timestamp
                )
                if not feature_backups:
                    self.show_error("Error", "Failed to add Voronoi polygons to layer")
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
                output_layer = QgsVectorLayer(save_path, output_name, "ogr")
                if not output_layer.isValid():
                    self.show_error("Error", "Failed to load saved layer")
                    return
            else:
                # Create temporary in-memory layer
                output_layer = self._create_output_layer(output_name, point_layer.crs())
                if not output_layer:
                    self.show_error("Error", "Failed to create output polygon layer")
                    return
                
                # Add Voronoi polygons to the output layer
                feature_backups = self._add_voronoi_polygons_to_layer(
                    output_layer, voronoi_polygons, point_features, point_layer,
                    include_source_info, include_point_id, include_polygon_area, include_creation_timestamp
                )
                if not feature_backups:
                    self.show_error("Error", "Failed to add Voronoi polygons to output layer")
                    return
            
            # Add layer to project if requested
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(output_layer)
            
            # Zoom to result if requested
            if zoom_to_result and canvas:
                self._zoom_to_voronoi_diagram(voronoi_polygons, canvas, point_layer.crs())
            
            # Show success message and detailed info
            if show_success_message:
                self._show_success_message(output_layer, len(point_features), len(voronoi_polygons), 
                                         boundary_description, show_detailed_info)

            # Record history: creating a new layer (store full layer definition for redo)
            try:
                from ..history_manager import get_history_manager
                history_manager = get_history_manager()

                # Build a lightweight layer definition for redo
                layer_def = self._build_layer_definition(output_layer)

                # Use BaseAction helper to create layer descriptor
                layers = [self.create_layer_descriptor(output_layer)]

                # Record features backups if available
                features_payload = feature_backups if 'feature_backups' in locals() and feature_backups else []

                self.record_to_history(
                    description=f"Created Voronoi diagram layer '{output_layer.name()}' ({len(voronoi_polygons)} polygons)",
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload={'layer_definitions': [layer_def]},
                    layers=layers,
                    features=features_payload,
                    meta={'boundary': boundary_description}
                )
            except Exception:
                # History recording must not break the action; log silently
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to create Voronoi diagram: {str(e)}")
    
    def _find_polygons_containing_all_points(self, point_features, point_layer):
        """
        Find all polygon features from all polygon layers that contain all points.
        
        Args:
            point_features (list): List of QgsFeature objects with point geometry
            point_layer (QgsVectorLayer): Source point layer
            
        Returns:
            list: List of dicts with 'layer', 'feature', 'layer_name', 'feature_id', 'geometry' keys
        """
        containing_polygons = []
        
        try:
            # Get all point geometries
            point_geometries = []
            for feature in point_features:
                geometry = feature.geometry()
                if geometry and not geometry.isEmpty():
                    point_geometries.append(geometry)
            
            if not point_geometries:
                return containing_polygons
            
            # Get all layers from project
            project = QgsProject.instance()
            all_layers = project.mapLayers().values()
            
            # Find all polygon layers
            polygon_layers = []
            for layer in all_layers:
                if isinstance(layer, QgsVectorLayer):
                    geometry_type = layer.geometryType()
                    # 2 = Polygon, 6 = MultiPolygon
                    if geometry_type in [2, 6]:
                        polygon_layers.append(layer)
            
            # Check each polygon feature to see if it contains all points
            for polygon_layer in polygon_layers:
                # Skip the source point layer if it's somehow a polygon layer
                if polygon_layer.id() == point_layer.id():
                    continue
                
                # Get CRS for transformation if needed
                polygon_crs = polygon_layer.crs()
                point_crs = point_layer.crs()
                needs_transform = polygon_crs != point_crs
                
                transform = None
                if needs_transform:
                    transform = QgsCoordinateTransform(point_crs, polygon_crs, project)
                
                # Check each polygon feature
                for polygon_feature in polygon_layer.getFeatures():
                    polygon_geometry = polygon_feature.geometry()
                    if not polygon_geometry or polygon_geometry.isEmpty():
                        continue
                    
                    # Check if this polygon contains all points
                    all_points_inside = True
                    for point_geometry in point_geometries:
                        # Transform point if needed
                        check_geometry = QgsGeometry(point_geometry)
                        if needs_transform:
                            try:
                                check_geometry.transform(transform)
                            except Exception:
                                all_points_inside = False
                                break
                        
                        # Check if point is inside polygon
                        if not polygon_geometry.contains(check_geometry):
                            all_points_inside = False
                            break
                    
                    if all_points_inside:
                        # This polygon contains all points
                        containing_polygons.append({
                            'layer': polygon_layer,
                            'feature': polygon_feature,
                            'layer_name': polygon_layer.name(),
                            'feature_id': polygon_feature.id(),
                            'geometry': polygon_geometry
                        })
            
            return containing_polygons
            
        except Exception as e:
            self.show_warning("Polygon Search Warning", f"Error while searching for containing polygons: {str(e)}")
            return containing_polygons
    
    def _ask_boundary_method_choice(self, polygon_count):
        """
        Ask user which boundary method they want to use.
        
        Args:
            polygon_count (int): Number of polygons found containing all points
            
        Returns:
            str: 'polygon' if user chose polygon method, 'buffer' if user chose buffer method, None if cancelled
        """
        from qgis.PyQt.QtWidgets import QMessageBox
        
        msg = QMessageBox()
        msg.setWindowTitle("Choose Boundary Method")
        msg.setText("Choose how to create the Voronoi diagram boundary:")
        msg.setInformativeText(
            f"Found {polygon_count} polygon(s) containing all points.\n\n"
            "• Polygon Boundary: Use the boundary of a selected polygon\n"
            "• Buffer Method: Create a convex hull around points and add a buffer"
        )
        
        polygon_button = msg.addButton("Use Polygon Boundary", QMessageBox.ActionRole)
        buffer_button = msg.addButton("Use Buffer Method", QMessageBox.ActionRole)
        cancel_button = msg.addButton("Cancel", QMessageBox.RejectRole)
        
        msg.setDefaultButton(polygon_button)
        
        result = msg.exec_()
        
        if msg.clickedButton() == polygon_button:
            return 'polygon'
        elif msg.clickedButton() == buffer_button:
            return 'buffer'
        else:
            return None
    
    def _select_polygon_from_list(self, containing_polygons):
        """
        Let user select which polygon to use from a list of containing polygons.
        
        Args:
            containing_polygons (list): List of dicts with polygon information
            
        Returns:
            dict: Selected polygon dict or None if user cancelled
        """
        if not containing_polygons:
            return None
        
        if len(containing_polygons) == 1:
            # Only one polygon, use it automatically
            return containing_polygons[0]
        
        # Multiple polygons found, let user choose
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton, QDialogButtonBox
        
        dialog = QDialog()
        dialog.setWindowTitle("Select Polygon Boundary")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        dialog.setLayout(layout)
        
        # Add label
        label = QLabel(
            f"Multiple polygons found that contain all points.\n"
            f"Please select which polygon to use as the Voronoi diagram boundary:"
        )
        layout.addWidget(label)
        
        # Add list widget
        list_widget = QListWidget()
        for i, poly_info in enumerate(containing_polygons):
            # Try to get a descriptive name for the feature
            feature = poly_info['feature']
            layer_name = poly_info['layer_name']
            feature_id = poly_info['feature_id']
            
            # Try to find a name field
            display_name = f"Feature ID {feature_id}"
            layer = poly_info['layer']
            fields = layer.fields()
            
            # Look for common name fields
            name_fields = ['name', 'Name', 'NAME', 'label', 'Label', 'title', 'Title']
            for name_field in name_fields:
                if name_field in [field.name() for field in fields]:
                    idx = layer.fields().indexFromName(name_field)
                    if idx >= 0:
                        name_value = feature.attribute(idx)
                        if name_value:
                            display_name = str(name_value)
                            break
            
            item_text = f"{layer_name} - {display_name} (ID: {feature_id})"
            list_widget.addItem(item_text)
        
        list_widget.setCurrentRow(0)  # Select first item
        layout.addWidget(list_widget)
        
        # Add buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # Show dialog
        if dialog.exec_() == QDialog.Accepted:
            selected_index = list_widget.currentRow()
            if 0 <= selected_index < len(containing_polygons):
                return containing_polygons[selected_index]
        
        return None
    
    def _get_buffer_distance_from_user(self, default_distance, unit_label, ask_user, layer_name):
        """
        Get buffer distance from user input.
        
        Args:
            default_distance (float): Default buffer distance
            unit_label (str): Unit label for display
            ask_user (bool): Whether to ask user or use default
            layer_name (str): Name of the source layer
            
        Returns:
            float: Buffer distance or None if user cancelled
        """
        if not ask_user:
            return default_distance
        
        try:
            distance, ok = QInputDialog.getDouble(
                None,
                "Buffer Distance for Voronoi Diagram",
                f"Enter buffer distance to add around the convex hull of layer '{layer_name}':\n"
                f"(Distance in {unit_label})",
                default_distance,
                0.1,
                10000.0,
                2
            )
            
            if ok:
                return distance
            else:
                return None
                
        except Exception as e:
            self.show_error("Error", f"Failed to get buffer distance from user: {str(e)}")
            return None
    
    def _create_voronoi_diagram(self, point_features, point_layer, boundary_geometry):
        """
        Create Voronoi diagram from point features within a boundary.
        
        Args:
            point_features (list): List of QgsFeature objects with point geometry
            point_layer (QgsVectorLayer): Source point layer
            boundary_geometry (QgsGeometry): Boundary geometry to clip Voronoi polygons
            
        Returns:
            list: List of QgsGeometry objects representing Voronoi polygons
        """
        try:
            # Collect all point coordinates
            points = []
            for feature in point_features:
                geometry = feature.geometry()
                if geometry and not geometry.isEmpty():
                    point = geometry.asPoint()
                    points.append(point)
            
            if len(points) < 3:
                return None
            
            # Validate boundary geometry
            if not boundary_geometry or boundary_geometry.isEmpty():
                self.show_error("Error", "Invalid boundary geometry")
                return None
            
            # Create Voronoi diagram using QGIS processing
            from qgis import processing
            from qgis.core import QgsProcessingContext, QgsProcessingFeedback
            
            # Create processing context and feedback
            context = QgsProcessingContext()
            feedback = QgsProcessingFeedback()
            
            # Create temporary point layer for processing
            temp_layer = self._create_temp_point_layer(points, point_layer.crs())
            if not temp_layer:
                return None
            
            # Create boundary layer for clipping
            boundary_layer = self._create_boundary_layer(boundary_geometry, point_layer.crs())
            if not boundary_layer:
                return None
            
            # Create Voronoi diagram with large buffer first
            try:
                # Use a large buffer to ensure we get all Voronoi polygons
                # Calculate buffer based on boundary extent
                boundary_extent = boundary_geometry.boundingBox()
                large_buffer = max(boundary_extent.width(), boundary_extent.height()) * 0.5
                voronoi_result = processing.run(
                    "qgis:voronoipolygons",
                    {
                        'INPUT': temp_layer,
                        'BUFFER': large_buffer,
                        'OUTPUT': 'memory:'
                    },
                    context=context,
                    feedback=feedback
                )
                
                if not voronoi_result or 'OUTPUT' not in voronoi_result:
                    self.show_error("Error", "Voronoi algorithm returned no output")
                    return None
                
                voronoi_layer = voronoi_result['OUTPUT']
                
                # Clip Voronoi polygons with the buffered boundary
                clip_result = processing.run(
                    "native:clip",
                    {
                        'INPUT': voronoi_layer,
                        'OVERLAY': boundary_layer,
                        'OUTPUT': 'memory:'
                    },
                    context=context,
                    feedback=feedback
                )
                
                if not clip_result or 'OUTPUT' not in clip_result:
                    self.show_error("Error", "Failed to clip Voronoi polygons with boundary")
                    return None
                
                clipped_layer = clip_result['OUTPUT']
                
                # Extract geometries
                voronoi_polygons = []
                for feature in clipped_layer.getFeatures():
                    geometry = feature.geometry()
                    if geometry and not geometry.isEmpty():
                        voronoi_polygons.append(geometry)
                
                return voronoi_polygons
                
            except Exception as processing_error:
                self.show_error("Processing Error", f"QGIS processing algorithm failed: {str(processing_error)}")
                return None
            
        except Exception as e:
            self.show_error("Error", f"Failed to create Voronoi diagram: {str(e)}")
            return None
    
    def _create_convex_hull_geometry(self, point_features):
        """
        Create convex hull geometry from point features.
        
        Args:
            point_features (list): List of QgsFeature objects with point geometry
            
        Returns:
            QgsGeometry: Convex hull geometry or None if failed
        """
        try:
            # Collect all point geometries
            point_geometries = []
            for feature in point_features:
                geometry = feature.geometry()
                if geometry and not geometry.isEmpty():
                    point_geometries.append(geometry)
            
            if not point_geometries:
                return None
            
            # Create a multi-point geometry from all points
            from qgis.core import QgsGeometry, QgsWkbTypes
            multi_point = QgsGeometry.fromMultiPointXY([geom.asPoint() for geom in point_geometries])
            
            # Create convex hull
            convex_hull = multi_point.convexHull()
            
            return convex_hull
            
        except Exception as e:
            self.show_error("Error", f"Failed to create convex hull geometry: {str(e)}")
            return None
    
    def _create_boundary_layer(self, boundary_geometry, crs):
        """
        Create boundary layer from geometry.
        
        Args:
            boundary_geometry (QgsGeometry): Boundary geometry
            crs: Coordinate reference system
            
        Returns:
            QgsVectorLayer: Boundary layer or None if failed
        """
        try:
            # Create memory layer with proper CRS string
            crs_string = crs.authid() if crs.authid() else crs.toWkt()
            layer = QgsVectorLayer(f"Polygon?crs={crs_string}", "temp_boundary", "memory")
            
            if not layer.isValid():
                self.show_error("Error", f"Failed to create valid boundary layer. CRS: {crs_string}")
                return None
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int))
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            # Add boundary feature
            if not layer.startEditing():
                self.show_error("Error", "Failed to start editing boundary layer")
                return None
            
            feature = QgsFeature()
            feature.setGeometry(boundary_geometry)
            feature.setAttributes([1])
            
            if not layer.addFeature(feature):
                self.show_error("Error", "Failed to add boundary feature")
                layer.rollBack()
                return None
            
            if not layer.commitChanges():
                self.show_error("Error", "Failed to commit boundary layer changes")
                layer.rollBack()
                return None
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create boundary layer: {str(e)}")
            return None
    
    def _create_temp_point_layer(self, points, crs):
        """
        Create temporary point layer for processing.
        
        Args:
            points (list): List of QgsPointXY objects
            crs: Coordinate reference system
            
        Returns:
            QgsVectorLayer: Temporary layer or None if failed
        """
        try:
            # Create memory layer with proper CRS string
            crs_string = crs.authid() if crs.authid() else crs.toWkt()
            layer = QgsVectorLayer(f"Point?crs={crs_string}", "temp_points", "memory")
            
            if not layer.isValid():
                self.show_error("Error", f"Failed to create valid temporary layer. CRS: {crs_string}")
                return None
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int))
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            # Add features
            if not layer.startEditing():
                self.show_error("Error", "Failed to start editing temporary layer")
                return None
            
            for i, point in enumerate(points):
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                feature.setAttributes([i])
                if not layer.addFeature(feature):
                    self.show_error("Error", f"Failed to add point {i} to temporary layer")
                    layer.rollBack()
                    return None
            
            if not layer.commitChanges():
                self.show_error("Error", "Failed to commit changes to temporary layer")
                layer.rollBack()
                return None
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create temporary point layer: {str(e)}")
            return None
    
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
    
    def _create_output_layer(self, layer_name, crs):
        """
        Create output polygon layer.
        
        Args:
            layer_name (str): Name for the output layer
            crs: Coordinate reference system
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            # Create memory layer
            layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", layer_name, "memory")
            if not layer.isValid():
                return None
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int))
            fields.append(QgsField('point_id', QVariant.Int))
            fields.append(QgsField('area', QVariant.Double))
            fields.append(QgsField('source_layer', QVariant.String))
            fields.append(QgsField('created_at', QVariant.String))
            
            # Set fields
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create output layer: {str(e)}")
            return None

    def _build_layer_definition(self, layer):
        """
        Build a serializable layer definition for history redo.
        Stores fields and feature geometries/attributes.
        """
        try:
            from qgis.core import QgsWkbTypes
            import base64

            layer_def = {
                'layer_name': layer.name(),
                'crs': layer.crs().authid() if layer.crs().isValid() else '',
                # Use display string for geometry type so handler can construct layer uri
                'geometry_type': QgsWkbTypes.displayString(layer.wkbType()),
                'fields': [],
                'features': []
            }

            # Fields
            for field in layer.fields():
                # Provide qmeta_type to help handler choose QgsField type
                layer_def['fields'].append({
                    'name': field.name(),
                    'type': field.type(),
                    'qmeta_type': field.type(),
                    'length': field.length(),
                    'precision': field.precision()
                })

            # Features: store WKB hex and attributes
            for feat in layer.getFeatures():
                geom_b64 = None
                if feat.hasGeometry() and feat.geometry() is not None:
                    try:
                        wkb = feat.geometry().asWkb()
                        geom_b64 = base64.b64encode(wkb).decode('utf-8')
                    except Exception:
                        geom_b64 = None

                # Build attributes dict keyed by field name (handler expects this)
                attrs = {}
                for field in layer.fields():
                    try:
                        val = feat.attribute(field.name())
                        if hasattr(val, 'isNull') and val.isNull():
                            val = None
                        attrs[field.name()] = val
                    except Exception:
                        try:
                            attrs[field.name()] = str(feat.attribute(field.name()))
                        except Exception:
                            attrs[field.name()] = None

                layer_def['features'].append({
                    'fid': feat.id(),
                    'geometry': {'wkb_base64': geom_b64} if geom_b64 else {},
                    'attributes': attrs
                })

            return layer_def
        except Exception:
            return {'layer_name': layer.name() if layer else 'unknown'}
    
    def _add_voronoi_polygons_to_layer(self, layer, voronoi_polygons, point_features, source_layer,
                                     include_source_info, include_point_id, include_polygon_area, include_creation_timestamp):
        """
        Add Voronoi polygons to the output layer.
        
        Args:
            layer (QgsVectorLayer): Output layer
            voronoi_polygons (list): List of Voronoi polygon geometries
            point_features (list): List of source point features
            source_layer (QgsVectorLayer): Source point layer
            include_source_info (bool): Whether to include source info
            include_point_id (bool): Whether to include point ID
            include_polygon_area (bool): Whether to include polygon area
            include_creation_timestamp (bool): Whether to include timestamp
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use edit helpers to ensure correct edit-mode handling
            was_editing, edit_entered = self.handle_edit_mode(layer, "adding voronoi polygons")
            if was_editing is None:
                return None

            features_to_add = []
            for i, polygon_geometry in enumerate(voronoi_polygons):
                feature = QgsFeature(layer.fields())
                feature.setGeometry(polygon_geometry)

                # Set attributes in same order as layer.fields()
                attributes = []
                # id (generate sequential id)
                attributes.append(i + 1)

                # point_id
                if include_point_id and i < len(point_features):
                    attributes.append(point_features[i].id())
                else:
                    attributes.append(-1)

                # area
                if include_polygon_area:
                    try:
                        area = polygon_geometry.area()
                        attributes.append(area)
                    except Exception:
                        attributes.append(0.0)
                else:
                    attributes.append(0.0)

                # source_layer
                if include_source_info:
                    attributes.append(source_layer.name())
                else:
                    attributes.append("")

                # created_at
                if include_creation_timestamp:
                    from datetime import datetime
                    attributes.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    attributes.append("")

                feature.setAttributes(attributes)
                features_to_add.append(feature)

            # Use dataProvider().addFeatures() to get proper assigned FIDs
            provider = layer.dataProvider()
            success, added = provider.addFeatures(features_to_add)
            if not success:
                if not was_editing:
                    layer.rollBack()
                self.show_error("Error", "Failed to add features via dataProvider")
                return None

            # Commit changes using helper
            if not self.commit_changes(layer, "adding voronoi polygons"):
                # commit_changes already shows an error and rolls back
                return None

            # Build feature backups for history/redo
            backups = []
            try:
                from qgis.core import QgsFeatureRequest
                for f in added:
                    fid = f.id()
                    # Fetch the created feature reliably
                    created = None
                    for feat in layer.getFeatures(QgsFeatureRequest().setFilterFid(fid)):
                        created = feat
                        break
                    if created:
                        backups.append(self.create_feature_backup(created, layer))
            except Exception:
                # If backups fail, still return empty list
                backups = []

            return backups

        except Exception as e:
            try:
                if layer and layer.isEditable():
                    layer.rollBack()
            except Exception:
                pass
            self.show_error("Error", f"Failed to add Voronoi polygons to layer: {str(e)}")
            return None
    
    def _zoom_to_voronoi_diagram(self, voronoi_polygons, canvas, layer_crs):
        """
        Zoom to the Voronoi diagram.
        
        Args:
            voronoi_polygons (list): List of Voronoi polygon geometries
            canvas (QgsMapCanvas): Map canvas
            layer_crs: Layer coordinate reference system
        """
        try:
            if not voronoi_polygons:
                return
            
            # Calculate combined extent
            combined_extent = None
            for geometry in voronoi_polygons:
                extent = geometry.boundingBox()
                if combined_extent is None:
                    combined_extent = extent
                else:
                    combined_extent.combineExtentWith(extent)
            
            if combined_extent.isEmpty():
                return
            
            # Transform extent to canvas CRS if needed
            canvas_crs = canvas.mapSettings().destinationCrs()
            if canvas_crs != layer_crs:
                from qgis.core import QgsCoordinateTransform, QgsProject
                transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                try:
                    combined_extent = transform.transformBoundingBox(combined_extent)
                except Exception:
                    pass  # Use original extent if transformation fails
            
            # Add 10% buffer
            width = combined_extent.width()
            height = combined_extent.height()
            buffer_x = width * 0.1
            buffer_y = height * 0.1
            
            combined_extent.setXMinimum(combined_extent.xMinimum() - buffer_x)
            combined_extent.setXMaximum(combined_extent.xMaximum() + buffer_x)
            combined_extent.setYMinimum(combined_extent.yMinimum() - buffer_y)
            combined_extent.setYMaximum(combined_extent.yMaximum() + buffer_y)
            
            # Zoom to extent
            canvas.setExtent(combined_extent)
            canvas.refresh()
            
        except Exception as e:
            self.show_warning("Zoom Warning", f"Failed to zoom to Voronoi diagram: {str(e)}")
    
    def _show_success_message(self, output_layer, point_count, polygon_count, boundary_description, 
                            show_detailed_info):
        """
        Show success message with optional detailed information.
        
        Args:
            output_layer (QgsVectorLayer): Created output layer
            point_count (int): Number of points used
            polygon_count (int): Number of Voronoi polygons created
            boundary_description (str): Description of boundary method used
            show_detailed_info (bool): Whether to show detailed info
        """
        message = f"Voronoi diagram created successfully!\n\n"
        message += f"Output Layer: {output_layer.name()}\n"
        message += f"Points Used: {point_count}\n"
        message += f"Voronoi Polygons Created: {polygon_count}\n"
        message += f"Boundary: {boundary_description}\n"
        
        if show_detailed_info:
            try:
                total_area = 0.0
                for feature in output_layer.getFeatures():
                    geometry = feature.geometry()
                    if geometry:
                        total_area += geometry.area()
                message += f"Total Area: {total_area:.2f} square units\n"
            except Exception:
                pass
        
        self.show_info("Voronoi Diagram Created", message)


# REQUIRED: Create global instance for automatic discovery
create_voronoi_diagram_from_points_action = CreateVoronoiDiagramFromPointsAction()
