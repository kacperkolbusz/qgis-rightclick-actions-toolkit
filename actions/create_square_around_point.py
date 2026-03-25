"""
Create Square Around Point Action for Right-click Utilities and Shortcuts Hub

Creates a square polygon around the selected point feature with user-configurable side length.
The square is created as a separate layer for easy management and visualization.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsFeature, QgsGeometry, QgsPointXY, QgsPolygon, QgsVectorLayer,
    QgsField, QgsFields, QgsProject, QgsCoordinateTransform,
    QgsWkbTypes, QgsFeatureRequest, QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant, QDateTime


class CreateSquareAroundPointAction(BaseAction):
    """
    Action to create a square polygon around the selected point feature.
    
    This action takes a point feature and creates a square polygon centered on that point
    with a user-configurable side length. The square is created as a separate layer
    for easy management and visualization.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_square_around_point"
        self.name = "Create Square Around Point"
        self.category = "Geometry"
        self.description = "Create a square polygon around the selected point feature with configurable side length. Creates a separate layer containing only the generated square for easy management."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with points
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    # Undo support: this action creates a new layer, so it supports undo
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
                'description': 'Length of each side of the square in map units',
                'min': 0.1,
                'max': 10000.0,
                'step': 1.0,
            },
            'square_rotation_angle': {
                'type': 'float',
                'default': 0.0,
                'label': 'Square Rotation Angle',
                'description': 'Rotation angle of the square in degrees (0 = no rotation)',
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
                'default': 'Square_{feature_id}_{layer_name}',
                'label': 'Layer Name Template',
                'description': 'Template for the new layer name. Available variables: {feature_id}, {layer_name}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add Layer to Project',
                'description': 'Automatically add the created layer to the current QGIS project',
            },
            'zoom_to_square': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Square',
                'description': 'Automatically zoom the map to show the created square',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_creation': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Creation',
                'description': 'Show confirmation dialog before creating the square',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when the square is created successfully',
            },
            
            # STYLING SETTINGS
            'outline_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Outline Color',
                'description': 'Color of the square outline (border)',
            },
            'outline_width': {
                'type': 'float',
                'default': 1.0,
                'label': 'Outline Width',
                'description': 'Width of the square outline in millimeters',
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
    
    def create_square_layer(self, geometry, layer_name, source_layer_crs):
        """
        Create a new vector layer containing the square geometry.
        
        Args:
            geometry (QgsGeometry): Square geometry to add
            layer_name (str): Name for the new layer
            source_layer_crs: CRS of the source layer
            
        Returns:
            QgsVectorLayer: New layer containing the square
        """
        # Create memory layer
        layer = QgsVectorLayer("Polygon?crs=" + source_layer_crs.authid(), layer_name, "memory")
        
        # Add fields
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("side_length", QVariant.Double))
        fields.append(QgsField("created_from", QVariant.String))
        fields.append(QgsField("created_at", QVariant.String))
        
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        
        # Create feature
        feature = QgsFeature()
        feature.setGeometry(geometry)
        feature.setAttributes([
            1,  # id
            self.get_setting('square_side_length', 100.0),  # side_length
            "Point Feature",  # created_from
            QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")  # created_at
        ])
        
        # Add feature to layer and ensure we can capture the created FID
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        
        # Apply styling - outline only, no fill
        self.apply_square_styling(layer)
        
        return layer
    
    def apply_square_styling(self, layer):
        """
        Apply styling to the square layer - outline only, no fill.
        
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
            print(f"Warning: Could not apply styling to square layer: {str(e)}")
            pass
    
    def execute(self, context):
        """
        Execute the create square around point action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            square_side_length = float(self.get_setting('square_side_length', 100.0))
            square_rotation_angle = float(self.get_setting('square_rotation_angle', 0.0))
            layer_name_template = str(self.get_setting('layer_name_template', 'Square_{feature_id}_{layer_name}'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_square = bool(self.get_setting('zoom_to_square', True))
            confirm_creation = bool(self.get_setting('confirm_creation', False))
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
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Validate that this is a point feature
        geometry = feature.geometry()
        if not geometry or not geometry.isGeosValid():
            self.show_error("Error", "Feature has invalid geometry")
            return
        
        # Get the point coordinates
        if geometry.type() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "This action only works with point features")
            return
        
        # Get the center point
        center_point = geometry.asPoint()
        
        # Show confirmation if requested
        if confirm_creation:
            if not self.confirm_action(
                "Create Square",
                f"Create a square with side length {square_side_length} units around point feature ID {feature.id()}?"
            ):
                return
        
        try:
            # Create square geometry
            square_geometry = self.create_square_geometry(center_point, square_side_length, square_rotation_angle)
            
            # Generate layer name
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            layer_name = layer_name_template.format(
                feature_id=feature.id(),
                layer_name=layer.name(),
                timestamp=timestamp
            )
            
            # Create the square layer based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Square Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer = self.create_square_layer(square_geometry, layer_name, layer.crs())
                
                # Save temporary layer to file
                from qgis.core import QgsVectorFileWriter
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    temp_layer, save_path, "UTF-8", temp_layer.crs(), "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer to file: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load the saved layer
                square_layer = QgsVectorLayer(save_path, layer_name, "ogr")
                if not square_layer.isValid():
                    self.show_error("Error", "Failed to load saved layer")
                    return
            else:
                # Create temporary in-memory layer
                square_layer = self.create_square_layer(square_geometry, layer_name, layer.crs())
            
            # Add to project if requested
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(square_layer)
            
            # Zoom to square if requested
            if zoom_to_square and canvas:
                # Get square extent
                square_extent = square_geometry.boundingBox()
                
                # CRS handling - transform if needed
                canvas_crs = canvas.mapSettings().destinationCrs()
                layer_crs = layer.crs()
                
                if canvas_crs != layer_crs:
                    transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                    try:
                        square_extent = transform.transformBoundingBox(square_extent)
                    except Exception as e:
                        if show_success_message:
                            self.show_warning("Warning", f"Could not zoom to square due to CRS transformation: {str(e)}")
                
                # Add buffer to extent for better visualization
                buffer_percentage = 10.0  # 10% buffer
                width = square_extent.width()
                height = square_extent.height()
                buffer_x = width * (buffer_percentage / 100.0)
                buffer_y = height * (buffer_percentage / 100.0)
                
                square_extent.grow(max(buffer_x, buffer_y))
                
                # Zoom to extent
                canvas.setExtent(square_extent)
                canvas.refresh()
            
            # Show success message
            if show_success_message:
                message = f"Square created successfully!\n\n"
                message += f"Feature ID: {feature.id()}\n"
                message += f"Source Layer: {layer.name()}\n"
                message += f"Square Layer: {layer_name}\n"
                message += f"Side Length: {square_side_length} units\n"
                if square_rotation_angle != 0.0:
                    message += f"Rotation: {square_rotation_angle}°\n"
                message += f"Center: ({center_point.x():.2f}, {center_point.y():.2f})"
                
                self.show_info("Square Created", message)

            # Record history entry (undoable): store layer descriptor and feature backup
            try:
                # Get the created feature (assume single feature layer)
                created_feature = None
                for f in square_layer.getFeatures():
                    created_feature = f
                    break

                layer_desc = self.create_layer_descriptor(square_layer)
                features_backup = []
                if created_feature is not None:
                    features_backup.append(self.create_feature_backup(created_feature, square_layer))

                # Build a simple layer definition suitable for redo/restore
                layer_definition = {
                    'layer_name': square_layer.name(),
                    'crs': square_layer.crs().authid() if square_layer.crs().isValid() else '',
                    # Use displayString so handlers can construct layer URI like 'Polygon'
                    'geometry_type': QgsWkbTypes.displayString(square_layer.wkbType()) if hasattr(square_layer, 'wkbType') else '',
                    'fields': [
                        {'name': fld.name(), 'qmeta_type': fld.type()} for fld in square_layer.fields()
                    ],
                    'features': features_backup
                }

                # Record using BaseAction helper
                self.record_to_history(
                    description=f"Created square layer '{square_layer.name()}'",
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload={'layer_definition': layer_definition},
                    layers=[layer_desc],
                    features=features_backup,
                    meta={'layer_was_created': True}
                )
            except Exception as e:
                # History recording must not break the main action
                print(f"Warning: Failed to record history for create_square_around_point: {e}")
            
        except Exception as e:
            self.show_error("Error", f"Failed to create square: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_square_around_point = CreateSquareAroundPointAction()
