"""
Create Convex Hull from Points Action for Right-click Utilities and Shortcuts Hub

Creates a convex hull polygon that encompasses all points from the selected point layer.
The generated polygon will have all points from the layer lying on its boundary.
"""

from .base_action import BaseAction
from qgis.core import QgsVectorLayer, QgsProject, QgsGeometry, QgsFeature, QgsField, QgsFields, QgsWkbTypes
from qgis.PyQt.QtCore import QVariant
from ..history_manager import get_history_manager, HistoryManager


class CreateConvexHullFromPointsAction(BaseAction):
    """
    Action to create a convex hull polygon from all points in a point layer.
    
    This action takes all points from the selected point layer and creates a convex hull
    polygon that encompasses all the points. The points will lie on the boundary of the
    generated polygon. A new polygon layer is created to store the result.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_convex_hull_from_points"
        self.name = "Create Convex Hull from Points"
        self.category = "Geometry"
        self.description = "Create a convex hull polygon that encompasses all points from the selected point layer. Generates a new polygon layer with the convex hull where all points lie on the boundary."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with point features
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
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
                'default': 'Convex Hull from {source_layer}',
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
                'description': 'Zoom the map to show the generated convex hull polygon',
            },
            
            # ATTRIBUTE SETTINGS - Control what attributes to include
            'include_source_info': {
                'type': 'bool',
                'default': True,
                'label': 'Include Source Information',
                'description': 'Add attributes with information about the source point layer',
            },
            'include_point_count': {
                'type': 'bool',
                'default': True,
                'label': 'Include Point Count',
                'description': 'Add attribute showing the number of points used to create the convex hull',
            },
            'include_area_perimeter': {
                'type': 'bool',
                'default': True,
                'label': 'Include Area and Perimeter',
                'description': 'Add attributes showing the area and perimeter of the convex hull',
            },
            'include_creation_timestamp': {
                'type': 'bool',
                'default': True,
                'label': 'Include Creation Timestamp',
                'description': 'Add attribute showing when the convex hull was created',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'confirm_creation': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Creation',
                'description': 'Show confirmation dialog before creating the convex hull',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when convex hull is created successfully',
            },
            'show_detailed_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Detailed Information',
                'description': 'Display detailed information about the created convex hull',
            },
            'minimum_points_required': {
                'type': 'int',
                'default': 3,
                'label': 'Minimum Points Required',
                'description': 'Minimum number of points required to create a valid convex hull',
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
        Execute the create convex hull from points action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Convex Hull from {source_layer}'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_result = bool(self.get_setting('zoom_to_result', True))
            include_source_info = bool(self.get_setting('include_source_info', True))
            include_point_count = bool(self.get_setting('include_point_count', True))
            include_area_perimeter = bool(self.get_setting('include_area_perimeter', True))
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
                    f"At least {minimum_points_required} points are required to create a convex hull. "
                    f"Found only {len(point_features)} points in layer '{point_layer.name()}'.")
                return
            
            # Show confirmation if requested
            if confirm_creation:
                if not self.confirm_action(
                    "Create Convex Hull",
                    f"Create a convex hull polygon from {len(point_features)} points in layer '{point_layer.name()}'?\n\n"
                    f"This will create a new polygon layer with the convex hull."
                ):
                    return
            
            # Create convex hull geometry
            convex_hull_geometry = self._create_convex_hull_geometry(point_features)
            if not convex_hull_geometry or convex_hull_geometry.isEmpty():
                self.show_error("Error", "Failed to create convex hull geometry")
                return
            
            # Create output layer name
            output_name = self._generate_output_layer_name(output_layer_name, point_layer.name())
            
            # Create the convex hull feature first (needed for both temporary and permanent)
            convex_hull_feature = self._create_convex_hull_feature(
                convex_hull_geometry, 
                point_layer, 
                len(point_features),
                include_source_info,
                include_point_count,
                include_area_perimeter,
                include_creation_timestamp
            )
            
            # Create the output polygon layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Convex Hull Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first to build features
                temp_layer = self._create_output_layer(output_name, point_layer.crs())
                if not temp_layer:
                    self.show_error("Error", "Failed to create temporary layer")
                    return
                
                # Add feature to temporary layer
                if not self._add_feature_to_layer(temp_layer, convex_hull_feature):
                    self.show_error("Error", "Failed to add convex hull feature to layer")
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
                
                # Add feature to output layer
                if not self._add_feature_to_layer(output_layer, convex_hull_feature):
                    self.show_error("Error", "Failed to add convex hull feature to output layer")
                    return
            
            # Add layer to project if requested
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(output_layer)

                # Record history: creation of the new layer
                try:
                    hm = get_history_manager()

                    # Collect created feature (new layer is fresh so first feature is ours)
                    created_features = list(output_layer.getFeatures())
                    feat_backups = []
                    for f in created_features:
                        fb = hm.create_feature_backup(f, output_layer, include_geometry=True, include_attributes=True)
                        feat_backups.append(fb)

                    # Layer descriptor for quick refs
                    layer_desc = hm.create_layer_descriptor(output_layer)

                    # Layer definition to allow redo of the layer (structure + backups)
                    layer_def = {
                        'layer_name': output_layer.name(),
                        'crs': output_layer.crs().authid() if output_layer.crs().isValid() else '',
                        'geometry_type': QgsWkbTypes.displayString(output_layer.wkbType()),
                        'fields': [],
                        'features': feat_backups,
                    }
                    for fld in output_layer.fields():
                        try:
                            layer_def['fields'].append({'name': fld.name(), 'qmeta_type': fld.type()})
                        except Exception:
                            layer_def['fields'].append({'name': fld.name()})

                    # Record history entry using CREATE_LAYER undo type (simpler, proven to work)
                    hm.record(
                        action_id=self.action_id,
                        action_name=self.name,
                        description=f"Created convex hull layer '{output_layer.name()}' with {len(feat_backups)} feature(s)",
                        undo_type=HistoryManager.UNDO_TYPE_CREATE_LAYER,
                        can_undo=True,
                        undo_payload={'layer_definition': layer_def},
                        layers=[layer_desc],
                        features=feat_backups,
                        atomic=True,
                        meta={'source_layer': point_layer.id(), 'source_layer_name': point_layer.name()}
                    )
                except Exception:
                    # History recording must not prevent successful action
                    pass
            
            # Zoom to result if requested
            if zoom_to_result and canvas:
                self._zoom_to_convex_hull(convex_hull_geometry, canvas, point_layer.crs())
            
            # Show success message and detailed info
            if show_success_message:
                self._show_success_message(output_layer, len(point_features), show_detailed_info, convex_hull_geometry)
            
        except Exception as e:
            self.show_error("Error", f"Failed to create convex hull: {str(e)}")
    
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
            from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsField, QgsFields
            from qgis.PyQt.QtCore import QVariant
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int))
            
            # Create layer
            layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", layer_name, "memory")
            if not layer.isValid():
                return None
            
            # Set fields
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create output layer: {str(e)}")
            return None
    
    def _create_convex_hull_feature(self, geometry, source_layer, point_count, 
                                  include_source_info, include_point_count, 
                                  include_area_perimeter, include_creation_timestamp):
        """
        Create convex hull feature with attributes.
        
        Args:
            geometry (QgsGeometry): Convex hull geometry
            source_layer (QgsVectorLayer): Source point layer
            point_count (int): Number of points used
            include_source_info (bool): Whether to include source info
            include_point_count (bool): Whether to include point count
            include_area_perimeter (bool): Whether to include area/perimeter
            include_creation_timestamp (bool): Whether to include timestamp
            
        Returns:
            QgsFeature: Created feature
        """
        try:
            feature = QgsFeature()
            feature.setGeometry(geometry)
            
            # Set attributes
            attributes = [1]  # id field
            
            # Add additional fields if needed
            if include_source_info:
                # Add source layer name field
                pass
            if include_point_count:
                # Add point count field
                pass
            if include_area_perimeter:
                # Add area and perimeter fields
                pass
            if include_creation_timestamp:
                # Add creation timestamp field
                pass
            
            feature.setAttributes(attributes)
            return feature
            
        except Exception as e:
            self.show_error("Error", f"Failed to create convex hull feature: {str(e)}")
            return None
    
    def _add_feature_to_layer(self, layer, feature):
        """
        Add feature to layer.
        
        Args:
            layer (QgsVectorLayer): Target layer
            feature (QgsFeature): Feature to add
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Start editing
            if not layer.startEditing():
                return False
            
            # Add feature
            if not layer.addFeature(feature):
                layer.rollBack()
                return False
            
            # Commit changes
            if not layer.commitChanges():
                layer.rollBack()
                return False
            
            return True
            
        except Exception as e:
            self.show_error("Error", f"Failed to add feature to layer: {str(e)}")
            return False
    
    def _zoom_to_convex_hull(self, geometry, canvas, layer_crs):
        """
        Zoom to the convex hull geometry.
        
        Args:
            geometry (QgsGeometry): Convex hull geometry
            canvas (QgsMapCanvas): Map canvas
            layer_crs: Layer coordinate reference system
        """
        try:
            # Get geometry extent
            extent = geometry.boundingBox()
            if extent.isEmpty():
                return
            
            # Transform extent to canvas CRS if needed
            canvas_crs = canvas.mapSettings().destinationCrs()
            if canvas_crs != layer_crs:
                from qgis.core import QgsCoordinateTransform, QgsProject
                transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                try:
                    extent = transform.transformBoundingBox(extent)
                except Exception:
                    pass  # Use original extent if transformation fails
            
            # Add 10% buffer
            width = extent.width()
            height = extent.height()
            buffer_x = width * 0.1
            buffer_y = height * 0.1
            
            extent.setXMinimum(extent.xMinimum() - buffer_x)
            extent.setXMaximum(extent.xMaximum() + buffer_x)
            extent.setYMinimum(extent.yMinimum() - buffer_y)
            extent.setYMaximum(extent.yMaximum() + buffer_y)
            
            # Zoom to extent
            canvas.setExtent(extent)
            canvas.refresh()
            
        except Exception as e:
            self.show_warning("Zoom Warning", f"Failed to zoom to convex hull: {str(e)}")
    
    def _show_success_message(self, output_layer, point_count, show_detailed_info, geometry):
        """
        Show success message with optional detailed information.
        
        Args:
            output_layer (QgsVectorLayer): Created output layer
            point_count (int): Number of points used
            show_detailed_info (bool): Whether to show detailed info
            geometry (QgsGeometry): Convex hull geometry
        """
        message = f"Convex hull created successfully!\n\n"
        message += f"Output Layer: {output_layer.name()}\n"
        message += f"Points Used: {point_count}\n"
        
        if show_detailed_info:
            try:
                area = geometry.area()
                perimeter = geometry.length()
                message += f"Area: {area:.2f} square units\n"
                message += f"Perimeter: {perimeter:.2f} units\n"
            except Exception:
                pass
        
        self.show_info("Convex Hull Created", message)


# REQUIRED: Create global instance for automatic discovery
create_convex_hull_from_points_action = CreateConvexHullFromPointsAction()
