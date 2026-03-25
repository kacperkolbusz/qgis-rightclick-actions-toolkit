"""
Generate Heatmap From Points Action for Right-click Utilities and Shortcuts Hub

Generates a heatmap raster layer from point features using kernel density estimation.
Works with point layers to visualize point density across the map.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsWkbTypes, QgsProject, QgsCoordinateTransform,
    QgsRasterLayer, QgsProcessingContext, QgsProcessingFeedback,
    QgsRasterBandStats
)
from qgis.PyQt.QtWidgets import QFileDialog
import os


class GenerateHeatmapFromPointsAction(BaseAction):
    """Action to generate a heatmap raster from point features."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "generate_heatmap_from_points"
        self.name = "Generate Heatmap From Points"
        self.category = "Analysis"
        self.description = "Generate a heatmap raster layer from point features using kernel density estimation. Areas with many clustered points show warm colors (red/yellow), while areas with sparse or distant points show cool colors (blue/transparent). Visualizes point density across the map with customizable radius, pixel size, and color scheme."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with point layers
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # OUTPUT SETTINGS
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'default': 'Heatmap_{source_layer}',
                'label': 'Layer Name Template',
                'description': 'Template for the heatmap layer name. Available variables: {source_layer}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created heatmap layer to the project',
            },
            
            # HEATMAP SETTINGS
            'auto_calculate_parameters': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-calculate Parameters',
                'description': 'Automatically calculate radius and pixel size based on layer extent. Recommended for proper scaling.',
            },
            'radius': {
                'type': 'float',
                'default': 100.0,
                'label': 'Radius',
                'description': 'Radius of the search circle in map units. Larger values create smoother, more generalized heatmaps. Only used if auto-calculate is disabled.',
                'min': 1.0,
                'max': 100000.0,
                'step': 10.0,
            },
            'pixel_size': {
                'type': 'float',
                'default': 1.0,
                'label': 'Pixel Size',
                'description': 'Size of each pixel in the output raster in map units. Smaller values create higher resolution heatmaps but take longer to process. Only used if auto-calculate is disabled.',
                'min': 0.01,
                'max': 1000.0,
                'step': 0.1,
            },
            'radius_percentage': {
                'type': 'float',
                'default': 5.0,
                'label': 'Radius Percentage',
                'description': 'Radius as percentage of layer extent (when auto-calculate is enabled). Higher values create smoother heatmaps.',
                'min': 0.1,
                'max': 50.0,
                'step': 0.5,
            },
            'pixel_count_target': {
                'type': 'int',
                'default': 500,
                'label': 'Target Pixel Count',
                'description': 'Target number of pixels along the longest dimension (when auto-calculate is enabled). Higher values create higher resolution but slower processing.',
                'min': 100,
                'max': 5000,
                'step': 50,
            },
            'weight_field': {
                'type': 'str',
                'default': '',
                'label': 'Weight Field (Optional)',
                'description': 'Optional numeric field to use as weight for each point. Leave empty to use equal weights for all points.',
            },
            'kernel_shape': {
                'type': 'choice',
                'default': 'Quartic',
                'label': 'Kernel Shape',
                'description': 'Shape of the kernel function used for density estimation',
                'options': ['Quartic', 'Triangular', 'Uniform', 'Triweight', 'Epanechnikov'],
            },
            'decay_ratio': {
                'type': 'float',
                'default': 0.0,
                'label': 'Decay Ratio',
                'description': 'Decay ratio for the kernel function (0.0 = no decay, 1.0 = full decay at radius)',
                'min': 0.0,
                'max': 1.0,
                'step': 0.1,
            },
            'output_value': {
                'type': 'choice',
                'default': 'Raw',
                'label': 'Output Value',
                'description': 'Type of output value to calculate',
                'options': ['Raw', 'Scaled'],
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created heatmap layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after creating the heatmap',
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
    
    def _get_available_numeric_fields(self, layer):
        """
        Get list of available numeric fields from the layer.
        
        Args:
            layer (QgsVectorLayer): Layer to get fields from
            
        Returns:
            list: List of field names
        """
        numeric_fields = []
        for field in layer.fields():
            if field.type() in [2, 4, 6]:  # Integer, Double, Real
                numeric_fields.append(field.name())
        return numeric_fields
    
    def _calculate_smart_parameters(self, layer, radius_percentage, pixel_count_target):
        """
        Calculate appropriate radius and pixel size based on layer extent.
        
        Args:
            layer (QgsVectorLayer): Point layer
            radius_percentage (float): Radius as percentage of extent
            pixel_count_target (int): Target number of pixels along longest dimension
            
        Returns:
            tuple: (radius, pixel_size) in map units
        """
        try:
            # Get layer extent
            layer_extent = layer.extent()
            if layer_extent.isEmpty():
                # Fallback to defaults
                return 100.0, 1.0
            
            # Calculate extent dimensions
            width = layer_extent.width()
            height = layer_extent.height()
            max_dimension = max(width, height)
            min_dimension = min(width, height)
            
            # Calculate radius as percentage of max dimension
            radius = max_dimension * (radius_percentage / 100.0)
            
            # Ensure minimum radius (1% of min dimension or absolute minimum)
            min_radius = max(min_dimension * 0.01, max_dimension * 0.001)
            radius = max(radius, min_radius)
            
            # Calculate pixel size to achieve target pixel count
            pixel_size = max_dimension / pixel_count_target
            
            # Ensure reasonable pixel size (not too small, not too large)
            # Pixel size should be between 0.1% and 10% of max dimension
            min_pixel_size = max_dimension * 0.001
            max_pixel_size = max_dimension * 0.1
            pixel_size = max(min_pixel_size, min(pixel_size, max_pixel_size))
            
            return radius, pixel_size
            
        except Exception as e:
            print(f"Warning: Could not calculate smart parameters: {str(e)}")
            return 100.0, 1.0
    
    def execute(self, context):
        """Execute the generate heatmap action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
            layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
            add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
            auto_calculate = bool(self.get_setting('auto_calculate_parameters', schema['auto_calculate_parameters']['default']))
            radius = float(self.get_setting('radius', schema['radius']['default']))
            pixel_size = float(self.get_setting('pixel_size', schema['pixel_size']['default']))
            radius_percentage = float(self.get_setting('radius_percentage', schema['radius_percentage']['default']))
            pixel_count_target = int(self.get_setting('pixel_count_target', schema['pixel_count_target']['default']))
            weight_field = str(self.get_setting('weight_field', schema['weight_field']['default']))
            kernel_shape = str(self.get_setting('kernel_shape', schema['kernel_shape']['default']))
            decay_ratio = float(self.get_setting('decay_ratio', schema['decay_ratio']['default']))
            output_value = str(self.get_setting('output_value', schema['output_value']['default']))
            zoom_to_layer = bool(self.get_setting('zoom_to_layer', schema['zoom_to_layer']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
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
        
        # Check if layer has any features
        feature_count = layer.featureCount()
        if feature_count == 0:
            self.show_error("Error", "The point layer has no features")
            return
        
        # Calculate radius and pixel size if auto-calculate is enabled
        if auto_calculate:
            calculated_radius, calculated_pixel_size = self._calculate_smart_parameters(
                layer, radius_percentage, pixel_count_target
            )
            radius = calculated_radius
            pixel_size = calculated_pixel_size
        
        # Validate weight field if specified
        weight_field_index = None
        if weight_field:
            field_index = layer.fields().indexFromName(weight_field)
            if field_index == -1:
                self.show_error("Error", f"Weight field '{weight_field}' not found in layer")
                return
            
            # Check if field is numeric
            field = layer.fields().at(field_index)
            if field.type() not in [2, 4, 6]:  # Integer, Double, Real
                self.show_error("Error", f"Weight field '{weight_field}' must be numeric")
                return
            
            weight_field_index = field_index
        
        try:
            # Generate output layer name
            source_layer_name = layer.name()
            output_layer_name = self._generate_output_layer_name(layer_name_template, source_layer_name)
            
            # Determine output path based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Heatmap As",
                    "",
                    "GeoTIFF (*.tif *.tiff);;All Files (*.*)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Ensure .tif extension
                if not save_path.lower().endswith(('.tif', '.tiff')):
                    save_path += '.tif'
                
                output_path = save_path
            else:
                # Temporary layer - use memory
                output_path = 'TEMPORARY_OUTPUT'
            
            # Map kernel shape to numeric value (QGIS algorithm expects enum)
            kernel_map = {
                'Quartic': 0,
                'Triangular': 1,
                'Uniform': 2,
                'Triweight': 3,
                'Epanechnikov': 4
            }
            kernel_value = kernel_map.get(kernel_shape, 0)  # Default to Quartic if unknown
            
            # Get layer extent for proper heatmap generation
            layer_extent = layer.extent()
            if layer_extent.isEmpty():
                self.show_error("Error", "Layer has no valid extent")
                return
            
            # Prepare processing parameters
            # Note: The algorithm will use the layer extent automatically
            processing_params = {
                'INPUT': layer,
                'RADIUS': radius,
                'PIXEL_SIZE': pixel_size,
                'KERNEL': kernel_value,
                'DECAY': decay_ratio,
                'OUTPUT_VALUE': 0 if output_value == 'Raw' else 1,
                'OUTPUT': output_path
            }
            
            # Add weight field if specified
            if weight_field_index is not None:
                processing_params['WEIGHT'] = weight_field_index
            
            # Run heatmap processing algorithm
            from qgis import processing
            
            processing_context = QgsProcessingContext()
            processing_context.setProject(QgsProject.instance())
            feedback = QgsProcessingFeedback()
            
            result = processing.run(
                "qgis:heatmapkerneldensityestimation",
                processing_params,
                context=processing_context,
                feedback=feedback
            )
            
            if not result or 'OUTPUT' not in result:
                self.show_error("Error", "Heatmap algorithm returned no output")
                return
            
            # Load the output raster layer
            output_raster_path = result['OUTPUT']
            raster_layer = QgsRasterLayer(output_raster_path, output_layer_name)
            
            if not raster_layer.isValid():
                self.show_error("Error", "Failed to create valid raster layer")
                return
            
            # Apply default styling (singleband pseudocolor)
            try:
                from qgis.core import QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer
                from qgis.PyQt.QtGui import QColor
                
                # Get actual data range from raster
                provider = raster_layer.dataProvider()
                
                # Calculate statistics if needed
                try:
                    stats = provider.bandStatistics(1, QgsRasterBandStats.All, raster_layer.extent(), 0)
                    min_value = stats.minimumValue if stats.minimumValue is not None else 0.0
                    max_value = stats.maximumValue if stats.maximumValue is not None else 1.0
                except Exception:
                    # If stats calculation fails, use default range
                    min_value = 0.0
                    max_value = 1.0
                
                # Ensure valid range
                if max_value <= min_value:
                    max_value = min_value + 1.0
                
                # Create color ramp: low density (sparse points) = cool colors, high density (clustered points) = warm colors
                # The kernel density algorithm calculates density values where:
                # - Low values = few points or points far apart (sparse areas)
                # - High values = many points close together (clustered areas)
                shader = QgsRasterShader()
                color_ramp = QgsColorRampShader()
                color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
                
                # Define color stops using actual data range
                # Low density (sparse points) -> cool/transparent colors
                color_ramp.setColorRampItem(min_value, QColor(0, 0, 255, 0))  # Transparent blue at min (sparse)
                color_ramp.setColorRampItem(
                    min_value + (max_value - min_value) * 0.25,
                    QColor(0, 255, 255, 200)  # Cyan (low-medium density)
                )
                color_ramp.setColorRampItem(
                    min_value + (max_value - min_value) * 0.5,
                    QColor(0, 255, 0, 200)  # Green (medium density)
                )
                # High density (clustered points) -> warm colors
                color_ramp.setColorRampItem(
                    min_value + (max_value - min_value) * 0.75,
                    QColor(255, 255, 0, 200)  # Yellow (high density)
                )
                color_ramp.setColorRampItem(max_value, QColor(255, 0, 0, 255))  # Red at max (very clustered)
                
                shader.setRasterShaderFunction(color_ramp)
                renderer = QgsSingleBandPseudoColorRenderer(
                    provider,
                    1,  # Band 1
                    shader
                )
                raster_layer.setRenderer(renderer)
                raster_layer.triggerRepaint()
            except Exception as style_error:
                # If styling fails, continue without custom styling
                print(f"Warning: Could not apply custom styling: {str(style_error)}")
            
            # Add to project if requested
            if add_to_project:
                QgsProject.instance().addMapLayer(raster_layer)
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                try:
                    # Get layer extent
                    layer_extent = raster_layer.extent()
                    
                    # Transform extent to canvas CRS if needed
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = raster_layer.crs()
                    
                    if canvas_crs != layer_crs:
                        transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                        try:
                            layer_extent = transform.transformBoundingBox(layer_extent)
                        except Exception as e:
                            print(f"Warning: CRS transformation failed: {str(e)}")
                    
                    canvas.setExtent(layer_extent)
                    canvas.refresh()
                except Exception as zoom_error:
                    print(f"Warning: Could not zoom to layer: {str(zoom_error)}")
            
            # Show success message if requested
            if show_success_message:
                storage_info = "saved to disk" if layer_storage_type == 'permanent' else "created as temporary layer"
                auto_info = " (auto-calculated)" if auto_calculate else ""
                self.show_info(
                    "Heatmap Created",
                    f"Heatmap layer '{output_layer_name}' {storage_info} successfully.\n\n"
                    f"Features processed: {feature_count}\n"
                    f"Radius: {radius:.2f} map units{auto_info}\n"
                    f"Pixel size: {pixel_size:.2f} map units{auto_info}"
                )

            # Record history: creating a new raster layer (allow undo = remove layer)
            try:
                from ..history_manager import get_history_manager
                history_manager = get_history_manager()

                # Build a lightweight layer definition for redo (raster-aware)
                layer_def = {
                    'layer_name': raster_layer.name(),
                    'crs': raster_layer.crs().authid() if raster_layer.crs().isValid() else '',
                    'is_raster': True,
                    'raster_path': output_raster_path,
                    'provider': raster_layer.dataProvider().name() if raster_layer.dataProvider() else '',
                }

                # Build a layer descriptor compatible with HistoryManager expectations
                try:
                    data_source = raster_layer.dataProvider().dataSourceUri() if raster_layer.dataProvider() else raster_layer.source()
                except Exception:
                    try:
                        data_source = raster_layer.source()
                    except Exception:
                        data_source = ''

                layers = [{
                    'layer_id': raster_layer.id(),
                    'layer_name': raster_layer.name(),
                    'data_source': data_source,
                    'is_temporary': (layer_storage_type != 'permanent'),
                    'geometry_type': '',
                    'crs': raster_layer.crs().authid() if raster_layer.crs().isValid() else ''
                }]

                self.record_to_history(
                    description=f"Created heatmap layer '{output_layer_name}'",
                    undo_type='create_layer',
                    can_undo=True,
                    undo_payload={'layer_definitions': [layer_def]},
                    layers=layers,
                    features=[],
                    meta={'radius': radius, 'pixel_size': pixel_size, 'kernel': kernel_value, 'weight_field': weight_field, 'storage': layer_storage_type}
                )
            except Exception:
                # History recording must not break the action; ignore failures
                pass
        
        except Exception as e:
            self.show_error("Error", f"Failed to generate heatmap: {str(e)}")

    def supports_undo(self) -> bool:
        """This action supports undo: created layer can be removed from project."""
        return True

    def get_undo_category(self) -> str:
        """Return undo category for this action (trivial create -> delete)."""
        return 'trivial'


# REQUIRED: Create global instance for automatic discovery
generate_heatmap_from_points = GenerateHeatmapFromPointsAction()



