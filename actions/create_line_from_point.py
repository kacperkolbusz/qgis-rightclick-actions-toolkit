"""
Create Line From Point Action for Right-click Utilities and Shortcuts Hub

Creates a line starting from the selected point feature with user-specified length and direction.
The line is created as a separate layer for easy management and visualization.
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager, HistoryManager
from qgis.core import (
    QgsFeature, QgsGeometry, QgsPointXY, QgsLineString, QgsVectorLayer,
    QgsField, QgsFields, QgsProject, QgsCoordinateTransform,
    QgsWkbTypes, QgsFeatureRequest, QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant, QDateTime
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFormLayout, QDoubleSpinBox
import math


class LineInputDialog(QDialog):
    """Dialog for user input of line length and direction."""
    
    def __init__(self, parent=None, default_length=100.0, default_direction=0.0):
        super().__init__(parent)
        self.setWindowTitle("Create Line From Point")
        self.setModal(True)
        self.resize(300, 150)
        
        # Create layout
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Length input
        self.length_spinbox = QDoubleSpinBox()
        self.length_spinbox.setRange(0.1, 10000.0)
        self.length_spinbox.setValue(default_length)
        self.length_spinbox.setSuffix(" units")
        self.length_spinbox.setDecimals(2)
        form_layout.addRow("Line Length:", self.length_spinbox)
        
        # Direction input
        self.direction_spinbox = QDoubleSpinBox()
        self.direction_spinbox.setRange(0.0, 360.0)
        self.direction_spinbox.setValue(default_direction)
        self.direction_spinbox.setSuffix("°")
        self.direction_spinbox.setDecimals(1)
        form_layout.addRow("Direction:", self.direction_spinbox)
        
        # Direction help label
        direction_help = QLabel("0° = North, 90° = East, 180° = South, 270° = West")
        direction_help.setStyleSheet("color: gray; font-size: 10px;")
        form_layout.addRow("", direction_help)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Create Line")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to length input
        self.length_spinbox.setFocus()
    
    def get_values(self):
        """Get the input values."""
        return self.length_spinbox.value(), self.direction_spinbox.value()


class CreateLineFromPointAction(BaseAction):
    """
    Action to create a line starting from the selected point feature.
    
    This action takes a point feature and creates a line starting from that point
    with a user-specified length and direction. The line is created as a separate layer
    for easy management and visualization.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_line_from_point"
        self.name = "Create Line From Point"
        self.category = "Geometry"
        self.description = "Create a line starting from the selected point feature with configurable length and direction. Creates a separate layer containing only the generated line for easy management."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with points
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # DEFAULT VALUES (used as defaults in input dialog)
            'default_line_length': {
                'type': 'float',
                'default': 100.0,
                'label': 'Default Line Length',
                'description': 'Default length value shown in the input dialog',
                'min': 0.1,
                'max': 10000.0,
                'step': 1.0,
            },
            'default_line_direction': {
                'type': 'float',
                'default': 0.0,
                'label': 'Default Line Direction',
                'description': 'Default direction value shown in the input dialog',
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
                'default': 'Line_{feature_id}_{layer_name}',
                'label': 'Layer Name Template',
                'description': 'Template for the new layer name. Available variables: {feature_id}, {layer_name}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add Layer to Project',
                'description': 'Automatically add the created layer to the current QGIS project',
            },
            'zoom_to_line': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Line',
                'description': 'Automatically zoom the map to show the created line',
            },
            
            # BEHAVIOR SETTINGS
            'confirm_creation': {
                'type': 'bool',
                'default': False,
                'label': 'Confirm Before Creation',
                'description': 'Show confirmation dialog before creating the line',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when the line is created successfully',
            },
            
            # STYLING SETTINGS
            'line_color': {
                'type': 'color',
                'default': '#FF0000',
                'label': 'Line Color',
                'description': 'Color of the line',
            },
            'line_width': {
                'type': 'float',
                'default': 2.0,
                'label': 'Line Width',
                'description': 'Width of the line in millimeters',
                'min': 0.1,
                'max': 10.0,
                'step': 0.1,
            },
            'line_style': {
                'type': 'choice',
                'default': 'Solid',
                'label': 'Line Style',
                'description': 'Style of the line',
                'options': ['Solid', 'Dash', 'Dot', 'Dash Dot', 'Dash Dot Dot'],
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
    
    def create_line_geometry(self, start_point, length, direction_degrees):
        """
        Create a line geometry starting from the given point.
        
        Args:
            start_point (QgsPointXY): Starting point of the line
            length (float): Length of the line
            direction_degrees (float): Direction in degrees (0 = East, 90 = North, etc.)
            
        Returns:
            QgsGeometry: Line geometry
        """
        # Convert direction from degrees to radians
        # Note: QGIS uses mathematical convention (0° = East, counter-clockwise)
        # but we'll use geographic convention (0° = North, clockwise) for user-friendliness
        direction_rad = math.radians(direction_degrees)
        
        # Calculate end point coordinates
        # Using geographic convention: 0° = North, 90° = East, 180° = South, 270° = West
        delta_x = length * math.sin(direction_rad)
        delta_y = length * math.cos(direction_rad)
        
        end_x = start_point.x() + delta_x
        end_y = start_point.y() + delta_y
        end_point = QgsPointXY(end_x, end_y)
        
        # Create line geometry
        line_geometry = QgsGeometry.fromPolylineXY([start_point, end_point])
        
        return line_geometry
    
    def create_line_layer(self, geometry, layer_name, source_layer_crs, line_length, line_direction):
        """
        Create a new vector layer containing the line geometry.
        
        Args:
            geometry (QgsGeometry): Line geometry to add
            layer_name (str): Name for the new layer
            source_layer_crs: CRS of the source layer
            line_length (float): Length of the line
            line_direction (float): Direction of the line
            
        Returns:
            QgsVectorLayer: New layer containing the line
        """
        # Create memory layer
        layer = QgsVectorLayer("LineString?crs=" + source_layer_crs.authid(), layer_name, "memory")
        
        # Add fields
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("length", QVariant.Double))
        fields.append(QgsField("direction", QVariant.Double))
        fields.append(QgsField("created_from", QVariant.String))
        fields.append(QgsField("created_at", QVariant.String))
        
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        
        # Create feature
        feature = QgsFeature()
        feature.setGeometry(geometry)
        feature.setAttributes([
            1,  # id
            line_length,  # length
            line_direction,  # direction
            "Point Feature",  # created_from
            QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")  # created_at
        ])
        
        # Add feature to layer
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()

        # Try to determine the created feature id (take first feature)
        created_fid = None
        try:
            for f in layer.getFeatures():
                created_fid = f.id()
                break
        except Exception:
            created_fid = None

        # Apply styling
        self.apply_line_styling(layer)

        return layer, created_fid
    
    def apply_line_styling(self, layer):
        """
        Apply styling to the line layer.
        
        Args:
            layer (QgsVectorLayer): Layer to style
        """
        try:
            from qgis.core import QgsSimpleLineSymbolLayer
            from qgis.PyQt.QtCore import Qt
            from qgis.PyQt.QtGui import QColor
            
            # Get styling settings
            line_color_hex = str(self.get_setting('line_color', '#FF0000'))
            line_width = float(self.get_setting('line_width', 2.0))
            line_style_name = str(self.get_setting('line_style', 'Solid'))
            
            # Convert hex color to QColor
            if line_color_hex.startswith('#'):
                line_color_hex = line_color_hex[1:]  # Remove #
            line_color = QColor(int(line_color_hex[0:2], 16), 
                              int(line_color_hex[2:4], 16), 
                              int(line_color_hex[4:6], 16))
            
            # Map style names to Qt pen styles
            style_map = {
                'Solid': Qt.SolidLine,
                'Dash': Qt.DashLine,
                'Dot': Qt.DotLine,
                'Dash Dot': Qt.DashDotLine,
                'Dash Dot Dot': Qt.DashDotDotLine,
            }
            line_style = style_map.get(line_style_name, Qt.SolidLine)
            
            # Create symbol layer
            symbol_layer = QgsSimpleLineSymbolLayer()
            symbol_layer.setColor(line_color)
            symbol_layer.setWidth(line_width)
            symbol_layer.setPenStyle(line_style)
            
            # Apply the symbol to the layer
            renderer = layer.renderer()
            if renderer:
                symbol = renderer.symbol()
                if symbol:
                    symbol.changeSymbolLayer(0, symbol_layer)
                    layer.triggerRepaint()
                    
        except Exception as e:
            # If styling fails, continue without it
            print(f"Warning: Could not apply styling to line layer: {str(e)}")
            pass
    
    def execute(self, context):
        """
        Execute the create line from point action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            default_length = float(self.get_setting('default_line_length', 100.0))
            default_direction = float(self.get_setting('default_line_direction', 0.0))
            layer_name_template = str(self.get_setting('layer_name_template', 'Line_{feature_id}_{layer_name}'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_line = bool(self.get_setting('zoom_to_line', True))
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
        
        # Get the starting point
        start_point = geometry.asPoint()
        
        # Show input dialog to get length and direction from user
        dialog = LineInputDialog(None, default_length, default_direction)
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Get the user input values
        line_length, line_direction = dialog.get_values()
        
        try:
            # Create line geometry
            line_geometry = self.create_line_geometry(start_point, line_length, line_direction)
            
            # Generate layer name
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            layer_name = layer_name_template.format(
                feature_id=feature.id(),
                layer_name=layer.name(),
                timestamp=timestamp
            )
            
            # Create the line layer based on storage type
            created_fid = None
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Line Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Create temporary layer first
                temp_layer, temp_fid = self.create_line_layer(line_geometry, layer_name, layer.crs(), line_length, line_direction)
                
                # Save temporary layer to file
                from qgis.core import QgsVectorFileWriter
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    temp_layer, save_path, "UTF-8", temp_layer.crs(), "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer to file: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load the saved layer
                line_layer = QgsVectorLayer(save_path, layer_name, "ogr")
                if not line_layer.isValid():
                    self.show_error("Error", "Failed to load saved layer")
                    return
                # determine created feature id from saved layer (if possible)
                try:
                    for f in line_layer.getFeatures():
                        created_fid = f.id()
                        break
                except Exception:
                    created_fid = None
            else:
                # Create temporary in-memory layer
                line_layer, created_fid = self.create_line_layer(line_geometry, layer_name, layer.crs(), line_length, line_direction)
            
            # Add to project if requested
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(line_layer)

            # Record history: this action creates a new layer containing the generated line
            try:
                if created_fid is not None:
                    # Get the created feature for full backup
                    from qgis.core import QgsFeatureRequest
                    created_feature = None
                    for f in line_layer.getFeatures(QgsFeatureRequest().setFilterFid(created_fid)):
                        created_feature = f
                        break
                else:
                    created_feature = None

                # Create feature backup
                feature_backup = self.create_feature_backup(created_feature, line_layer) if created_feature else ({'fid': created_fid} if created_fid is not None else None)

                # Layer definition to allow redo of the layer (structure + backups)
                layer_def = {
                    'layer_name': line_layer.name(),
                    'crs': line_layer.crs().authid() if line_layer.crs().isValid() else '',
                    'geometry_type': QgsWkbTypes.displayString(line_layer.wkbType()),
                    'fields': [],
                    'features': [feature_backup] if feature_backup else []
                }
                for fld in line_layer.fields():
                    try:
                        layer_def['fields'].append({'name': fld.name(), 'qmeta_type': fld.type()})
                    except Exception:
                        layer_def['fields'].append({'name': fld.name()})

                hm = get_history_manager()
                hm.record(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Created line from point {feature.id()} in new layer '{line_layer.name()}'",
                    undo_type=HistoryManager.UNDO_TYPE_CREATE_LAYER,
                    can_undo=True,
                    undo_payload={'layer_definition': layer_def},
                    layers=[self.create_layer_descriptor(line_layer)],
                    features=[feature_backup] if feature_backup else [],
                    atomic=True,
                    meta={'layer_was_created': True, 'source_feature_id': feature.id(), 'source_layer_id': layer.id()}
                )
            except Exception:
                pass
            
            # Zoom to line if requested
            if zoom_to_line and canvas:
                # Get line extent
                line_extent = line_geometry.boundingBox()
                
                # CRS handling - transform if needed
                canvas_crs = canvas.mapSettings().destinationCrs()
                layer_crs = layer.crs()
                
                if canvas_crs != layer_crs:
                    transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                    try:
                        line_extent = transform.transformBoundingBox(line_extent)
                    except Exception as e:
                        if show_success_message:
                            self.show_warning("Warning", f"Could not zoom to line due to CRS transformation: {str(e)}")
                
                # Add buffer to extent for better visualization
                buffer_percentage = 20.0  # 20% buffer
                width = line_extent.width()
                height = line_extent.height()
                buffer_x = width * (buffer_percentage / 100.0)
                buffer_y = height * (buffer_percentage / 100.0)
                
                line_extent.grow(max(buffer_x, buffer_y))
                
                # Zoom to extent
                canvas.setExtent(line_extent)
                canvas.refresh()
            
            # Show success message
            if show_success_message:
                # Calculate end point for display
                direction_rad = math.radians(line_direction)
                delta_x = line_length * math.sin(direction_rad)
                delta_y = line_length * math.cos(direction_rad)
                end_x = start_point.x() + delta_x
                end_y = start_point.y() + delta_y
                
                message = f"Line created successfully!\n\n"
                message += f"Feature ID: {feature.id()}\n"
                message += f"Source Layer: {layer.name()}\n"
                message += f"Line Layer: {layer_name}\n"
                message += f"Length: {line_length} units\n"
                message += f"Direction: {line_direction}°\n"
                message += f"Start Point: ({start_point.x():.2f}, {start_point.y():.2f})\n"
                message += f"End Point: ({end_x:.2f}, {end_y:.2f})"
                
                self.show_info("Line Created", message)
            
        except Exception as e:
            self.show_error("Error", f"Failed to create line: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_line_from_point = CreateLineFromPointAction()
