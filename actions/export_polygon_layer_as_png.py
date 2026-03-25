"""
Export Polygon Layer as PNG Action for Right-click Utilities and Shortcuts Hub

Exports each polygon feature in a layer as a separate PNG image file.
Creates a dedicated folder and saves all PNG files with descriptive names.
"""

from .base_action import BaseAction


class ExportPolygonLayerAsPngAction(BaseAction):
    """Action to export each polygon feature in a layer as separate PNG files."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "export_polygon_layer_as_png"
        self.name = "Export Layer as PNG Files"
        self.category = "Export"
        self.description = "Export each polygon feature in the layer as a separate PNG image file. Creates a dedicated folder and saves all PNG files with descriptive names. Shows all visible layers as background, with option to temporarily hide the exported layer during export for clean background images."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'save_directory': {
                'type': 'directory_path',
                'default': '~/Downloads',
                'label': 'Save Directory',
                'description': 'Directory where the PNG files will be saved. Use ~ for home directory.',
            },
            'folder_name_template': {
                'type': 'str',
                'default': 'polygon_exports_{layer_name}_{timestamp}',
                'label': 'Folder Name Template',
                'description': 'Template for the export folder name. Available variables: {layer_name}, {timestamp}, {date}, {time}',
            },
            'filename_template': {
                'type': 'str',
                'default': 'polygon_{feature_id}_{timestamp}',
                'label': 'Filename Template',
                'description': 'Template for individual PNG filenames. Available variables: {feature_id}, {timestamp}, {date}, {time}',
            },
            'image_size': {
                'type': 'int',
                'default': 800,
                'label': 'Image Size',
                'description': 'Size of the exported PNG images in pixels (width and height)',
                'min': 200,
                'max': 2000,
                'step': 50,
            },
            'border_color': {
                'type': 'color',
                'default': '#FF0000',
                'label': 'Border Color',
                'description': 'Color for the polygon borders in the exported images',
            },
            'border_width': {
                'type': 'int',
                'default': 3,
                'label': 'Border Width',
                'description': 'Width of the polygon borders in pixels',
                'min': 1,
                'max': 10,
                'step': 1,
            },
            'background_color': {
                'type': 'color',
                'default': '#FFFFFF',
                'label': 'Background Color',
                'description': 'Background color for the exported images',
            },
            'include_canvas_layers': {
                'type': 'bool',
                'default': True,
                'label': 'Include Canvas Layers',
                'description': 'Include visible canvas layers as background in the exported images',
            },
            'show_progress': {
                'type': 'bool',
                'default': True,
                'label': 'Show Progress',
                'description': 'Display progress information during export',
            },
            'auto_open_folder': {
                'type': 'bool',
                'default': False,
                'label': 'Auto-open Folder',
                'description': 'Automatically open the export folder after completion',
            },
            'hide_exported_layer': {
                'type': 'bool',
                'default': False,
                'label': 'Hide Exported Layer',
                'description': 'Temporarily hide the layer being exported during PNG creation. This creates clean background images showing all other visible layers except the exported layer.',
            },
            'show_polygons_in_export': {
                'type': 'bool',
                'default': False,
                'label': 'Show Polygons in Export',
                'description': 'Show the polygon features in the exported PNG images. When disabled (default), only background layers are shown without the polygon outlines.',
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
        """Execute the export polygon layer as PNG action."""
        try:
            # Get settings with proper type conversion
            try:
                schema = self.get_settings_schema()
                save_directory = str(self.get_setting('save_directory', schema['save_directory']['default']))
                folder_name_template = str(self.get_setting('folder_name_template', schema['folder_name_template']['default']))
                filename_template = str(self.get_setting('filename_template', schema['filename_template']['default']))
                image_size = int(self.get_setting('image_size', schema['image_size']['default']))
                border_color = str(self.get_setting('border_color', schema['border_color']['default']))
                border_width = int(self.get_setting('border_width', schema['border_width']['default']))
                background_color = str(self.get_setting('background_color', schema['background_color']['default']))
                include_canvas_layers = bool(self.get_setting('include_canvas_layers', schema['include_canvas_layers']['default']))
                show_progress = bool(self.get_setting('show_progress', schema['show_progress']['default']))
                auto_open_folder = bool(self.get_setting('auto_open_folder', schema['auto_open_folder']['default']))
                hide_exported_layer = bool(self.get_setting('hide_exported_layer', schema['hide_exported_layer']['default']))
                show_polygons_in_export = bool(self.get_setting('show_polygons_in_export', schema['show_polygons_in_export']['default']))
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
                self.show_error("Error", "No canvas found")
                return
            
            # Get the layer from the first detected feature
            detected_feature = detected_features[0]
            layer = detected_feature.layer
            
            if not layer or not layer.isValid():
                self.show_error("Error", "Invalid layer")
                return
            
            # Check if layer has polygon features
            if layer.geometryType() not in [1, 2]:  # 1 = Polygon, 2 = MultiPolygon
                self.show_error("Error", "This action only works with polygon layers")
                return
        
            # Import required modules
            try:
                from qgis.PyQt.QtCore import QSettings, QSize, QRectF, QPointF
                from qgis.PyQt.QtGui import QColor, QPainter, QPen, QBrush, QImage, QPolygonF, QTransform
                from qgis.PyQt.QtWidgets import QFileDialog
                from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                                     QgsCoordinateTransform, QgsRectangle, QgsWkbTypes, QgsMapSettings,
                                     QgsRenderContext, QgsMapRendererCustomPainterJob, QgsSingleSymbolRenderer,
                                     QgsSymbol, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer, QgsMapLayer,
                                     QgsMemoryProviderUtils)
                from qgis.gui import QgsMapCanvas
                import os
                from datetime import datetime
            except ImportError as e:
                self.show_error("Error", f"Failed to import required modules: {str(e)}")
                return
        
            # Get all features from the layer
            features = list(layer.getFeatures())
            if not features:
                self.show_error("Error", "No features found in the layer")
                return
        
            # Create export folder
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = folder_name_template.format(
                layer_name=layer.name().replace(' ', '_').replace('/', '_').replace('\\', '_'),
                timestamp=timestamp,
                date=datetime.now().strftime("%Y%m%d"),
                time=datetime.now().strftime("%H%M%S")
            )
            
            # Expand user directory
            if save_directory.startswith('~'):
                save_directory = os.path.expanduser(save_directory)
            
            export_folder = os.path.join(save_directory, folder_name)
            
            try:
                os.makedirs(export_folder, exist_ok=True)
            except Exception as e:
                self.show_error("Error", f"Failed to create export folder: {str(e)}")
                return
        
            # Handle layer visibility for export
            original_layer_visibility = None
            layer_tree_layer = None
            
            if hide_exported_layer:
                # Find the layer tree node for the exported layer
                layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                if layer_tree_layer:
                    # Store original visibility state
                    original_layer_visibility = layer_tree_layer.isVisible()
                    # Temporarily hide the layer using setItemVisibilityChecked
                    layer_tree_layer.setItemVisibilityChecked(False)
                    # Refresh the canvas to update the view
                    canvas.refresh()
            
            # Get canvas layers for background (if enabled)
            # Always exclude the exported layer to prevent its borders from showing
            canvas_layers = []
            if include_canvas_layers:
                for canvas_layer in canvas.layers():
                    if canvas_layer.isValid():
                        # Exclude the exported layer itself
                        if canvas_layer.id() == layer.id():
                            continue
                        # Check if layer is visible in the layers panel
                        layer_tree_layer_check = QgsProject.instance().layerTreeRoot().findLayer(canvas_layer.id())
                        if layer_tree_layer_check and layer_tree_layer_check.isVisible():
                            canvas_layers.append(canvas_layer)
            
            # Export each feature
            exported_count = 0
            total_features = len(features)
        
            for i, feature in enumerate(features):
                try:
                    # Create filename for this feature
                    feature_filename = filename_template.format(
                        feature_id=feature.id(),
                        timestamp=timestamp,
                        date=datetime.now().strftime("%Y%m%d"),
                        time=datetime.now().strftime("%H%M%S")
                    ) + ".png"
                    
                    file_path = os.path.join(export_folder, feature_filename)
                    
                    # Get feature geometry and extent
                    geometry = feature.geometry()
                    if not geometry or geometry.isEmpty():
                        continue
                    
                    # Get feature extent with padding
                    extent = geometry.boundingBox()
                    padding = max(extent.width(), extent.height()) * 0.1
                    padded_extent = QgsRectangle(
                        extent.xMinimum() - padding,
                        extent.yMinimum() - padding,
                        extent.xMaximum() + padding,
                        extent.yMaximum() + padding
                    )
                    
                    # Create image and painter
                    image = QImage(image_size, image_size, QImage.Format_ARGB32)
                    image.fill(QColor(background_color))
                    painter = QPainter(image)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # Set up map settings
                    map_settings = QgsMapSettings()
                    map_settings.setOutputSize(QSize(image_size, image_size))
                    map_settings.setExtent(padded_extent)
                    map_settings.setDestinationCrs(layer.crs())
                    map_settings.setBackgroundColor(QColor(background_color))
                    
                    # Combine layers - only add polygon layer if show_polygons_in_export is enabled
                    all_layers = list(canvas_layers)  # Start with background layers
                    
                    if show_polygons_in_export:
                        # Create temporary layer with only this feature
                        temp_layer = self.create_temp_layer_with_feature(layer, feature, border_color, border_width)
                        if temp_layer:
                            all_layers.append(temp_layer)
                    
                    map_settings.setLayers(all_layers)
                    
                    # Render the map
                    job = QgsMapRendererCustomPainterJob(map_settings, painter)
                    job.renderSynchronously()
                    
                    # Save the image
                    if not image.save(file_path):
                        painter.end()
                        continue
                    
                    exported_count += 1
                    painter.end()
                    
                    # Show progress if enabled
                    if show_progress and (i + 1) % 10 == 0:
                        progress = (i + 1) / total_features * 100
                        self.show_info("Export Progress", f"Exported {i + 1}/{total_features} features ({progress:.1f}%)")
                    
                except Exception as e:
                    # Continue with next feature if one fails
                    try:
                        painter.end()
                    except:
                        pass
                    continue
        
            # Restore original layer visibility if it was hidden
            if hide_exported_layer and layer_tree_layer is not None and original_layer_visibility is not None:
                try:
                    layer_tree_layer.setItemVisibilityChecked(original_layer_visibility)
                    canvas.refresh()
                except Exception as e:
                    print(f"Warning: Could not restore layer visibility: {str(e)}")
            
            # Show completion message
            if exported_count > 0:
                message = f"Successfully exported {exported_count} polygon features to:\n{export_folder}"
                if exported_count < total_features:
                    message += f"\n\nNote: {total_features - exported_count} features were skipped due to errors."
                if hide_exported_layer:
                    message += f"\n\nNote: The exported layer was temporarily hidden during export."
                
                self.show_info("Export Complete", message)
                # Record non-undoable history entry so the export appears in history
                try:
                    self.record_informational(
                        description=f"Exported {exported_count}/{total_features} polygons from layer '{layer.name()}' to {export_folder}",
                        meta={
                            'export_folder': export_folder,
                            'exported_count': exported_count,
                            'total_features': total_features,
                            'layer_id': layer.id(),
                            'layer_name': layer.name()
                        }
                    )
                except Exception:
                    pass
                
                # Auto-open folder if enabled
                if auto_open_folder:
                    try:
                        import subprocess
                        import platform
                        if platform.system() == "Windows":
                            os.startfile(export_folder)
                        elif platform.system() == "Darwin":  # macOS
                            subprocess.run(["open", export_folder])
                        else:  # Linux
                            subprocess.run(["xdg-open", export_folder])
                    except Exception:
                        pass  # Ignore errors opening folder
            else:
                self.show_error("Error", "No features were exported successfully")
                
        except Exception as e:
            # Restore original layer visibility if it was hidden (error case)
            if hide_exported_layer and layer_tree_layer is not None and original_layer_visibility is not None:
                try:
                    layer_tree_layer.setItemVisibilityChecked(original_layer_visibility)
                    canvas.refresh()
                except Exception:
                    pass  # Ignore errors restoring visibility in error case
            
            self.show_error("Error", f"Failed to export polygon layer: {str(e)}")
            return

    def supports_undo(self):
        """This export action is not undoable."""
        return False

    def get_undo_category(self):
        """Return undo category; not used because undo is disabled."""
        return "export"
    
    def create_temp_layer_with_feature(self, original_layer, feature, border_color, border_width):
        """
        Create a temporary memory layer with only the specified feature and custom styling.
        
        Args:
            original_layer: The original layer
            feature: The feature to include
            border_color: Color for the border
            border_width: Width of the border
            
        Returns:
            QgsVectorLayer: Temporary layer with the feature
        """
        try:
            from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsMemoryProviderUtils,
                                 QgsSingleSymbolRenderer, QgsSymbol, QgsSimpleFillSymbolLayer,
                                 QgsSimpleLineSymbolLayer, QgsWkbTypes)
            from qgis.PyQt.QtGui import QColor
            
            # Create memory layer using the layer's WKB type (expected by createMemoryLayer)
            wkb_type = original_layer.wkbType()
            temp_layer = QgsMemoryProviderUtils.createMemoryLayer(
                f"temp_polygon_{feature.id()}",
                original_layer.fields(),
                wkb_type,
                original_layer.crs()
            )

            if not temp_layer or not temp_layer.isValid():
                return None

            # Add the feature and update extents so it will render
            temp_layer.dataProvider().addFeature(feature)
            temp_layer.updateExtents()

            # Create custom symbol using geometryType for symbol creation
            geom_type_for_symbol = original_layer.geometryType()
            symbol = QgsSymbol.defaultSymbol(geom_type_for_symbol)
            if symbol.symbolLayerCount() > 0:
                fill_layer = symbol.symbolLayer(0)
                if hasattr(fill_layer, 'setFillColor'):
                    fill_layer.setFillColor(QColor(0, 0, 0, 0))  # Transparent fill
                if hasattr(fill_layer, 'setStrokeColor'):
                    fill_layer.setStrokeColor(QColor(border_color))
                if hasattr(fill_layer, 'setStrokeWidth'):
                    fill_layer.setStrokeWidth(border_width)
            
            # Set renderer
            renderer = QgsSingleSymbolRenderer(symbol)
            temp_layer.setRenderer(renderer)

            return temp_layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create temporary layer: {str(e)}")
            return None


# REQUIRED: Create global instance for automatic discovery
export_polygon_layer_as_png_action = ExportPolygonLayerAsPngAction()

