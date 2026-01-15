"""
Show Line Layer Segment Lengths Action for Right-click Utilities and Shortcuts Hub

Displays the length of each segment in all line/polyline features in a layer by creating
labeled points at the midpoint of each segment showing the segment length.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsPointXY,
    QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
import math


class ShowLineLayerSegmentLengthsAction(BaseAction):
    """Action to display segment lengths for all lines in a layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "show_line_layer_segment_lengths"
        self.name = "Show Line Layer Segment Lengths"
        self.category = "Information"
        self.description = "Display the length of each segment in all line/polyline features in a layer. Creates labeled points at the midpoint of each segment showing the segment length in map units. Works with line and multiline layers."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with line layers
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
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
                'default': 'Segment Lengths_{source_layer}',
                'label': 'Layer Name Template',
                'description': 'Template for the segment lengths layer name. Available variables: {source_layer}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created segment lengths layer to the project',
            },
            
            # PROCESSING SETTINGS
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'Only process selected line features (if any are selected)',
            },
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip lines with invalid or empty geometries instead of showing an error',
            },
            
            # DISPLAY SETTINGS
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in length values',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            'label_size': {
                'type': 'float',
                'default': 10.0,
                'label': 'Label Size',
                'description': 'Text size for segment length labels',
                'min': 6.0,
                'max': 24.0,
                'step': 0.5,
            },
            'label_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Label Color',
                'description': 'Text color for segment length labels',
            },
            'label_placement': {
                'type': 'choice',
                'default': 'around',
                'label': 'Label Placement',
                'description': 'Placement of labels relative to segment midpoints',
                'options': ['around', 'over'],
            },
            'include_segment_index': {
                'type': 'bool',
                'default': False,
                'label': 'Include Segment Index',
                'description': 'Include segment index number in labels (e.g., "1: 123.45 m")',
            },
            'include_feature_id': {
                'type': 'bool',
                'default': False,
                'label': 'Include Feature ID',
                'description': 'Include feature ID in labels to identify which line the segment belongs to',
            },
            'include_total_length': {
                'type': 'bool',
                'default': True,
                'label': 'Include Total Length',
                'description': 'Show total length of all lines in information message',
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created segment lengths layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after creating the segment lengths layer',
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
    
    def _calculate_distance(self, point1, point2):
        """
        Calculate Euclidean distance between two points.
        
        Args:
            point1 (QgsPointXY): First point
            point2 (QgsPointXY): Second point
            
        Returns:
            float: Distance between points
        """
        dx = point2.x() - point1.x()
        dy = point2.y() - point1.y()
        return math.sqrt(dx * dx + dy * dy)
    
    def _get_line_segments(self, geometry):
        """
        Extract all segments from a line geometry.
        
        Args:
            geometry (QgsGeometry): Line geometry
            
        Returns:
            list: List of tuples (start_point, end_point) for each segment
        """
        segments = []
        
        if not geometry or geometry.isEmpty():
            return segments
        
        # Handle both single and multi-part geometries
        if geometry.isMultipart():
            # Multi-part geometry (MultiLineString)
            try:
                multi_polyline = geometry.asMultiPolyline()
                for polyline in multi_polyline:
                    if len(polyline) >= 2:
                        # Create segments from consecutive points
                        for i in range(len(polyline) - 1):
                            start_point = QgsPointXY(polyline[i])
                            end_point = QgsPointXY(polyline[i + 1])
                            segments.append((start_point, end_point))
            except:
                # Fallback to geometry collection method
                for part in geometry.asGeometryCollection():
                    if part and part.type() == QgsWkbTypes.LineGeometry:
                        part_segments = self._get_segments_from_line(part)
                        segments.extend(part_segments)
        else:
            # Single-part geometry
            segments = self._get_segments_from_line(geometry)
        
        return segments
    
    def _get_segments_from_line(self, line_geometry):
        """
        Extract segments from a single line geometry.
        
        Args:
            line_geometry (QgsGeometry): Single line geometry
            
        Returns:
            list: List of tuples (start_point, end_point) for each segment
        """
        segments = []
        
        # Get polyline points
        polyline = line_geometry.asPolyline()
        
        if len(polyline) < 2:
            return segments
        
        # Create segments from consecutive points
        for i in range(len(polyline) - 1):
            start_point = QgsPointXY(polyline[i])
            end_point = QgsPointXY(polyline[i + 1])
            segments.append((start_point, end_point))
        
        return segments
    
    def _calculate_segment_midpoint(self, start_point, end_point):
        """
        Calculate midpoint of a line segment.
        
        Args:
            start_point (QgsPointXY): Start point of segment
            end_point (QgsPointXY): End point of segment
            
        Returns:
            QgsPointXY: Midpoint of the segment
        """
        mid_x = (start_point.x() + end_point.x()) / 2.0
        mid_y = (start_point.y() + end_point.y()) / 2.0
        return QgsPointXY(mid_x, mid_y)
    
    def _create_segment_lengths_layer(self, layer_name, crs, include_segment_index, include_feature_id):
        """
        Create a point layer for displaying segment lengths.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            include_segment_index (bool): Whether to include segment index field
            include_feature_id (bool): Whether to include feature ID field
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            # Create memory layer
            layer = QgsVectorLayer(f"Point?crs={crs.authid()}", layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            # Define fields
            fields = QgsFields()
            fields.append(QgsField('segment_length', QVariant.Double))
            
            if include_segment_index:
                fields.append(QgsField('segment_index', QVariant.Int))
            
            if include_feature_id:
                fields.append(QgsField('feature_id', QVariant.Int))
            
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create segment lengths layer: {str(e)}")
            return None
    
    def _enable_labeling(self, layer, length_field_name, decimal_places, label_size, label_color, label_placement, include_segment_index, include_feature_id):
        """
        Enable labeling on the layer to show segment lengths.
        
        Args:
            layer (QgsVectorLayer): Layer to enable labeling on
            length_field_name (str): Name of the length field
            decimal_places (int): Number of decimal places
            label_size (float): Label text size
            label_color (str): Label color (hex string)
            label_placement (str): Label placement option
            include_segment_index (bool): Whether to include segment index in label
            include_feature_id (bool): Whether to include feature ID in label
        """
        try:
            # Create labeling settings
            pal_layer_settings = QgsPalLayerSettings()
            pal_layer_settings.enabled = True
            
            # Create expression to format length
            parts = []
            if include_feature_id:
                parts.append('to_string("feature_id") || ": "')
            if include_segment_index:
                parts.append('to_string("segment_index") || ": "')
            
            parts.append(f'format_number("{length_field_name}", {decimal_places})')
            expression = ' || '.join(parts)
            
            pal_layer_settings.fieldName = expression
            pal_layer_settings.isExpression = True
            
            # Configure text format
            text_format = QgsTextFormat()
            text_format.setSize(label_size)
            
            # Parse color from hex string
            try:
                color = QColor(label_color)
                if not color.isValid():
                    color = QColor(0, 0, 0, 255)  # Default to black
            except:
                color = QColor(0, 0, 0, 255)  # Default to black
            
            text_format.setColor(color)
            pal_layer_settings.setFormat(text_format)
            
            # Set placement
            placement_map = {
                'around': QgsPalLayerSettings.AroundPoint,
                'over': QgsPalLayerSettings.OverPoint,
            }
            pal_layer_settings.placement = placement_map.get(label_placement, QgsPalLayerSettings.AroundPoint)
            
            # Apply labeling settings
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal_layer_settings))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
            
        except Exception as e:
            print(f"Warning: Could not enable labeling: {str(e)}")
            # Labeling is optional, so we don't fail if it doesn't work
    
    def _make_points_invisible(self, layer):
        """
        Make point symbols invisible so only labels are visible.
        
        Args:
            layer (QgsVectorLayer): Point layer to make invisible
        """
        try:
            from qgis.core import QgsMarkerSymbol, QgsSimpleMarkerSymbolLayer, QgsSingleSymbolRenderer
            from qgis.PyQt.QtGui import QColor
            
            # Create transparent marker symbol
            symbol_layer = QgsSimpleMarkerSymbolLayer()
            symbol_layer.setSize(0)  # Size 0 makes it invisible
            symbol_layer.setColor(QColor(255, 255, 255, 0))  # Transparent color
            
            # Create marker symbol
            symbol = QgsMarkerSymbol()
            symbol.changeSymbolLayer(0, symbol_layer)
            
            # Apply symbol to layer
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
        except Exception as e:
            print(f"Warning: Could not make points invisible: {str(e)}")
            # If styling fails, continue - labels will still work
    
    def execute(self, context):
        """Execute the show line layer segment lengths action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
            layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
            add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
            process_selected_only = bool(self.get_setting('process_selected_only', schema['process_selected_only']['default']))
            skip_invalid_geometries = bool(self.get_setting('skip_invalid_geometries', schema['skip_invalid_geometries']['default']))
            decimal_places = int(self.get_setting('decimal_places', schema['decimal_places']['default']))
            label_size = float(self.get_setting('label_size', schema['label_size']['default']))
            label_color = str(self.get_setting('label_color', schema['label_color']['default']))
            label_placement = str(self.get_setting('label_placement', schema['label_placement']['default']))
            include_segment_index = bool(self.get_setting('include_segment_index', schema['include_segment_index']['default']))
            include_feature_id = bool(self.get_setting('include_feature_id', schema['include_feature_id']['default']))
            include_total_length = bool(self.get_setting('include_total_length', schema['include_total_length']['default']))
            zoom_to_layer = bool(self.get_setting('zoom_to_layer', schema['zoom_to_layer']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
            return
        
        # Get the layer from the first detected feature
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Validate that this is a line layer
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.show_error("Error", "This action only works with line layers")
            return
        
        try:
            # Get features to process
            if process_selected_only:
                features = list(layer.selectedFeatures())
                if not features:
                    self.show_warning("No Selection", "No features are selected. Please select features first or disable 'Process Selected Features Only' setting.")
                    return
            else:
                features = list(layer.getFeatures())
            
            if not features:
                self.show_error("Error", "No features found in layer")
                return
            
            # Process all features and collect segment data
            all_segment_data = []
            total_length = 0.0
            features_processed = 0
            features_skipped = 0
            
            for feature in features:
                geometry = feature.geometry()
                
                if not geometry or geometry.isEmpty():
                    if skip_invalid_geometries:
                        features_skipped += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature ID {feature.id()} has invalid or empty geometry")
                        return
                
                # Extract all segments from the line
                segments = self._get_line_segments(geometry)
                
                if not segments:
                    if skip_invalid_geometries:
                        features_skipped += 1
                        continue
                    else:
                        self.show_error("Error", f"Could not extract segments from feature ID {feature.id()}")
                        return
                
                # Calculate segment lengths and midpoints
                for i, (start_point, end_point) in enumerate(segments):
                    # Calculate segment length
                    segment_length = self._calculate_distance(start_point, end_point)
                    total_length += segment_length
                    
                    # Calculate midpoint
                    midpoint = self._calculate_segment_midpoint(start_point, end_point)
                    
                    all_segment_data.append({
                        'midpoint': midpoint,
                        'length': segment_length,
                        'segment_index': i + 1,
                        'feature_id': feature.id()
                    })
                
                features_processed += 1
            
            if not all_segment_data:
                self.show_error("Error", "No valid segments found in any features")
                return
            
            # Generate output layer name
            source_layer_name = layer.name()
            output_layer_name = self._generate_output_layer_name(layer_name_template, source_layer_name)
            
            # Determine output path based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Segment Lengths Layer As",
                    "",
                    "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                output_path = save_path
            else:
                output_path = None  # Temporary layer
            
            # Create segment lengths layer
            segment_layer = self._create_segment_lengths_layer(
                output_layer_name,
                layer.crs(),
                include_segment_index,
                include_feature_id
            )
            
            if not segment_layer:
                self.show_error("Error", "Failed to create segment lengths layer")
                return
            
            # Add segment points to layer
            segment_layer.startEditing()
            
            for seg_data in all_segment_data:
                point_feature = QgsFeature()
                point_geometry = QgsGeometry.fromPointXY(seg_data['midpoint'])
                point_feature.setGeometry(point_geometry)
                
                # Set attributes
                attributes = [round(seg_data['length'], decimal_places)]
                if include_segment_index:
                    attributes.append(seg_data['segment_index'])
                if include_feature_id:
                    attributes.append(seg_data['feature_id'])
                
                point_feature.setAttributes(attributes)
                segment_layer.addFeature(point_feature)
            
            segment_layer.commitChanges()
            
            # Make points invisible (only labels visible)
            self._make_points_invisible(segment_layer)
            
            # Enable labeling
            self._enable_labeling(
                segment_layer,
                'segment_length',
                decimal_places,
                label_size,
                label_color,
                label_placement,
                include_segment_index,
                include_feature_id
            )
            
            # Save to file if permanent
            if layer_storage_type == 'permanent' and output_path:
                from qgis.core import QgsVectorFileWriter
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    segment_layer,
                    output_path,
                    "UTF-8",
                    segment_layer.crs(),
                    "GPKG" if output_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load saved layer
                saved_layer = QgsVectorLayer(output_path, output_layer_name, "ogr")
                if saved_layer.isValid():
                    # Make points invisible
                    self._make_points_invisible(saved_layer)
                    
                    # Copy labeling settings
                    self._enable_labeling(
                        saved_layer,
                        'segment_length',
                        decimal_places,
                        label_size,
                        label_color,
                        label_placement,
                        include_segment_index,
                        include_feature_id
                    )
                    segment_layer = saved_layer
                else:
                    self.show_error("Error", "Failed to load saved layer")
                    return
            
            # Add to project if requested
            if add_to_project:
                QgsProject.instance().addMapLayer(segment_layer)
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                try:
                    # Get layer extent
                    layer_extent = segment_layer.extent()
                    
                    # Transform extent to canvas CRS if needed
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = segment_layer.crs()
                    
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
                
                # Get unit name
                crs = layer.crs()
                unit_name = "units"
                if crs.isGeographic():
                    unit_name = "degrees"
                elif crs.isValid() and crs.mapUnits() != 0:
                    unit_name = crs.mapUnits().name().lower()
                
                message = f"Segment lengths layer '{output_layer_name}' {storage_info} successfully.\n\n"
                message += f"Features processed: {features_processed}\n"
                if features_skipped > 0:
                    message += f"Features skipped: {features_skipped}\n"
                message += f"Total segments: {len(all_segment_data)}\n"
                
                if include_total_length:
                    message += f"Total length: {total_length:.{decimal_places}f} {unit_name}\n"
                
                message += f"Labels displayed at segment midpoints"
                
                self.show_info("Segment Lengths Displayed", message)
        
        except Exception as e:
            self.show_error("Error", f"Failed to show segment lengths: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
show_line_layer_segment_lengths = ShowLineLayerSegmentLengthsAction()

