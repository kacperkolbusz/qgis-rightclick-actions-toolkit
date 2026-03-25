"""
Create Lines From Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Creates line features from the outlines/boundaries of all polygon features in a layer.
Extracts each polygon's exterior ring and creates a new line layer with all boundaries.
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager, HistoryManager
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant, QDateTime
from qgis.PyQt.QtWidgets import QMessageBox
import os


class CreateLinesFromPolygonLayerAction(BaseAction):
    """Action to create line features from all polygon boundaries in a layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_lines_from_polygon_layer"
        self.name = "Create Lines From Polygon Layer"
        self.category = "Geometry"
        self.description = "Create line features from the outlines/boundaries of all polygon features in the selected layer. Extracts each polygon's exterior ring and creates a new line layer with all boundaries. Preserves the original polygon layer's CRS and optionally includes metadata about source features."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def supports_undo(self) -> bool:
        """This action creates a new layer and is undoable via layer removal."""
        return True

    def get_undo_category(self) -> str:
        """Classify as 'trivial' (create -> delete) per the guide."""
        return 'trivial'
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # OUTPUT SETTINGS - Easy to customize output
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'default': 'Lines_{layer_name}',
                'label': 'Layer Name Template',
                'description': 'Template for the new line layer name. Available variables: {layer_name}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created line layer to the project',
            },
            'include_metadata': {
                'type': 'bool',
                'default': True,
                'label': 'Include Metadata',
                'description': 'Include metadata fields in the line layer (source feature ID, source layer name, creation date)',
            },
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'Only create lines from selected polygon features (if any are selected)',
            },
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip polygons with invalid or empty geometries instead of showing an error',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created line layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after creating the line layer',
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
    
    def _extract_boundary_line(self, polygon_geometry):
        """
        Extract the boundary line from a polygon geometry.
        Works with both single and multipart polygons.
        
        Args:
            polygon_geometry (QgsGeometry): Polygon geometry
            
        Returns:
            QgsGeometry: Line geometry representing the boundary, or None if failed
        """
        from qgis.core import QgsPointXY
        
        try:
            # Ensure geometry is valid and not empty
            if polygon_geometry.isEmpty():
                return None
            
            # Try to make valid if needed
            if not polygon_geometry.isGeosValid():
                polygon_geometry = polygon_geometry.makeValid()
                if polygon_geometry.isEmpty():
                    return None
            
            # Method 1: Use boundary() method - this should work for both single and multipart
            try:
                boundary = polygon_geometry.boundary()
                if boundary and not boundary.isEmpty():
                    # For multipart polygons, boundary() returns MultiLineString
                    # For single polygons, it returns LineString
                    # Both are valid line geometries
                    if boundary.type() == QgsWkbTypes.LineGeometry:
                        # This handles both LineString and MultiLineString
                        return boundary
                    
                    # If type check failed but boundary exists, return it anyway
                    return boundary
            except Exception as e:
                print(f"Boundary() method failed: {str(e)}")
            
            # Method 2: Manually extract exterior ring(s) - handles multipart explicitly
            try:
                if polygon_geometry.type() != QgsWkbTypes.PolygonGeometry:
                    return None
                
                # Handle multipart polygons
                if polygon_geometry.isMultipart():
                    # For multipart, extract exterior ring from each part
                    all_lines = []
                    for part in polygon_geometry.asGeometryCollection():
                        if part and part.type() == QgsWkbTypes.PolygonGeometry:
                            # Get exterior ring
                            exterior_ring = part.exteriorRing()
                            if exterior_ring:
                                num_points = exterior_ring.numPoints()
                                if num_points >= 2:
                                    # Extract all points from the ring
                                    points = []
                                    for i in range(num_points):
                                        try:
                                            point = exterior_ring.pointN(i)
                                            if point:
                                                points.append(QgsPointXY(point.x(), point.y()))
                                        except Exception:
                                            continue
                                    
                                    # Create line geometry from points
                                    if len(points) >= 2:
                                        line_geom = QgsGeometry.fromPolylineXY(points)
                                        if line_geom and not line_geom.isEmpty():
                                            all_lines.append(line_geom)
                    
                    # Return first line (or combine all if needed - for now just first)
                    if all_lines:
                        return all_lines[0]
                else:
                    # Single polygon - extract exterior ring
                    exterior_ring = polygon_geometry.exteriorRing()
                    if exterior_ring:
                        num_points = exterior_ring.numPoints()
                        if num_points >= 2:
                            # Extract all points from the ring
                            points = []
                            for i in range(num_points):
                                try:
                                    point = exterior_ring.pointN(i)
                                    if point:
                                        points.append(QgsPointXY(point.x(), point.y()))
                                except Exception:
                                    continue
                            
                            # Create line geometry from points
                            if len(points) >= 2:
                                line_geom = QgsGeometry.fromPolylineXY(points)
                                if line_geom and not line_geom.isEmpty():
                                    return line_geom
            except Exception as e:
                print(f"Manual extraction failed: {str(e)}")
            
            # Method 3: Try using asPolygon() / asMultiPolygon() to get polygon structure
            try:
                if polygon_geometry.isMultipart():
                    # Multipart polygon
                    multi_polygon = polygon_geometry.asMultiPolygon()
                    if multi_polygon and len(multi_polygon) > 0:
                        # Get first polygon's exterior ring
                        first_polygon = multi_polygon[0]
                        if first_polygon and len(first_polygon) > 0:
                            exterior_ring_points = first_polygon[0]  # First ring is exterior
                            if len(exterior_ring_points) >= 2:
                                points = [QgsPointXY(p.x(), p.y()) for p in exterior_ring_points]
                                line_geom = QgsGeometry.fromPolylineXY(points)
                                if line_geom and not line_geom.isEmpty():
                                    return line_geom
                else:
                    # Single polygon
                    polygon = polygon_geometry.asPolygon()
                    if polygon and len(polygon) > 0:
                        # First element is exterior ring
                        exterior_ring_points = polygon[0]
                        if len(exterior_ring_points) >= 2:
                            points = [QgsPointXY(p.x(), p.y()) for p in exterior_ring_points]
                            line_geom = QgsGeometry.fromPolylineXY(points)
                            if line_geom and not line_geom.isEmpty():
                                return line_geom
            except Exception as e:
                print(f"asPolygon()/asMultiPolygon() method failed: {str(e)}")
            
            return None
            
        except Exception as e:
            print(f"Error extracting boundary: {str(e)}")
            return None
    
    def _create_line_layer(self, line_features, layer_name, source_crs, include_metadata, source_layer_name, output_file_path=None, file_format=None, create_permanent=False):
        """
        Create a new line layer with all boundary geometries.
        
        Args:
            line_features (list): List of tuples (line_geometry, source_feature_id)
            layer_name (str): Name for the new layer
            source_crs: CRS of the source layer
            include_metadata (bool): Whether to include metadata fields
            source_layer_name: Name of the source layer
            output_file_path (str): Path where to save the file (only for permanent layers)
            file_format (str): File format (ESRI Shapefile, GPKG, etc.) (only for permanent layers)
            create_permanent (bool): If True, create file-based layer; if False, create temporary memory layer
            
        Returns:
            QgsVectorLayer: New layer containing the lines, or None if failed
        """
        try:
            # Create temporary memory layer for lines
            crs_string = source_crs.authid() if source_crs.authid() else source_crs.toWkt()
            temp_layer = QgsVectorLayer(f"LineString?crs={crs_string}", layer_name, "memory")
            
            if not temp_layer.isValid():
                return None
            
            # Add fields
            fields = QgsFields()
            if include_metadata:
                fields.append(QgsField("source_feature_id", QVariant.Int))
                fields.append(QgsField("source_layer", QVariant.String))
                fields.append(QgsField("created_at", QVariant.String))
            
            temp_layer.dataProvider().addAttributes(fields.toList())
            temp_layer.updateFields()
            
            # Add all line features
            features_to_add = []
            for line_geometry, source_feature_id in line_features:
                feature = QgsFeature()
                feature.setGeometry(line_geometry)
                
                # Set attributes
                if include_metadata:
                    feature.setAttributes([
                        source_feature_id,
                        source_layer_name,
                        QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
                    ])
                
                features_to_add.append(feature)
            
            # Add all features at once
            temp_layer.dataProvider().addFeatures(features_to_add)
            temp_layer.updateExtents()

            # Determine created feature ids for the newly added features
            created_fids = []
            try:
                for f in temp_layer.getFeatures():
                    created_fids.append(f.id())
            except Exception:
                created_fids = []

            # If creating temporary layer, return it and the created fids
            if not create_permanent:
                return temp_layer, created_fids
            
            # Otherwise, write to file and load it
            if not output_file_path or not file_format:
                return None
            
            # Write to file
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = file_format
            options.fileEncoding = "UTF-8"
            
            if file_format == "GPKG":
                options.layerName = layer_name
            
            # For shapefiles, use base path without extension
            if file_format == "ESRI Shapefile":
                write_path = output_file_path  # Already without extension
            else:
                write_path = output_file_path  # With extension
            
            error_code, error_message = QgsVectorFileWriter.writeAsVectorFormat(
                temp_layer,
                write_path,
                options
            )
            
            if error_code != QgsVectorFileWriter.NoError:
                self.show_error("Error", f"Failed to write line layer file: {error_message}")
                return None
            
            # For shapefiles, construct the full path to load
            if file_format == "ESRI Shapefile":
                load_path = output_file_path + ".shp"
            else:
                load_path = output_file_path
            
            # Load the file-based layer
            file_layer = QgsVectorLayer(load_path, layer_name, "ogr")
            if not file_layer.isValid():
                self.show_error("Error", "Failed to load created line layer file")
                return None, []

            # Determine created feature ids in loaded file layer
            created_fids = []
            try:
                for f in file_layer.getFeatures():
                    created_fids.append(f.id())
            except Exception:
                created_fids = []

            return file_layer, created_fids
            
        except Exception as e:
            print(f"Error creating line layer: {str(e)}")
            return None
    
    def execute(self, context):
        """Execute the create lines from polygon layer action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
            layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
            add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
            include_metadata = bool(self.get_setting('include_metadata', schema['include_metadata']['default']))
            process_selected_only = bool(self.get_setting('process_selected_only', schema['process_selected_only']['default']))
            skip_invalid_geometries = bool(self.get_setting('skip_invalid_geometries', schema['skip_invalid_geometries']['default']))
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
            # Variables for permanent layer creation (only needed if user chooses permanent)
            file_format = None
            layer_dir = None
            actual_source = None
            
            # We'll determine these later if user wants permanent layers
            
            # Generate layer name
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            layer_name = layer_name_template.format(
                layer_name=layer.name().replace(' ', '_').replace('/', '_').replace('\\', '_'),
                timestamp=timestamp
            )
            
            # Ensure unique layer name in project
            project = QgsProject.instance()
            base_layer_name = layer_name
            counter = 1
            while project.mapLayersByName(layer_name):
                layer_name = f"{base_layer_name}_{counter}"
                counter += 1
            
            # Get features to process
            if process_selected_only and layer.selectedFeatureCount() > 0:
                features_to_process = list(layer.selectedFeatures())
                total_features = layer.selectedFeatureCount()
            else:
                features_to_process = list(layer.getFeatures())
                total_features = layer.featureCount()
            
            if total_features == 0:
                self.show_error("Error", "No polygon features found in the layer to process")
                return
            
            # Extract boundaries from all polygons
            line_features = []  # List of (line_geometry, source_feature_id) tuples
            success_count = 0
            error_count = 0
            
            for feature in features_to_process:
                polygon_geometry = feature.geometry()
                
                if not polygon_geometry or polygon_geometry.isEmpty():
                    if skip_invalid_geometries:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature {feature.id()} has empty geometry")
                        return
                
                # Validate that this is a polygon feature
                if polygon_geometry.type() != QgsWkbTypes.PolygonGeometry:
                    if skip_invalid_geometries:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature {feature.id()} is not a polygon feature")
                        return
                
                # Extract boundary line from polygon
                line_geometry = self._extract_boundary_line(polygon_geometry)
                
                if not line_geometry or line_geometry.isEmpty():
                    if skip_invalid_geometries:
                        error_count += 1
                        continue
                    else:
                        self.show_error("Error", f"Failed to extract boundary from feature {feature.id()}")
                        return
                
                # Ensure the geometry is valid
                if not line_geometry.isGeosValid():
                    # Try to fix the geometry
                    line_geometry = line_geometry.makeValid()
                    if line_geometry.isEmpty():
                        if skip_invalid_geometries:
                            error_count += 1
                            continue
                        else:
                            self.show_error("Error", f"Could not create valid line geometry from feature {feature.id()}")
                            return
                
                # Add to list
                line_features.append((line_geometry, feature.id()))
                success_count += 1
            
            if not line_features:
                self.show_error("Error", "No valid boundaries could be extracted from the polygon features")
                return
            
            # Check layer storage type setting
            create_permanent = (layer_storage_type == 'permanent')
            
            # Prepare variables for permanent layer creation
            output_file_path = None
            file_format = None
            
            if create_permanent:
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Lines Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                output_file_path = save_path
                file_format = "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
            
            # Create the line layer
            line_layer, created_fids = self._create_line_layer(
                line_features,
                layer_name,
                layer.crs(),
                include_metadata,
                layer.name(),
                output_file_path,
                file_format,
                create_permanent
            )

            if not line_layer:
                self.show_error("Error", "Failed to create line layer")
                return
            
            # Add to project if requested
            if add_to_project:
                project.addMapLayer(line_layer)

                # Record history for created layer so undo/redo is supported
                try:
                    # Build feature backups (HistoryManager will externalize if payload large)
                    features_backup = []
                    try:
                        for f in line_layer.getFeatures():
                            try:
                                features_backup.append(self.create_feature_backup(f, line_layer))
                            except Exception:
                                features_backup.append({'fid': f.id()})
                    except Exception:
                        features_backup = []

                    # Build field definitions
                    fields_def = []
                    try:
                        for fld in line_layer.fields():
                            try:
                                fields_def.append({'name': fld.name(), 'qmeta_type': fld.type()})
                            except Exception:
                                fields_def.append({'name': fld.name()})
                    except Exception:
                        fields_def = []

                    layer_def = {
                        'layer_name': line_layer.name(),
                        'crs': line_layer.crs().authid() if line_layer.crs().isValid() else '',
                        'geometry_type': QgsWkbTypes.displayString(line_layer.wkbType()),
                        'fields': fields_def,
                        'features': features_backup
                    }

                    hm = get_history_manager()
                    hm.record(
                        action_id=self.action_id,
                        action_name=self.name,
                        description=f"Created {len(features_backup)} line(s) from polygon layer '{layer.name()}'",
                        undo_type=HistoryManager.UNDO_TYPE_CREATE_LAYER,
                        can_undo=True,
                        undo_payload={'layer_definition': layer_def},
                        layers=[self.create_layer_descriptor(line_layer)],
                        features=features_backup,
                        atomic=True,
                        meta={'source_layer_id': layer.id(), 'source_layer_name': layer.name(), 'features_processed': len(line_features)}
                    )
                except Exception:
                    pass
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                # Get layer extent
                layer_extent = line_layer.extent()
                
                # CRS handling - transform if needed
                canvas_crs = canvas.mapSettings().destinationCrs()
                layer_crs = layer.crs()
                
                if canvas_crs != layer_crs:
                    transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                    try:
                        layer_extent = transform.transformBoundingBox(layer_extent)
                    except Exception as e:
                        if show_success_message:
                            self.show_warning("Warning", f"Could not zoom to layer due to CRS transformation: {str(e)}")
                
                # Add buffer to extent for better visualization
                buffer_percentage = 10.0  # 10% buffer
                width = layer_extent.width()
                height = layer_extent.height()
                buffer_x = width * (buffer_percentage / 100.0)
                buffer_y = height * (buffer_percentage / 100.0)
                
                layer_extent.grow(max(buffer_x, buffer_y))
                
                # Zoom to extent
                canvas.setExtent(layer_extent)
                canvas.refresh()
            
            # Show success message
            if show_success_message:
                message = f"Line layer created successfully!\n\n"
                message += f"Source Layer: {layer.name()}\n"
                message += f"Line Layer: {layer_name}\n"
                message += f"Features Processed: {total_features}\n"
                message += f"Lines Created: {success_count}\n"
                
                if error_count > 0:
                    message += f"Skipped (invalid): {error_count}\n"
                
                if create_permanent:
                    message += f"\nLayer type: Permanent (saved to disk)"
                else:
                    message += f"\nLayer type: Temporary (memory only)"
                
                if add_to_project:
                    message += "\n\nLine layer has been added to the project."
                
                self.show_info("Lines Created", message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to create lines from polygon layer: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_lines_from_polygon_layer_action = CreateLinesFromPolygonLayerAction()

