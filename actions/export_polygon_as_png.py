"""
Export Polygon as PNG Action for Right-click Utilities and Shortcuts Hub

Exports the selected polygon feature as a PNG image showing only the borders.
Ignores any fill styling and focuses on the polygon outline.
"""

from .base_action import BaseAction
import os
from datetime import datetime


class ExportPolygonAsPngAction(BaseAction):
    """
    Action to export the selected polygon feature as a PNG image.
    
    This action creates a PNG image showing only the polygon borders,
    ignoring any fill styling. The image is saved to a user-specified location.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "export_polygon_as_png"
        self.name = "Export Polygon as PNG"
        self.category = "Export"
        self.description = "Export the selected polygon feature as a PNG image showing only the borders. Ignores fill styling and creates a clean outline image."
        self.enabled = True
        
        # Action scoping configuration - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
        
        # Debug output
        print(f"ExportPolygonAsPngAction initialized: {self.action_id}")
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'border_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Border Color',
                'description': 'Color for the polygon border in the exported PNG',
            },
            'border_width': {
                'type': 'int',
                'default': 2,
                'label': 'Border Width (pixels)',
                'description': 'Width of the polygon border in pixels',
                'min': 1,
                'max': 10,
                'step': 1,
            },
            'background_color': {
                'type': 'color',
                'default': '#FFFFFF',
                'label': 'Background Color',
                'description': 'Background color for the exported PNG',
            },
            'image_size': {
                'type': 'int',
                'default': 800,
                'label': 'Image Size (pixels)',
                'description': 'Size of the exported PNG image (square)',
                'min': 200,
                'max': 2000,
                'step': 50,
            },
            'padding_percentage': {
                'type': 'float',
                'default': 10.0,
                'label': 'Padding Percentage',
                'description': 'Percentage of padding around the polygon in the image',
                'min': 0.0,
                'max': 50.0,
                'step': 1.0,
            },
            'save_directory': {
                'type': 'directory_path',
                'default': '~/Downloads',
                'label': 'Save Directory',
                'description': 'Directory where PNG files will be saved',
            },
            'filename_template': {
                'type': 'str',
                'default': 'polygon_{feature_id}_{timestamp}',
                'label': 'Filename Template',
                'description': 'Template for PNG filenames. Available variables: {feature_id}, {timestamp}, {date}, {time}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when PNG is saved successfully',
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
        Execute the export polygon as PNG action using QGIS map rendering.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Import Qt classes inside the method to avoid import issues
        try:
            from qgis.PyQt.QtCore import QSettings, QSize, QRectF, QPointF
            from qgis.PyQt.QtGui import QColor, QPainter, QPen, QBrush, QImage, QPolygonF, QTransform
            from qgis.PyQt.QtWidgets import QFileDialog
            from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, 
                                 QgsCoordinateTransform, QgsRectangle, QgsWkbTypes, QgsMapSettings,
                                 QgsRenderContext, QgsMapRendererCustomPainterJob, QgsSingleSymbolRenderer,
                                 QgsSymbol, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer, QgsMapLayer)
            from qgis.gui import QgsMapCanvas
        except ImportError as e:
            self.show_error("Error", f"Failed to import required modules: {str(e)}")
            return
        
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            border_color = str(self.get_setting('border_color', schema['border_color']['default']))
            border_width = int(self.get_setting('border_width', schema['border_width']['default']))
            background_color = str(self.get_setting('background_color', schema['background_color']['default']))
            image_size = int(self.get_setting('image_size', schema['image_size']['default']))
            padding_percentage = float(self.get_setting('padding_percentage', schema['padding_percentage']['default']))
            save_directory = str(self.get_setting('save_directory', schema['save_directory']['default']))
            filename_template = str(self.get_setting('filename_template', schema['filename_template']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        if not canvas:
            self.show_error("Error", "Canvas not available")
            return
        
        # Get the clicked feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get feature geometry and extent
            geometry = feature.geometry()
            if not geometry:
                self.show_error("Error", "Feature has no geometry")
                return
            
            extent = geometry.boundingBox()
            if extent.isEmpty():
                self.show_error("Error", "Feature has empty extent")
                return
            
            # Add padding to extent
            width = extent.width()
            height = extent.height()
            padding_x = width * (padding_percentage / 100.0)
            padding_y = height * (padding_percentage / 100.0)
            
            padded_extent = QgsRectangle(
                extent.xMinimum() - padding_x,
                extent.yMinimum() - padding_y,
                extent.xMaximum() + padding_x,
                extent.yMaximum() + padding_y
            )
            
            # Create image
            image = QImage(image_size, image_size, QImage.Format_ARGB32)
            image.fill(QColor(background_color))
            
            # Create painter
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Create map settings for rendering
            map_settings = QgsMapSettings()
            map_settings.setOutputSize(QSize(image_size, image_size))
            map_settings.setExtent(padded_extent)
            map_settings.setDestinationCrs(layer.crs())
            map_settings.setBackgroundColor(QColor(background_color))
            
            # Get only visible layers from the layers panel (checked layers)
            canvas_layers = []
            for canvas_layer in canvas.layers():
                if canvas_layer.isValid():
                    # Check if layer is visible in the layers panel
                    layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(canvas_layer.id())
                    if layer_tree_layer and layer_tree_layer.isVisible():
                        canvas_layers.append(canvas_layer)
            
            # Create a temporary layer with only our feature and custom styling
            temp_layer = self.create_temp_layer_with_feature(layer, feature, border_color, border_width)
            
            # Combine canvas layers with our highlighted polygon layer (on top)
            all_layers = canvas_layers + [temp_layer]
            map_settings.setLayers(all_layers)
            
            # Render the map
            job = QgsMapRendererCustomPainterJob(map_settings, painter)
            job.renderSynchronously()
            
            painter.end()
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            date = datetime.now().strftime("%Y%m%d")
            time = datetime.now().strftime("%H%M%S")
            
            filename = filename_template.format(
                feature_id=feature.id(),
                timestamp=timestamp,
                date=date,
                time=time
            )
            
            # Ensure filename has .png extension
            if not filename.endswith('.png'):
                filename += '.png'
            
            # Expand tilde in save directory
            if save_directory.startswith('~'):
                save_directory = os.path.expanduser(save_directory)
            
            # Create save directory if it doesn't exist
            os.makedirs(save_directory, exist_ok=True)
            
            # Full file path
            file_path = os.path.join(save_directory, filename)
            
            # Save image
            if image.save(file_path, 'PNG'):
                if show_success_message:
                    self.show_info("Export Successful", 
                        f"Polygon exported as PNG successfully!\n"
                        f"File: {filename}\n"
                        f"Location: {save_directory}\n"
                        f"Size: {image_size}x{image_size} pixels")
                # Record non-undoable history entry so the export appears in history
                try:
                    self.record_informational(
                        description=f"Exported polygon {feature.id()} to PNG: {file_path}",
                        meta={'file_path': file_path, 'feature_id': feature.id(), 'image_size': image_size}
                    )
                except Exception:
                    pass
            else:
                self.show_error("Error", "Failed to save PNG file")
            
        except Exception as e:
            self.show_error("Error", f"Failed to export polygon as PNG: {str(e)}")
    
    def create_temp_layer_with_feature(self, original_layer, feature, border_color, border_width):
        """Create a temporary layer with only the selected feature and custom styling."""
        try:
            from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields, QgsField,
                                 QgsSingleSymbolRenderer, QgsSymbol, QgsSimpleFillSymbolLayer,
                                 QgsSimpleLineSymbolLayer, QgsMemoryProviderUtils)
            
            # Create a memory layer with the same geometry type
            geometry_type = original_layer.geometryType()
            temp_layer = QgsMemoryProviderUtils.createMemoryLayer(
                f"temp_polygon_{feature.id()}", 
                original_layer.fields(), 
                geometry_type, 
                original_layer.crs()
            )
            
            # Add the feature to the temp layer
            temp_layer.dataProvider().addFeature(feature)
            temp_layer.updateExtents()
            
            # Create custom symbol for border-only rendering
            symbol = QgsSymbol.defaultSymbol(geometry_type)
            
            # Remove fill (make it transparent)
            if symbol.symbolLayerCount() > 0:
                fill_layer = symbol.symbolLayer(0)
                if hasattr(fill_layer, 'setFillColor'):
                    fill_layer.setFillColor(QColor(0, 0, 0, 0))  # Transparent fill
                if hasattr(fill_layer, 'setStrokeColor'):
                    fill_layer.setStrokeColor(QColor(border_color))
                if hasattr(fill_layer, 'setStrokeWidth'):
                    fill_layer.setStrokeWidth(border_width)
            
            # Apply the symbol to the layer
            renderer = QgsSingleSymbolRenderer(symbol)
            temp_layer.setRenderer(renderer)
            
            return temp_layer
            
        except Exception as e:
            # Fallback: return original layer
            return original_layer
    
    def supports_undo(self):
        """This action is not undoable (export only)."""
        return False

    def get_undo_category(self):
        """Return an undo category for grouping; not used since undo is disabled."""
        return "export"



# REQUIRED: Create global instance for automatic discovery
export_polygon_as_png_action = ExportPolygonAsPngAction()
