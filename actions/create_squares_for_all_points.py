"""
Create Squares for All Points Action for Right-click Utilities and Shortcuts Hub

Creates square polygons around all point features in the selected layer with user-configurable side length.
All squares are created in a single separate layer for easy management and visualization.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsFeature, QgsGeometry, QgsPointXY, QgsPolygon, QgsVectorLayer,
    QgsField, QgsFields, QgsProject, QgsCoordinateTransform,
    QgsWkbTypes, QgsFeatureRequest, QgsFeatureIterator, QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant, QDateTime


class CreateSquaresForAllPointsAction(BaseAction):
    """
    Action to create square polygons around all point features in a layer.
    
    This action processes all point features in the selected layer and creates
    square polygons centered on each point with a user-configurable side length.
    All squares are created in a single separate layer for easy management.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_squares_for_all_points"
        self.name = "Create Squares for All Points"
        self.category = "Geometry"
        self.description = "Create square polygons around all point features in the selected layer with configurable side length. All squares are created in a single separate layer for easy management and visualization."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with point layers
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    # Undo support: this action creates a new layer containing created features
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'trivial'
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # SQUARE SETTINGS
            'square_side_length': {
                'type': 'float',
                'default': 100.0,
                'label': 'Square Side Length',
                'description': 'Length of each side of the squares in map units',
                'min': 0.1,
                'max': 10000.0,
                'step': 1.0,
            },
            'square_rotation_angle': {
                'type': 'float',
                'default': 0.0,
                'label': 'Square Rotation Angle',
                'description': 'Rotation angle of the squares in degrees (0 = no rotation)',
                'min': 0.0,
                'max': 360.0,
                'step': 1.0,
            },
            
            # LAYER SETTINGS
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'default': 'Squares_{layer_name}_{timestamp}',
                'label': 'Layer Name Template',
                'description': 'Template for the new layer name. Available variables: {layer_name}, {timestamp}, {feature_count}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add Layer to Project',
                'description': 'Automatically add the created layer to the current QGIS project',
            },
            'zoom_to_squares': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Squares',
                'description': 'Automatically zoom the map to show all created squares',
            },
            
            # PROCESSING SETTINGS
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'Create squares only for selected features in the layer (if any are selected)',
            },
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip features with invalid or empty geometries',
            },
            'show_progress_dialog': {
                'type': 'bool',
                'default': True,
                'label': 'Show Progress Dialog',
                'description': 'Display progress dialog during processing of large layers',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_creation': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Creation',
                'description': 'Show confirmation dialog before creating squares',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when squares are created successfully',
            },
            
            # STYLING SETTINGS
            'outline_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Outline Color',
                'description': 'Color of the square outlines (borders)',
            },
            'outline_width': {
                'type': 'float',
                'default': 1.0,
                'label': 'Outline Width',
                'description': 'Width of the square outlines in millimeters',
                'min': 0.1,
                'max': 10.0,
                'step': 0.1,
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
    
    def create_square_geometry(self, center_point, side_length, rotation_angle=0.0):
        """
        Create a square geometry centered on the given point.
        
        Args:
            center_point (QgsPointXY): Center point of the square
            side_length (float): Length of each side
            rotation_angle (float): Rotation angle in degrees
            
        Returns:
            QgsGeometry: Square polygon geometry
        """
        # Calculate half side length
        half_side = side_length / 2.0
        
        # Create square vertices (counter-clockwise)
        vertices = [
            QgsPointXY(center_point.x() - half_side, center_point.y() - half_side),  # Bottom-left
            QgsPointXY(center_point.x() + half_side, center_point.y() - half_side),  # Bottom-right
            QgsPointXY(center_point.x() + half_side, center_point.y() + half_side),  # Top-right
            QgsPointXY(center_point.x() - half_side, center_point.y() + half_side),  # Top-left
            QgsPointXY(center_point.x() - half_side, center_point.y() - half_side),  # Close polygon
        ]
        
        # Create polygon geometry using fromPolygonXY
        geometry = QgsGeometry.fromPolygonXY([vertices])
        
        # Apply rotation if needed
        if rotation_angle != 0.0:
            geometry.rotate(rotation_angle, center_point)
        
        return geometry
    
    def create_squares_layer(self, layer_name, source_layer_crs, feature_count):
        """
        Create a new vector layer for storing square geometries.
        
        Args:
            layer_name (str): Name for the new layer
            source_layer_crs: CRS of the source layer
            feature_count (int): Number of features that will be processed
            
        Returns:
            QgsVectorLayer: New layer for storing squares
        """
        # Create memory layer
        layer = QgsVectorLayer("Polygon?crs=" + source_layer_crs.authid(), layer_name, "memory")
        
        # Add fields
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("source_feature_id", QVariant.Int))
        fields.append(QgsField("side_length", QVariant.Double))
        fields.append(QgsField("created_from", QVariant.String))
        fields.append(QgsField("created_at", QVariant.String))
        
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        
        # Apply styling - outline only, no fill
        self.apply_squares_styling(layer)
        
        return layer
    
    def apply_squares_styling(self, layer):
        """
        Apply styling to the squares layer - outline only, no fill.
        
        Args:
            layer (QgsVectorLayer): Layer to style
        """
        try:
            from qgis.core import QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer
            from qgis.PyQt.QtCore import Qt
            from qgis.PyQt.QtGui import QColor
            
            # Get styling settings
            outline_color_hex = str(self.get_setting('outline_color', '#000000'))
            outline_width = float(self.get_setting('outline_width', 1.0))
            
            # Convert hex color to QColor
            if outline_color_hex.startswith('#'):
                outline_color_hex = outline_color_hex[1:]  # Remove #
            outline_color = QColor(int(outline_color_hex[0:2], 16), 
                                 int(outline_color_hex[2:4], 16), 
                                 int(outline_color_hex[4:6], 16))
            
            # Create symbol layer for outline only
            symbol_layer = QgsSimpleFillSymbolLayer()
            symbol_layer.setStrokeColor(outline_color)  # Customizable outline color
            symbol_layer.setStrokeWidth(outline_width)  # Customizable line width
            symbol_layer.setStrokeStyle(Qt.SolidLine)
            symbol_layer.setFillColor(QColor(255, 255, 255, 0))  # Transparent fill (alpha = 0)
            
            # Apply the symbol to the layer
            renderer = layer.renderer()
            if renderer:
                symbol = renderer.symbol()
                if symbol:
                    symbol.changeSymbolLayer(0, symbol_layer)
                    layer.triggerRepaint()
                    
        except Exception as e:
            # If styling fails, continue without it
            print(f"Warning: Could not apply styling to squares layer: {str(e)}")
            pass
    
    def process_features(self, source_layer, square_side_length, square_rotation_angle, 
                        process_selected_only, skip_invalid_geometries, show_progress_dialog):
        """
        Process all point features in the source layer and create squares.
        
        Args:
            source_layer (QgsVectorLayer): Source layer containing point features
            square_side_length (float): Side length for squares
            square_rotation_angle (float): Rotation angle for squares
            process_selected_only (bool): Whether to process only selected features
            skip_invalid_geometries (bool): Whether to skip invalid geometries
            show_progress_dialog (bool): Whether to show progress dialog
            
        Returns:
            tuple: (success_count, error_count, square_features)
        """
        # Get features to process
        if process_selected_only and source_layer.selectedFeatureCount() > 0:
            features = source_layer.selectedFeatures()
            total_features = source_layer.selectedFeatureCount()
        else:
            features = source_layer.getFeatures()
            total_features = source_layer.featureCount()
        
        square_features = []
        success_count = 0
        error_count = 0
        
        # Show progress dialog if requested and processing many features
        progress_dialog = None
        if show_progress_dialog and total_features > 10:
            from qgis.PyQt.QtWidgets import QProgressDialog
            progress_dialog = QProgressDialog(
                f"Creating squares for {total_features} features...",
                "Cancel", 0, total_features
            )
            progress_dialog.setWindowModality(2)  # ApplicationModal
            progress_dialog.show()
        
        try:
            for i, feature in enumerate(features):
                # Update progress
                if progress_dialog:
                    progress_dialog.setValue(i)
                    if progress_dialog.wasCanceled():
                        break
                
                try:
                    # Get feature geometry
                    geometry = feature.geometry()
                    if not geometry or not geometry.isGeosValid():
                        if skip_invalid_geometries:
                            error_count += 1
                            continue
                        else:
                            raise Exception(f"Invalid geometry for feature ID {feature.id()}")
                    
                    # Validate that this is a point feature
                    if geometry.type() != QgsWkbTypes.PointGeometry:
                        if skip_invalid_geometries:
                            error_count += 1
                            continue
                        else:
                            raise Exception(f"Feature ID {feature.id()} is not a point feature")
                    
                    # Get the center point
                    center_point = geometry.asPoint()
                    
                    # Create square geometry
                    square_geometry = self.create_square_geometry(center_point, square_side_length, square_rotation_angle)
                    
                    # Create square feature
                    square_feature = QgsFeature()
                    square_feature.setGeometry(square_geometry)
                    square_feature.setAttributes([
                        success_count + 1,  # id
                        feature.id(),  # source_feature_id
                        square_side_length,  # side_length
                        f"Point Feature ID {feature.id()}",  # created_from
                        QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")  # created_at
                    ])
                    
                    square_features.append(square_feature)
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    print(f"Error processing feature ID {feature.id()}: {str(e)}")
                    continue
        
        finally:
            if progress_dialog:
                progress_dialog.close()
        
        return success_count, error_count, square_features
    
    def execute(self, context):
        """
        Execute the create squares for all points action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            square_side_length = float(self.get_setting('square_side_length', 100.0))
            square_rotation_angle = float(self.get_setting('square_rotation_angle', 0.0))
            layer_name_template = str(self.get_setting('layer_name_template', 'Squares_{layer_name}_{timestamp}'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_squares = bool(self.get_setting('zoom_to_squares', True))
            process_selected_only = bool(self.get_setting('process_selected_only', False))
            skip_invalid_geometries = bool(self.get_setting('skip_invalid_geometries', True))
            show_progress_dialog = bool(self.get_setting('show_progress_dialog', True))
            confirm_creation = bool(self.get_setting('confirm_creation', True))
            show_success_message = bool(self.get_setting('show_success_message', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
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
        
        # Count features to process
        if process_selected_only and layer.selectedFeatureCount() > 0:
            feature_count = layer.selectedFeatureCount()
            process_text = f"{feature_count} selected features"
        else:
            feature_count = layer.featureCount()
            process_text = f"all {feature_count} features"
        
        # Show confirmation if requested
        if confirm_creation:
            if not self.confirm_action(
                "Create Squares for All Points",
                f"Create squares with side length {square_side_length} units around {process_text} in layer '{layer.name()}'?\n\n"
                f"This will create {feature_count} square polygons in a new layer."
            ):
                return
        
        try:
            # Process all features
            success_count, error_count, square_features = self.process_features(
                layer, square_side_length, square_rotation_angle,
                process_selected_only, skip_invalid_geometries, show_progress_dialog
            )
            
            if success_count == 0:
                self.show_error("Error", "No valid point features found to process")
                return
            
            # Generate layer name
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            layer_name = layer_name_template.format(
                layer_name=layer.name(),
                timestamp=timestamp,
                feature_count=success_count
            )
            
            # Create the squares layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Squares Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer = self.create_squares_layer(layer_name, layer.crs(), success_count)
                
                # Add features to temporary layer
                temp_layer.dataProvider().addFeatures(square_features)
                temp_layer.updateExtents()
                
                # Save temporary layer to file
                from qgis.core import QgsVectorFileWriter
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    temp_layer, save_path, "UTF-8", temp_layer.crs(), "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer to file: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load the saved layer
                squares_layer = QgsVectorLayer(save_path, layer_name, "ogr")
                if not squares_layer.isValid():
                    self.show_error("Error", "Failed to load saved layer")
                    return
            else:
                # Create temporary in-memory layer
                squares_layer = self.create_squares_layer(layer_name, layer.crs(), success_count)
                
                # Add features to layer
                squares_layer.dataProvider().addFeatures(square_features)
                squares_layer.updateExtents()
            
            # Add to project if requested
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(squares_layer)
            
            # Zoom to squares if requested
            if zoom_to_squares and canvas:
                # Get squares extent
                squares_extent = squares_layer.extent()
                
                # CRS handling - transform if needed
                canvas_crs = canvas.mapSettings().destinationCrs()
                layer_crs = layer.crs()
                
                if canvas_crs != layer_crs:
                    transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                    try:
                        squares_extent = transform.transformBoundingBox(squares_extent)
                    except Exception as e:
                        if show_success_message:
                            self.show_warning("Warning", f"Could not zoom to squares due to CRS transformation: {str(e)}")
                
                # Add buffer to extent for better visualization
                buffer_percentage = 10.0  # 10% buffer
                width = squares_extent.width()
                height = squares_extent.height()
                buffer_x = width * (buffer_percentage / 100.0)
                buffer_y = height * (buffer_percentage / 100.0)
                
                squares_extent.grow(max(buffer_x, buffer_y))
                
                # Zoom to extent
                canvas.setExtent(squares_extent)
                canvas.refresh()
            
            # Show success message
            if show_success_message:
                message = f"Squares created successfully!\n\n"
                message += f"Source Layer: {layer.name()}\n"
                message += f"Squares Layer: {layer_name}\n"
                message += f"Features Processed: {success_count}\n"
                if error_count > 0:
                    message += f"Errors/Skipped: {error_count}\n"
                message += f"Side Length: {square_side_length} units\n"
                if square_rotation_angle != 0.0:
                    message += f"Rotation: {square_rotation_angle}°\n"
                message += f"Processing Mode: {process_text}"
                
                self.show_info("Squares Created", message)

            # Record history entry (undoable): capture layer descriptor and feature backups
            try:
                # collect created features from the squares layer
                created_features = []
                for f in squares_layer.getFeatures():
                    created_features.append(f)

                layer_desc = self.create_layer_descriptor(squares_layer)
                features_backup = [self.create_feature_backup(f, squares_layer) for f in created_features]

                # Build a simple layer definition for redo/restore
                layer_definition = {
                    'layer_name': squares_layer.name(),
                    'crs': squares_layer.crs().authid() if squares_layer.crs().isValid() else '',
                    'geometry_type': QgsWkbTypes.displayString(squares_layer.wkbType()) if hasattr(squares_layer, 'wkbType') else '',
                    'fields': [
                        {'name': fld.name(), 'qmeta_type': fld.type()} for fld in squares_layer.fields()
                    ],
                    'features': features_backup
                }

                self.record_to_history(
                    description=f"Created {len(created_features)} square(s) in layer '{squares_layer.name()}'",
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload={'layer_definition': layer_definition},
                    layers=[layer_desc],
                    features=features_backup,
                    meta={'layer_was_created': True, 'source_layer_id': layer.id(), 'feature_count': len(created_features)}
                )
            except Exception as e:
                print(f"Warning: Failed to record history for create_squares_for_all_points: {e}")
            
        except Exception as e:
            self.show_error("Error", f"Failed to create squares: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_squares_for_all_points = CreateSquaresForAllPointsAction()
