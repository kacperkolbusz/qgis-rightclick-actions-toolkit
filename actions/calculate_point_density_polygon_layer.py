"""
Calculate Point Density for Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Calculates point density for all polygons in the selected polygon layer.
Shows point counts and densities for each polygon, organized by point layers.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsVectorLayer, QgsGeometry, QgsWkbTypes, QgsCoordinateTransform, QgsField
from qgis.PyQt.QtCore import QVariant, QMetaType


class CalculatePointDensityPolygonLayerAction(BaseAction):
    """Action to calculate point density for all polygons in a polygon layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_point_density_polygon_layer"
        self.name = "Calculate Point Density for Polygon Layer"
        self.category = "Analysis"
        self.description = "Calculate point density for all polygons in the selected polygon layer. Shows point counts and densities for each polygon, organized by point layers. Displays summary statistics and detailed per-polygon results."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        # Only support layer scope so the action appears in the polygon-layer section
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # DISPLAY SETTINGS - Easy to customize output format
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Display the polygon layer name in the result dialog',
            },
            'show_summary_statistics': {
                'type': 'bool',
                'default': True,
                'label': 'Show Summary Statistics',
                'description': 'Display summary statistics (total polygons, average density, etc.)',
            },
            'show_per_polygon_details': {
                'type': 'bool',
                'default': True,
                'label': 'Show Per-Polygon Details',
                'description': 'Display detailed results for each polygon',
            },
            'show_polygon_area': {
                'type': 'bool',
                'default': True,
                'label': 'Show Polygon Area',
                'description': 'Display polygon area in per-polygon details',
            },
            'show_point_counts': {
                'type': 'bool',
                'default': True,
                'label': 'Show Point Counts',
                'description': 'Display the number of points for each polygon',
            },
            'show_densities': {
                'type': 'bool',
                'default': True,
                'label': 'Show Densities',
                'description': 'Display point density (points per unit area) for each polygon',
            },
            'sort_polygons_by_density': {
                'type': 'bool',
                'default': True,
                'label': 'Sort Polygons by Density',
                'description': 'Sort polygons by overall density (highest first) in the result',
            },
            'group_by_point_layer': {
                'type': 'bool',
                'default': False,
                'label': 'Group by Point Layer',
                'description': 'Group results by point layer instead of by polygon',
            },
            'show_empty_polygons': {
                'type': 'bool',
                'default': False,
                'label': 'Show Empty Polygons',
                'description': 'Display polygons that have no points within them',
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places for density values',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'max_polygons_to_display': {
                'type': 'int',
                'default': 50,
                'label': 'Max Polygons to Display',
                'description': 'Maximum number of polygons to show in detailed results (0 = show all)',
                'min': 0,
                'max': 1000,
                'step': 10,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'include_visible_only': {
                'type': 'bool',
                'default': False,
                'label': 'Visible Layers Only',
                'description': 'Only analyze points from visible point layers',
            },
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
            
            # ATTRIBUTE TABLE SETTINGS - Store results in layer
            'store_in_attribute_table': {
                'type': 'bool',
                'default': False,
                'label': 'Store in Attribute Table',
                'description': 'Store density and point count values in the polygon layer attribute table',
            },
            'density_field_name': {
                'type': 'str',
                'default': 'pt_density',
                'label': 'Density Field Name',
                'description': 'Name of the field to store point density values (max 10 chars for shapefiles)',
            },
            'points_count_field_name': {
                'type': 'str',
                'default': 'pt_count',
                'label': 'Points Count Field Name',
                'description': 'Name of the field to store total point count values (max 10 chars for shapefiles)',
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
    
    def _get_point_layers(self, include_visible_only=False):
        """
        Get all point layers from the project.
        
        Args:
            include_visible_only (bool): If True, only return visible layers
            
        Returns:
            list: List of QgsVectorLayer objects that are point layers
        """
        project = QgsProject.instance()
        point_layers = []
        
        for layer_id, layer in project.mapLayers().items():
            # Check if it's a vector layer
            if not isinstance(layer, QgsVectorLayer):
                continue
            
            # Check if it's a point layer
            if layer.geometryType() != QgsWkbTypes.PointGeometry:
                continue
            
            # Check if layer is valid
            if not layer.isValid():
                continue
            
            # Check visibility if requested
            if include_visible_only:
                root = project.layerTreeRoot()
                layer_tree_layer = root.findLayer(layer_id)
                if not layer_tree_layer or not layer_tree_layer.isVisible():
                    continue
            
            point_layers.append(layer)
        
        return point_layers
    
    def _get_area_unit_name(self, crs):
        """
        Get the appropriate area unit name for the CRS.
        
        Args:
            crs: QgsCoordinateReferenceSystem
            
        Returns:
            str: Unit name for area (e.g., "square meters", "square degrees")
        """
        if crs.isGeographic():
            return "square degrees"
        elif crs.isValid() and crs.mapUnits() != 0:
            unit_name = crs.mapUnits().name().lower()
            if unit_name == "meters" or unit_name == "meter":
                return "square meters"
            elif unit_name == "feet" or unit_name == "foot":
                return "square feet"
            elif unit_name == "us feet" or unit_name == "us foot":
                return "square US feet"
            else:
                return f"square {unit_name}"
        else:
            return "square units"
    
    def _format_density(self, density, decimal_places):
        """
        Format density value intelligently to avoid showing 0.00 for very small values.
        
        Args:
            density (float): Density value to format
            decimal_places (int): Preferred number of decimal places
            
        Returns:
            str: Formatted density string
        """
        if density == 0.0:
            return "0.00"
        
        # If density is very small (< 0.01), use more decimal places to show meaningful value
        if density < 0.01:
            # Use more decimal places to show at least 2 significant digits
            import math
            if density > 0:
                # Calculate decimal places needed to show 2 significant digits
                magnitude = math.floor(math.log10(abs(density)))
                needed_places = abs(magnitude) + 1
                # Cap at reasonable maximum (12 decimal places)
                needed_places = min(needed_places, 12)
                return f"{density:.{needed_places}f}"
        
        # For normal values, use the requested decimal places
        return f"{density:.{decimal_places}f}"
    
    def _get_calculation_crs(self, layer_crs, layer_extent):
        """
        Get appropriate CRS for area calculations.
        Transforms geographic CRS to projected CRS for meaningful area measurements.
        
        Args:
            layer_crs: Original layer CRS
            layer_extent: Layer extent for determining UTM zone
            
        Returns:
            tuple: (calculation_crs, needs_transformation)
        """
        if layer_crs.isGeographic():
            # Transform to a projected CRS for accurate area calculation
            from qgis.core import QgsCoordinateReferenceSystem
            
            try:
                # Get layer extent to determine appropriate UTM zone
                if not layer_extent.isEmpty():
                    centroid = layer_extent.center()
                    utm_zone = int((centroid.x() + 180) / 6) + 1
                    hemisphere = 'north' if centroid.y() >= 0 else 'south'
                    utm_epsg = f"EPSG:{32600 + utm_zone}" if hemisphere == 'north' else f"EPSG:{32700 + utm_zone}"
                    projected_crs = QgsCoordinateReferenceSystem(utm_epsg)
                else:
                    # Fallback to Web Mercator
                    projected_crs = QgsCoordinateReferenceSystem("EPSG:3857")
            except:
                # Fallback to Web Mercator
                projected_crs = QgsCoordinateReferenceSystem("EPSG:3857")
            
            return projected_crs, True
        else:
            # Already in projected CRS
            return layer_crs, False
    
    def _count_points_in_polygon(self, polygon_geometry, polygon_crs, calculation_crs, point_layers):
        """
        Count points in a polygon from all point layers and calculate density.
        
        Args:
            polygon_geometry (QgsGeometry): Polygon geometry (in polygon_crs)
            polygon_crs: Polygon layer CRS (for point containment checks)
            calculation_crs: CRS to use for area calculations (projected CRS)
            point_layers (list): List of point layers to analyze
            
        Returns:
            dict: {layer_name: {'count': int, 'density': float}, ...}, 'total_count': int, 'overall_density': float
        """
        # Create a copy of geometry for area calculation in projected CRS
        if calculation_crs != polygon_crs:
            from qgis.core import QgsCoordinateTransform, QgsProject
            geometry_for_area = QgsGeometry(polygon_geometry)
            try:
                transform = QgsCoordinateTransform(polygon_crs, calculation_crs, QgsProject.instance())
                geometry_for_area.transform(transform)
            except Exception:
                # If transformation fails, use original geometry (will give wrong units but won't crash)
                geometry_for_area = polygon_geometry
        else:
            geometry_for_area = polygon_geometry
        
        polygon_area = geometry_for_area.area()
        if polygon_area < 0:
            return {}, 0, 0.0
        # Allow zero area - will result in 0 density (handled by caller)
        
        layer_data = {}
        total_count = 0
        
        for point_layer in point_layers:
            layer_name = point_layer.name()
            count = 0
            
            # Get point layer CRS
            point_crs = point_layer.crs()
            
            # Check if CRS transformation is needed (for containment check, use polygon_crs)
            needs_transformation = polygon_crs != point_crs
            
            if needs_transformation:
                try:
                    transform = QgsCoordinateTransform(point_crs, polygon_crs, QgsProject.instance())
                except Exception:
                    continue
            
            # Iterate through all points in the layer
            for point_feature in point_layer.getFeatures():
                point_geometry = point_feature.geometry()
                if not point_geometry or point_geometry.isEmpty():
                    continue
                
                # Transform point geometry if needed (to polygon_crs for containment check)
                if needs_transformation:
                    try:
                        point_geometry.transform(transform)
                    except Exception:
                        continue
                
                # Check if point is within polygon (using original polygon geometry in polygon_crs)
                if polygon_geometry.contains(point_geometry):
                    count += 1
            
            # Calculate density for this layer (using area in calculation_crs)
            density = count / polygon_area if polygon_area > 0 else 0.0
            
            # Store data for this layer
            layer_data[layer_name] = {
                'count': count,
                'density': density
            }
            total_count += count
        
        # Calculate overall density (using area in calculation_crs)
        overall_density = total_count / polygon_area if polygon_area > 0 else 0.0
        
        return layer_data, total_count, overall_density
    
    def execute(self, context):
        """Execute the calculate point density for polygon layer action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            show_layer_name = bool(self.get_setting('show_layer_name', schema['show_layer_name']['default']))
            show_summary_statistics = bool(self.get_setting('show_summary_statistics', schema['show_summary_statistics']['default']))
            show_per_polygon_details = bool(self.get_setting('show_per_polygon_details', schema['show_per_polygon_details']['default']))
            show_polygon_area = bool(self.get_setting('show_polygon_area', schema['show_polygon_area']['default']))
            show_point_counts = bool(self.get_setting('show_point_counts', schema['show_point_counts']['default']))
            show_densities = bool(self.get_setting('show_densities', schema['show_densities']['default']))
            sort_polygons_by_density = bool(self.get_setting('sort_polygons_by_density', schema['sort_polygons_by_density']['default']))
            group_by_point_layer = bool(self.get_setting('group_by_point_layer', schema['group_by_point_layer']['default']))
            show_empty_polygons = bool(self.get_setting('show_empty_polygons', schema['show_empty_polygons']['default']))
            decimal_places = int(self.get_setting('decimal_places', schema['decimal_places']['default']))
            max_polygons_to_display = int(self.get_setting('max_polygons_to_display', schema['max_polygons_to_display']['default']))
            include_visible_only = bool(self.get_setting('include_visible_only', schema['include_visible_only']['default']))
            process_selected_only = bool(self.get_setting('process_selected_only', schema['process_selected_only']['default']))
            skip_invalid_geometries = bool(self.get_setting('skip_invalid_geometries', schema['skip_invalid_geometries']['default']))
            store_in_attribute_table = bool(self.get_setting('store_in_attribute_table', schema['store_in_attribute_table']['default']))
            density_field_name = str(self.get_setting('density_field_name', schema['density_field_name']['default']))
            points_count_field_name = str(self.get_setting('points_count_field_name', schema['points_count_field_name']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
            return
        
        # Get the layer from the first detected feature
        layer = detected_features[0].layer
        
        if not isinstance(layer, QgsVectorLayer):
            self.show_error("Error", "Selected layer is not a vector layer")
            return
        
        if layer.geometryType() not in [QgsWkbTypes.PolygonGeometry]:
            self.show_error("Error", "Selected layer is not a polygon layer")
            return
        
        try:
            # Get polygon layer CRS
            polygon_crs = layer.crs()
            layer_extent = layer.extent()
            
            # Get appropriate CRS for area calculations (projected CRS if layer is geographic)
            calculation_crs, needs_crs_transform = self._get_calculation_crs(polygon_crs, layer_extent)
            area_unit_name = self._get_area_unit_name(calculation_crs)
            
            # Get all point layers
            point_layers = self._get_point_layers(include_visible_only)
            
            if not point_layers:
                self.show_warning("No Point Layers", "No point layers found in the project.")
                return
            
            # Get features to process
            if process_selected_only and layer.selectedFeatureCount() > 0:
                features = layer.selectedFeatures()
            else:
                features = layer.getFeatures()
            
            # Process all polygons
            polygon_results = []
            total_polygons = 0
            valid_polygons = 0
            total_points_all_polygons = 0
            total_area_all_polygons = 0.0
            density_sum = 0.0
            
            for feature in features:
                total_polygons += 1
                
                polygon_geometry = feature.geometry()
                if not polygon_geometry or polygon_geometry.isEmpty():
                    if not skip_invalid_geometries:
                        self.show_error("Error", f"Feature ID {feature.id()} has no geometry")
                        return
                    continue
                
                # Check area - but still process even if area is 0 (will result in 0 density)
                polygon_area = polygon_geometry.area()
                if polygon_area < 0:
                    if not skip_invalid_geometries:
                        self.show_error("Error", f"Feature ID {feature.id()} has negative area")
                        return
                    continue
                
                valid_polygons += 1
                
                # Calculate area in calculation CRS (projected CRS for meaningful units)
                if needs_crs_transform:
                    from qgis.core import QgsCoordinateTransform, QgsProject
                    geometry_for_area = QgsGeometry(polygon_geometry)
                    try:
                        transform = QgsCoordinateTransform(polygon_crs, calculation_crs, QgsProject.instance())
                        geometry_for_area.transform(transform)
                        polygon_area_calc = geometry_for_area.area()
                    except Exception:
                        # If transformation fails, use original area (will have wrong units)
                        polygon_area_calc = polygon_area
                else:
                    polygon_area_calc = polygon_area
                
                # Count points in this polygon (always calculate, even if area is 0)
                layer_data, total_count, overall_density = self._count_points_in_polygon(
                    polygon_geometry, polygon_crs, calculation_crs, point_layers
                )
                
                # Ensure density is 0 if area is 0 (to avoid division issues)
                if polygon_area_calc <= 0:
                    overall_density = 0.0
                    # Reset layer densities to 0 as well
                    for layer_name in layer_data:
                        layer_data[layer_name]['density'] = 0.0
                
                # Store results (use calculated area for display)
                # Always store, even if count is 0 (will show 0 density)
                polygon_results.append({
                    'feature_id': feature.id(),
                    'area': polygon_area_calc,
                    'layer_data': layer_data,
                    'total_count': total_count,
                    'overall_density': overall_density
                })
                
                total_points_all_polygons += total_count
                total_area_all_polygons += polygon_area_calc
                density_sum += overall_density
            
            if valid_polygons == 0:
                self.show_warning("No Valid Polygons", "No valid polygons found in the layer.")
                return
            
            # Calculate summary statistics
            average_density = density_sum / valid_polygons if valid_polygons > 0 else 0.0
            average_area = total_area_all_polygons / valid_polygons if valid_polygons > 0 else 0.0
            average_points_per_polygon = total_points_all_polygons / valid_polygons if valid_polygons > 0 else 0.0
            
            # Build result message
            result_lines = []
            
            if show_layer_name:
                result_lines.append(f"Layer: {layer.name()}")
            
            # Summary statistics
            if show_summary_statistics:
                formatted_avg_density = self._format_density(average_density, decimal_places)
                result_lines.append(f"Summary: {valid_polygons} polygons | {total_points_all_polygons} points | Avg density: {formatted_avg_density} pts/{area_unit_name}")
            
            # Per-polygon details
            if show_per_polygon_details:
                # Sort polygons if requested
                if sort_polygons_by_density:
                    sorted_polygons = sorted(polygon_results, key=lambda x: x['overall_density'], reverse=True)
                else:
                    sorted_polygons = sorted(polygon_results, key=lambda x: x['feature_id'])
                
                # Limit display if requested
                polygons_to_show = sorted_polygons
                if max_polygons_to_display > 0 and len(sorted_polygons) > max_polygons_to_display:
                    polygons_to_show = sorted_polygons[:max_polygons_to_display]
                    result_lines.append(f"Showing {max_polygons_to_display} of {len(sorted_polygons)} polygons:")
                else:
                    result_lines.append(f"Polygons ({len(sorted_polygons)}):")
                
                for idx, poly_data in enumerate(polygons_to_show, 1):
                    feature_id = poly_data['feature_id']
                    area = poly_data['area']
                    layer_data = poly_data['layer_data']
                    total_count = poly_data['total_count']
                    overall_density = poly_data['overall_density']
                    
                    # Skip empty polygons in display if not showing them (but still process them for storage)
                    if total_count == 0 and not show_empty_polygons:
                        # Still add to results for storage, just skip display
                        pass
                    
                    # Build compact line for polygon
                    poly_line = f"ID {feature_id}:"
                    
                    if show_polygon_area:
                        poly_line += f" Area={area:.{decimal_places}f} {area_unit_name}"
                    
                    if show_point_counts:
                        poly_line += f" | Points={total_count}"
                    
                    if show_densities:
                        formatted_density = self._format_density(overall_density, decimal_places)
                        poly_line += f" | Density={formatted_density} pts/{area_unit_name}"
                    
                    result_lines.append(poly_line)
                    
                    # Show breakdown by point layer (compact)
                    if layer_data:
                        layer_lines = []
                        for layer_name, data in sorted(layer_data.items(), key=lambda x: x[1]['count'], reverse=True):
                            count = data['count']
                            if count == 0 and not show_empty_polygons:
                                continue
                            
                            layer_line = f"  {layer_name}:"
                            
                            if show_point_counts:
                                layer_line += f" {count}"
                            
                            if show_densities:
                                formatted_layer_density = self._format_density(data['density'], decimal_places)
                                layer_line += f" ({formatted_layer_density} pts/{area_unit_name})"
                            
                            layer_lines.append(layer_line)
                        
                        if layer_lines:
                            result_lines.extend(layer_lines)
                
                if max_polygons_to_display > 0 and len(sorted_polygons) > max_polygons_to_display:
                    result_lines.append(f"... {len(sorted_polygons) - max_polygons_to_display} more (increase 'Max Polygons to Display' to see all)")
            
            result_text = "\n".join(result_lines)
            
            # Store in attribute table if requested
            if store_in_attribute_table:
                try:
                    # Handle edit mode
                    edit_result = self.handle_edit_mode(layer, "storing density data")
                    if edit_result[0] is None:  # Error occurred
                        self.show_warning("Warning", "Could not enter edit mode. Density data will not be stored in attribute table.")
                    else:
                        was_in_edit_mode, edit_mode_entered = edit_result
                        
                        try:
                            # Prepare fields to add
                            fields_to_add = []
                            
                            # Check and add density field (with precision to avoid scientific notation)
                            if layer.fields().indexOf(density_field_name) == -1:
                                density_field = QgsField(density_field_name, QVariant.Double)
                                density_field.setPrecision(10)  # Set precision to avoid scientific notation
                                density_field.setLength(20)  # Set length for display
                                fields_to_add.append(density_field)
                            
                            # Check and add points count field
                            if layer.fields().indexOf(points_count_field_name) == -1:
                                fields_to_add.append(QgsField(points_count_field_name, QVariant.Int))
                            
                            # Add new fields if any
                            if fields_to_add:
                                result = layer.dataProvider().addAttributes(fields_to_add)
                                if not result:
                                    self.show_warning("Warning", f"Failed to add fields: {[f.name() for f in fields_to_add]}")
                                # Always update fields after attempting to add (even if it failed, to refresh)
                                layer.updateFields()
                            
                            # Get final field indices (after adding fields and updating)
                            # Force refresh of fields
                            layer.updateFields()
                            fields = layer.fields()
                            
                            # Find fields by name (handle truncation - use actual field names that were created)
                            # First try exact match
                            density_field_idx = fields.indexOf(density_field_name)
                            if density_field_idx == -1:
                                # Try case-insensitive search
                                for i, field in enumerate(fields):
                                    if field.name().lower() == density_field_name.lower():
                                        density_field_idx = i
                                        density_field_name = field.name()  # Use actual name
                                        break
                                # If still not found, try prefix match (for truncated names)
                                if density_field_idx == -1:
                                    for i, field in enumerate(fields):
                                        if field.name().lower().startswith(density_field_name.lower()[:8]):
                                            density_field_idx = i
                                            density_field_name = field.name()  # Use actual truncated name
                                            break
                            
                            points_count_field_idx = fields.indexOf(points_count_field_name)
                            if points_count_field_idx == -1:
                                # Try case-insensitive search
                                for i, field in enumerate(fields):
                                    if field.name().lower() == points_count_field_name.lower():
                                        points_count_field_idx = i
                                        points_count_field_name = field.name()  # Use actual name
                                        break
                                # If still not found, try prefix match (for truncated names)
                                if points_count_field_idx == -1:
                                    for i, field in enumerate(fields):
                                        if field.name().lower().startswith(points_count_field_name.lower()[:8]):
                                            points_count_field_idx = i
                                            points_count_field_name = field.name()  # Use actual truncated name
                                            break
                            
                            # Check if fields exist
                            if density_field_idx == -1 and points_count_field_idx == -1:
                                # List all field names for debugging
                                all_field_names = [f.name() for f in fields]
                                self.show_warning("Warning", f"Could not find fields '{density_field_name}' or '{points_count_field_name}' after adding them. Available fields: {', '.join(all_field_names[:10])}")
                            else:
                                # Update features with calculated values
                                updated_count = 0
                                failed_count = 0

                                # Prepare backups for history (old/new attribute values)
                                features_backup = []

                                for poly_data in polygon_results:
                                    feature_id = poly_data['feature_id']

                                    # Get feature by ID (more reliable than iterating)
                                    feature = layer.getFeature(feature_id)
                                    if not feature.isValid():
                                        failed_count += 1
                                        continue

                                    attributes_changed = False

                                    old_attrs = {}
                                    new_attrs = {}

                                    # Density field
                                    if density_field_idx >= 0:
                                        try:
                                            old_val = feature.attribute(density_field_idx)
                                            if hasattr(old_val, 'isNull') and old_val.isNull():
                                                old_serial = None
                                            else:
                                                old_serial = old_val
                                        except Exception:
                                            old_serial = None

                                        density_value = poly_data['overall_density']
                                        if density_value != 0.0:
                                            if density_value < 0.000001:
                                                density_value = round(density_value, 12)
                                            else:
                                                density_value = round(density_value, 10)

                                        new_serial = density_value

                                        old_attrs[fields[density_field_idx].name()] = old_serial
                                        new_attrs[fields[density_field_idx].name()] = new_serial

                                        try:
                                            feature.setAttribute(density_field_idx, density_value)
                                            attributes_changed = True
                                        except Exception:
                                            # try setting by name
                                            try:
                                                feature.setAttribute(fields[density_field_idx].name(), density_value)
                                                attributes_changed = True
                                            except Exception:
                                                pass

                                    # Points count field
                                    if points_count_field_idx >= 0:
                                        try:
                                            old_val = feature.attribute(points_count_field_idx)
                                            if hasattr(old_val, 'isNull') and old_val.isNull():
                                                old_serial = None
                                            else:
                                                old_serial = old_val
                                        except Exception:
                                            old_serial = None

                                        new_count = int(poly_data['total_count'])
                                        old_attrs[fields[points_count_field_idx].name()] = old_serial
                                        new_attrs[fields[points_count_field_idx].name()] = new_count

                                        try:
                                            feature.setAttribute(points_count_field_idx, new_count)
                                            attributes_changed = True
                                        except Exception:
                                            try:
                                                feature.setAttribute(fields[points_count_field_idx].name(), new_count)
                                                attributes_changed = True
                                            except Exception:
                                                pass

                                    # If any attributes changed, attempt update and record backup
                                    if attributes_changed:
                                        if layer.updateFeature(feature):
                                            updated_count += 1
                                            features_backup.append({
                                                'fid': int(feature_id),
                                                'old_attributes': old_attrs,
                                                'new_attributes': new_attrs
                                            })
                                        else:
                                            failed_count += 1
                                
                                if updated_count == 0 and failed_count > 0:
                                    self.show_warning("Warning", f"Could not update any features. {failed_count} features failed to update.")
                            
                            # Commit changes
                            if self.commit_changes(layer, "storing density data"):
                                # Trigger layer refresh to update attribute table display
                                layer.triggerRepaint()
                                
                                stored_fields = []
                                if density_field_idx >= 0:
                                    stored_fields.append(density_field_name)
                                if points_count_field_idx >= 0:
                                    stored_fields.append(points_count_field_name)
                                
                                if stored_fields:
                                        # Record undoable history entry (schema + attribute updates if fields were added)
                                        try:
                                            from ..history_manager import get_history_manager
                                            hm = get_history_manager()

                                            layer_desc = hm.create_layer_descriptor(layer)
                                            description_store = f"Stored density/count values in fields {', '.join(stored_fields)} ({updated_count} features updated)"

                                            if fields_to_add:
                                                added_fields_desc = []
                                                for nf in fields_to_add:
                                                    try:
                                                        qmeta = int(QMetaType.Double)
                                                    except Exception:
                                                        qmeta = 0
                                                    added_fields_desc.append({
                                                        'name': nf.name(),
                                                        'qmeta_type': qmeta,
                                                        'length': getattr(nf, 'length', None),
                                                        'precision': getattr(nf, 'precision', None)
                                                    })

                                                sub_operations = [
                                                    {
                                                        'undo_type': 'update_schema',
                                                        'layers': [layer_desc],
                                                        'undo_payload': {'added_fields': added_fields_desc}
                                                    },
                                                    {
                                                        'undo_type': 'update_attributes',
                                                        'layers': [layer_desc],
                                                        'features': features_backup
                                                    }
                                                ]

                                                hm.record(
                                                    action_id=self.action_id,
                                                    action_name=self.name,
                                                    description=description_store,
                                                    undo_type='composite',
                                                    can_undo=True,
                                                    undo_payload={'sub_operations': sub_operations},
                                                    layers=[layer_desc],
                                                    features=features_backup,
                                                    atomic=True,
                                                    meta={'fields': stored_fields, 'updated_count': updated_count}
                                                )
                                            else:
                                                hm.record(
                                                    action_id=self.action_id,
                                                    action_name=self.name,
                                                    description=description_store,
                                                    undo_type='update_attributes',
                                                    can_undo=True,
                                                    undo_payload=None,
                                                    redo_payload=None,
                                                    layers=[layer_desc],
                                                    features=features_backup,
                                                    atomic=True,
                                                    meta={'fields': stored_fields, 'updated_count': updated_count}
                                                )
                                        except Exception:
                                            self.show_warning("Warning", "Failed to record undo information for stored density data")

                                        result_text += f"\n\n✓ Stored in attribute table: {', '.join(stored_fields)} ({updated_count} features updated)"
                            
                        except Exception as store_error:
                            self.show_warning("Warning", f"Failed to store data in attribute table: {str(store_error)}")
                            self.rollback_changes(layer)
                        finally:
                            # Exit edit mode if we entered it
                            self.exit_edit_mode(layer, edit_mode_entered)
                            
                except Exception as e:
                    self.show_warning("Warning", f"Failed to store data in attribute table: {str(e)}")
            
            # Show result
            self.show_info("Point Density for Polygon Layer", result_text)
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate point density: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_point_density_polygon_layer_action = CalculatePointDensityPolygonLayerAction()

