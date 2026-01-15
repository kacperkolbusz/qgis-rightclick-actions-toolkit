"""
Show Polygon Layer Areas Action for Right-click Utilities and Shortcuts Hub

Displays the area of all polygon features in a layer by creating labeled points
at the centroid of each polygon showing the area value.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsPointXY,
    QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling,
    QgsCoordinateReferenceSystem, QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
import math


class ShowPolygonLayerAreasAction(BaseAction):
    """Action to display areas for all polygons in a layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "show_polygon_layer_areas"
        self.name = "Show Polygon Layer Areas"
        self.category = "Information"
        self.description = "Display the area of all polygon features in a layer. Creates labeled points at the centroid of each polygon showing the area value in map units. Works with polygon and multipolygon layers."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
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
                'default': 'Polygon Areas_{source_layer}',
                'label': 'Layer Name Template',
                'description': 'Template for the areas layer name. Available variables: {source_layer}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created areas layer to the project',
            },
            
            # PROCESSING SETTINGS
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'Only process selected polygon features (if any are selected)',
            },
            'skip_invalid_geometries': {
                'type': 'bool',
                'default': True,
                'label': 'Skip Invalid Geometries',
                'description': 'Skip polygons with invalid or empty geometries instead of showing an error',
            },
            
            # DISPLAY SETTINGS
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in area values',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            'label_size': {
                'type': 'float',
                'default': 10.0,
                'label': 'Label Size',
                'description': 'Text size for area labels',
                'min': 6.0,
                'max': 24.0,
                'step': 0.5,
            },
            'label_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Label Color',
                'description': 'Text color for area labels',
            },
            'label_placement': {
                'type': 'choice',
                'default': 'around',
                'label': 'Label Placement',
                'description': 'Placement of labels relative to polygon centroids',
                'options': ['around', 'over'],
            },
            'include_feature_id': {
                'type': 'bool',
                'default': False,
                'label': 'Include Feature ID',
                'description': 'Include feature ID in labels to identify which polygon the area belongs to',
            },
            'show_units': {
                'type': 'bool',
                'default': False,
                'label': 'Show Units',
                'description': 'Include unit name in labels (e.g., "123.45 m²")',
            },
            'include_total_area': {
                'type': 'bool',
                'default': True,
                'label': 'Include Total Area',
                'description': 'Show total area of all polygons in information message',
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created areas layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a success message after creating the areas layer',
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
    
    def _create_area_layer(self, layer_name, crs):
        """
        Create a point layer for displaying polygon areas.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            
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
            fields.append(QgsField('area', QVariant.Double))
            fields.append(QgsField('feature_id', QVariant.LongLong))
            
            layer.dataProvider().addAttributes(fields.toList())
            layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create area layer: {str(e)}")
            return None
    
    def _calculate_area(self, geometry, layer_crs):
        """
        Calculate polygon area with proper CRS handling.
        
        Args:
            geometry (QgsGeometry): Polygon geometry
            layer_crs: Layer coordinate reference system
            
        Returns:
            tuple: (area, calculation_crs) - Area value and CRS used for calculation
        """
        if not geometry or geometry.isEmpty():
            return None, None
        
        calculation_crs = layer_crs
        
        if layer_crs.isGeographic():
            # Transform to a projected CRS for accurate area calculation
            try:
                # Try to get UTM zone for the feature centroid
                centroid = geometry.centroid().asPoint()
                utm_zone = int((centroid.x() + 180) / 6) + 1
                hemisphere = 'north' if centroid.y() >= 0 else 'south'
                utm_epsg = f"EPSG:{32600 + utm_zone}" if hemisphere == 'north' else f"EPSG:{32700 + utm_zone}"
                projected_crs = QgsCoordinateReferenceSystem(utm_epsg)
            except:
                # Fallback to Web Mercator
                projected_crs = QgsCoordinateReferenceSystem("EPSG:3857")
            
            # Create a copy of geometry for transformation
            geometry_for_calculation = QgsGeometry(geometry)
            
            # Transform geometry to projected CRS
            transform = QgsCoordinateTransform(layer_crs, projected_crs, QgsProject.instance())
            try:
                geometry_for_calculation.transform(transform)
                calculation_crs = projected_crs
            except Exception as e:
                print(f"Warning: CRS transformation failed: {str(e)}, using original CRS")
                geometry_for_calculation = geometry
        else:
            # Already in projected CRS
            geometry_for_calculation = geometry
        
        # Calculate area
        area = geometry_for_calculation.area()
        return area, calculation_crs
    
    def _enable_labeling(self, layer, area_field_name, feature_id_field_name, decimal_places, label_size, label_color, label_placement, show_units, include_feature_id, unit_name=""):
        """
        Enable labeling on the layer to show polygon area.
        
        Args:
            layer (QgsVectorLayer): Layer to enable labeling on
            area_field_name (str): Name of the area field
            feature_id_field_name (str): Name of the feature ID field
            decimal_places (int): Number of decimal places
            label_size (float): Label text size
            label_color (str): Label color (hex string)
            label_placement (str): Label placement option
            show_units (bool): Whether to include units in label
            include_feature_id (bool): Whether to include feature ID in label
            unit_name (str): Unit name to display (e.g., "m²", "square meters")
        """
        try:
            # Create labeling settings
            pal_layer_settings = QgsPalLayerSettings()
            pal_layer_settings.enabled = True
            
            # Create expression to format area
            parts = []
            
            if include_feature_id:
                parts.append(f'"{feature_id_field_name}" || \': \'')
            
            parts.append(f'format_number("{area_field_name}", {decimal_places})')
            
            if show_units and unit_name:
                # Escape single quotes in unit_name for expression
                unit_escaped = unit_name.replace("'", "\\'")
                parts.append(f'\' {unit_escaped}\'')
            
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
        """Execute the show polygon layer areas action."""
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
            include_feature_id = bool(self.get_setting('include_feature_id', schema['include_feature_id']['default']))
            show_units = bool(self.get_setting('show_units', schema['show_units']['default']))
            include_total_area = bool(self.get_setting('include_total_area', schema['include_total_area']['default']))
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
        
        # Get the layer
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Validate that this is a polygon layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return
        
        try:
            # Generate output layer name
            source_layer_name = layer.name()
            output_layer_name = self._generate_output_layer_name(layer_name_template, source_layer_name)
            
            # Determine output path based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Areas Layer As",
                    "",
                    "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                output_path = save_path
            else:
                output_path = None  # Temporary layer
            
            # Create area layer
            area_layer = self._create_area_layer(
                output_layer_name,
                layer.crs()
            )
            
            if not area_layer:
                self.show_error("Error", "Failed to create area layer")
                return
            
            # Get features to process
            if process_selected_only and layer.selectedFeatureCount() > 0:
                features = layer.getSelectedFeatures()
            else:
                features = layer.getFeatures()
            
            # Process each polygon
            area_layer.startEditing()
            
            total_area = 0.0
            features_processed = 0
            features_skipped = 0
            calculation_crs = layer.crs()
            
            for feature in features:
                geometry = feature.geometry()
                
                if not geometry or geometry.isEmpty():
                    if skip_invalid_geometries:
                        features_skipped += 1
                        continue
                    else:
                        self.show_error("Error", f"Feature ID {feature.id()} has no valid geometry")
                        area_layer.rollBack()
                        return
                
                # Calculate area
                area, calc_crs = self._calculate_area(geometry, layer.crs())
                if area is None:
                    if skip_invalid_geometries:
                        features_skipped += 1
                        continue
                    else:
                        self.show_error("Error", f"Failed to calculate area for feature ID {feature.id()}")
                        area_layer.rollBack()
                        return
                
                # Store calculation CRS (use first valid one)
                if calc_crs and calculation_crs == layer.crs():
                    calculation_crs = calc_crs
                
                # Get polygon centroid
                centroid_geometry = geometry.centroid()
                if centroid_geometry.isEmpty():
                    if skip_invalid_geometries:
                        features_skipped += 1
                        continue
                    else:
                        self.show_error("Error", f"Could not calculate centroid for feature ID {feature.id()}")
                        area_layer.rollBack()
                        return
                
                centroid_point = centroid_geometry.asPoint()
                
                # Create point feature
                point_feature = QgsFeature()
                point_geometry = QgsGeometry.fromPointXY(QgsPointXY(centroid_point))
                point_feature.setGeometry(point_geometry)
                
                # Set attributes
                point_feature.setAttributes([round(area, decimal_places), feature.id()])
                area_layer.addFeature(point_feature)
                
                total_area += area
                features_processed += 1
            
            area_layer.commitChanges()
            
            if features_processed == 0:
                self.show_error("Error", "No valid polygon features found to process")
                return
            
            # Get unit name for labeling
            if calculation_crs.isGeographic():
                # We transformed to UTM/Web Mercator, so use square meters
                unit_name = "m²"
            elif calculation_crs.isValid() and calculation_crs.mapUnits() != 0:
                unit_name = f"square {calculation_crs.mapUnits().name().lower()}"
            else:
                unit_name = "square units"
            
            # Make points invisible (only labels visible)
            self._make_points_invisible(area_layer)
            
            # Enable labeling
            self._enable_labeling(
                area_layer,
                'area',
                'feature_id',
                decimal_places,
                label_size,
                label_color,
                label_placement,
                show_units,
                include_feature_id,
                unit_name
            )
            
            # Save to file if permanent
            if layer_storage_type == 'permanent' and output_path:
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    area_layer,
                    output_path,
                    "UTF-8",
                    area_layer.crs(),
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
                    
                    # Enable labeling
                    self._enable_labeling(
                        saved_layer,
                        'area',
                        'feature_id',
                        decimal_places,
                        label_size,
                        label_color,
                        label_placement,
                        show_units,
                        include_feature_id,
                        unit_name
                    )
                    area_layer = saved_layer
                else:
                    self.show_error("Error", "Failed to load saved layer")
                    return
            
            # Add to project if requested
            if add_to_project:
                QgsProject.instance().addMapLayer(area_layer)
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                try:
                    # Get layer extent
                    layer_extent = area_layer.extent()
                    
                    # Transform extent to canvas CRS if needed
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = area_layer.crs()
                    
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
                
                # Get unit name for message
                if calculation_crs.isGeographic():
                    unit_name_msg = "square meters"
                elif calculation_crs.isValid() and calculation_crs.mapUnits() != 0:
                    unit_name_msg = f"square {calculation_crs.mapUnits().name().lower()}"
                else:
                    unit_name_msg = "square units"
                
                message = f"Area layer '{output_layer_name}' {storage_info} successfully.\n\n"
                message += f"Features processed: {features_processed}\n"
                if features_skipped > 0:
                    message += f"Features skipped: {features_skipped}\n"
                if include_total_area:
                    message += f"Total area: {total_area:.{decimal_places}f} {unit_name_msg}\n"
                
                self.show_info("Polygon Areas Displayed", message)
        
        except Exception as e:
            self.show_error("Error", f"Failed to show polygon areas: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
show_polygon_layer_areas = ShowPolygonLayerAreasAction()

