"""
Divide Polygon Into Equal Areas Action for Right-click Utilities and Shortcuts Hub

Divides a polygon feature into smaller polygons with equal areas.
User specifies the number of divisions, and the polygon is sliced accordingly.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsPointXY,
    QgsCoordinateReferenceSystem, QgsVectorFileWriter, QgsRectangle
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QSpinBox, QComboBox
)


class DivisionInputDialog(QDialog):
    """Dialog for user input of number of divisions and division method."""
    
    def __init__(self, parent=None, default_divisions=2, default_method='vertical', polygon_area=None):
        super().__init__(parent)
        self.setWindowTitle("Divide Polygon Into Equal Areas")
        self.setModal(True)
        self.resize(400, 200)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Polygon area info
        if polygon_area is not None:
            area_label = QLabel(f"Polygon area: {polygon_area:.2f} square map units")
            area_label.setStyleSheet("color: gray; font-size: 10px;")
            form_layout.addRow("", area_label)
        
        # Division method selection
        self.method_combo = QComboBox()
        self.method_combo.addItem("Vertical Stripes", "vertical")
        self.method_combo.addItem("Horizontal Stripes", "horizontal")
        self.method_combo.addItem("Cake Slices (Radial)", "radial")
        self.method_combo.addItem("Grid (Rows x Columns)", "grid")
        
        # Set default method
        index = self.method_combo.findData(default_method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)
        
        form_layout.addRow("Division Method:", self.method_combo)
        
        # Number of divisions input
        self.divisions_spinbox = QSpinBox()
        self.divisions_spinbox.setRange(2, 100)
        self.divisions_spinbox.setValue(default_divisions)
        form_layout.addRow("Number of Divisions:", self.divisions_spinbox)
        
        # Grid-specific inputs (hidden by default)
        self.grid_rows_label = QLabel("Grid Rows:")
        self.grid_rows_spinbox = QSpinBox()
        self.grid_rows_spinbox.setRange(2, 20)
        self.grid_rows_spinbox.setValue(2)
        self.grid_rows_label.setVisible(False)
        self.grid_rows_spinbox.setVisible(False)
        form_layout.addRow(self.grid_rows_label, self.grid_rows_spinbox)
        
        self.grid_cols_label = QLabel("Grid Columns:")
        self.grid_cols_spinbox = QSpinBox()
        self.grid_cols_spinbox.setRange(2, 20)
        self.grid_cols_spinbox.setValue(2)
        self.grid_cols_label.setVisible(False)
        self.grid_cols_spinbox.setVisible(False)
        form_layout.addRow(self.grid_cols_label, self.grid_cols_spinbox)
        
        # Help text
        self.help_label = QLabel("The polygon will be divided into this many equal-area parts")
        self.help_label.setStyleSheet("color: gray; font-size: 10px;")
        form_layout.addRow("", self.help_label)
        
        # Update help text and visibility when method changes
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._on_method_changed()
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Divide")
        self.cancel_button = QPushButton("Cancel")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to divisions input
        self.divisions_spinbox.setFocus()
    
    def _on_method_changed(self):
        """Update UI based on selected division method."""
        method = self.method_combo.currentData()
        
        if method == 'grid':
            # Show grid-specific inputs
            self.grid_rows_label.setVisible(True)
            self.grid_rows_spinbox.setVisible(True)
            self.grid_cols_label.setVisible(True)
            self.grid_cols_spinbox.setVisible(True)
            self.divisions_spinbox.setVisible(False)
            self.help_label.setText("Grid will be divided into rows × columns equal-area cells")
        else:
            # Hide grid-specific inputs
            self.grid_rows_label.setVisible(False)
            self.grid_rows_spinbox.setVisible(False)
            self.grid_cols_label.setVisible(False)
            self.grid_cols_spinbox.setVisible(False)
            self.divisions_spinbox.setVisible(True)
            
            # Update help text
            method_names = {
                'vertical': 'vertical stripes',
                'horizontal': 'horizontal stripes',
                'radial': 'cake slices from center'
            }
            method_name = method_names.get(method, 'parts')
            self.help_label.setText(f"The polygon will be divided into {self.divisions_spinbox.value()} equal-area {method_name}")
    
    def get_divisions(self):
        """Get the number of divisions."""
        return self.divisions_spinbox.value()
    
    def get_method(self):
        """Get the division method."""
        return self.method_combo.currentData()
    
    def get_grid_rows(self):
        """Get grid rows (only for grid method)."""
        return self.grid_rows_spinbox.value()
    
    def get_grid_cols(self):
        """Get grid columns (only for grid method)."""
        return self.grid_cols_spinbox.value()


class DividePolygonIntoEqualAreasAction(BaseAction):
    """Action to divide a polygon into equal-area parts."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "divide_polygon_into_equal_areas"
        self.name = "Divide Polygon Into Equal Areas"
        self.category = "Geometry"
        self.description = "Divide a polygon feature into smaller polygons with equal areas. User specifies the number of divisions, and the polygon is sliced into that many equal-area parts. Works with polygon and multipolygon features."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    # Undo support: creating layers requires storing layer definitions for redo
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'
    
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
                'default': 'Divided Polygon_{feature_id}',
                'label': 'Layer Name Template',
                'description': 'Template for the divided polygon layer name. Available variables: {feature_id}, {layer_name}, {timestamp}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the created divided polygon layer to the project',
            },
            'copy_attributes': {
                'type': 'bool',
                'default': True,
                'label': 'Copy Attributes',
                'description': 'Copy attributes from original polygon to divided polygons',
            },
            
            # DIVISION SETTINGS
            'default_divisions': {
                'type': 'int',
                'default': 2,
                'label': 'Default Number of Divisions',
                'description': 'Default number of divisions shown in the input dialog',
                'min': 2,
                'max': 100,
                'step': 1,
            },
            'default_division_method': {
                'type': 'choice',
                'default': 'vertical',
                'label': 'Default Division Method',
                'description': 'Default division method shown in the input dialog',
                'options': ['vertical', 'horizontal', 'radial', 'grid'],
            },
            
            # BEHAVIOR SETTINGS
            'zoom_to_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Zoom to Layer',
                'description': 'Automatically zoom to the created divided polygon layer',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after dividing the polygon',
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
    
    def _generate_output_layer_name(self, template, feature_id, layer_name):
        """
        Generate output layer name from template.
        
        Args:
            template (str): Name template
            feature_id (int): Feature ID
            layer_name (str): Source layer name
            
        Returns:
            str: Generated layer name
        """
        from datetime import datetime
        
        # Replace template variables
        name = template.replace('{feature_id}', str(feature_id))
        name = name.replace('{layer_name}', layer_name)
        name = name.replace('{timestamp}', datetime.now().strftime('%Y%m%d_%H%M%S'))
        name = name.replace('{date}', datetime.now().strftime('%Y-%m-%d'))
        name = name.replace('{time}', datetime.now().strftime('%H:%M:%S'))
        
        return name
    
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
    
    def _divide_polygon(self, geometry, num_divisions, division_method, layer_crs, grid_rows=None, grid_cols=None):
        """
        Divide a polygon into equal-area parts.
        
        Args:
            geometry (QgsGeometry): Polygon geometry to divide
            num_divisions (int): Number of divisions (for non-grid methods)
            division_method (str): Division method ('vertical', 'horizontal', 'radial', 'grid')
            layer_crs: Layer coordinate reference system
            grid_rows (int): Number of grid rows (for grid method)
            grid_cols (int): Number of grid columns (for grid method)
            
        Returns:
            list: List of QgsGeometry objects representing divided polygons
        """
        if not geometry or geometry.isEmpty():
            return []
        
        # Route to appropriate division method
        if division_method == 'vertical':
            return self._divide_vertical(geometry, num_divisions, layer_crs)
        elif division_method == 'horizontal':
            return self._divide_horizontal(geometry, num_divisions, layer_crs)
        elif division_method == 'radial':
            return self._divide_radial(geometry, num_divisions, layer_crs)
        elif division_method == 'grid':
            if grid_rows is None or grid_cols is None:
                return []
            return self._divide_grid(geometry, grid_rows, grid_cols, layer_crs)
        else:
            return []
    
    def _divide_vertical(self, geometry, num_divisions, layer_crs):
        """Divide polygon into vertical stripes."""
        if not geometry or geometry.isEmpty():
            return []
        
        bbox = geometry.boundingBox()
        total_area, _ = self._calculate_area(geometry, layer_crs)
        if total_area is None or total_area <= 0:
            return []
        
        target_area = total_area / num_divisions
        # Area tolerance: 0.0001% of target area (for 99.9999% precision)
        area_tolerance = target_area * 0.000001
        # Coordinate tolerance: very small relative to bbox width
        coord_tolerance = (bbox.xMaximum() - bbox.xMinimum()) * 1e-10
        divided_polygons = []
        
        # Vertical slices (divide by X coordinates)
        x_min = bbox.xMinimum()
        x_max = bbox.xMaximum()
        
        # Find slice positions using binary search with area-based convergence
        slice_positions = [x_min]
        
        for i in range(1, num_divisions):
            x_low = slice_positions[-1]
            x_high = x_max
            max_iterations = 100  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                x_mid = (x_low + x_high) / 2.0
                
                # Check coordinate tolerance
                if x_high - x_low < coord_tolerance:
                    break
                
                slice_rect = QgsGeometry.fromRect(
                    QgsRectangle(slice_positions[-1], bbox.yMinimum(), x_mid, bbox.yMaximum())
                )
                
                slice_geom = geometry.intersection(slice_rect)
                if slice_geom and not slice_geom.isEmpty():
                    slice_area, _ = self._calculate_area(slice_geom, layer_crs)
                    if slice_area:
                        area_diff = abs(slice_area - target_area)
                        # Check area tolerance
                        if area_diff < area_tolerance:
                            break
                        if slice_area < target_area:
                            x_low = x_mid
                        else:
                            x_high = x_mid
                    else:
                        x_low = x_mid
                else:
                    x_low = x_mid
                
                iteration += 1
            
            slice_positions.append((x_low + x_high) / 2.0)
        
        slice_positions.append(x_max)
        
        # Create divided polygons
        for i in range(num_divisions):
            x_start = slice_positions[i]
            x_end = slice_positions[i + 1]
            
            slice_rect = QgsGeometry.fromRect(
                QgsRectangle(x_start, bbox.yMinimum(), x_end, bbox.yMaximum())
            )
            
            slice_geom = geometry.intersection(slice_rect)
            if slice_geom and not slice_geom.isEmpty():
                if slice_geom.isMultipart():
                    parts = slice_geom.asGeometryCollection()
                    for part in parts:
                        if part and not part.isEmpty() and part.type() == QgsWkbTypes.PolygonGeometry:
                            divided_polygons.append(part)
                else:
                    divided_polygons.append(slice_geom)
        
        return divided_polygons
    
    def _divide_horizontal(self, geometry, num_divisions, layer_crs):
        """Divide polygon into horizontal stripes."""
        if not geometry or geometry.isEmpty():
            return []
        
        bbox = geometry.boundingBox()
        total_area, _ = self._calculate_area(geometry, layer_crs)
        if total_area is None or total_area <= 0:
            return []
        
        target_area = total_area / num_divisions
        # Area tolerance: 0.0001% of target area (for 99.9999% precision)
        area_tolerance = target_area * 0.000001
        # Coordinate tolerance: very small relative to bbox height
        coord_tolerance = (bbox.yMaximum() - bbox.yMinimum()) * 1e-10
        divided_polygons = []
        
        # Horizontal slices (divide by Y coordinates)
        y_min = bbox.yMinimum()
        y_max = bbox.yMaximum()
        
        # Find slice positions using binary search with area-based convergence
        slice_positions = [y_min]
        
        for i in range(1, num_divisions):
            y_low = slice_positions[-1]
            y_high = y_max
            max_iterations = 100  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                y_mid = (y_low + y_high) / 2.0
                
                # Check coordinate tolerance
                if y_high - y_low < coord_tolerance:
                    break
                
                slice_rect = QgsGeometry.fromRect(
                    QgsRectangle(bbox.xMinimum(), slice_positions[-1], bbox.xMaximum(), y_mid)
                )
                
                slice_geom = geometry.intersection(slice_rect)
                if slice_geom and not slice_geom.isEmpty():
                    slice_area, _ = self._calculate_area(slice_geom, layer_crs)
                    if slice_area:
                        area_diff = abs(slice_area - target_area)
                        # Check area tolerance
                        if area_diff < area_tolerance:
                            break
                        if slice_area < target_area:
                            y_low = y_mid
                        else:
                            y_high = y_mid
                    else:
                        y_low = y_mid
                else:
                    y_low = y_mid
                
                iteration += 1
            
            slice_positions.append((y_low + y_high) / 2.0)
        
        slice_positions.append(y_max)
        
        # Create divided polygons
        for i in range(num_divisions):
            y_start = slice_positions[i]
            y_end = slice_positions[i + 1]
            
            slice_rect = QgsGeometry.fromRect(
                QgsRectangle(bbox.xMinimum(), y_start, bbox.xMaximum(), y_end)
            )
            
            slice_geom = geometry.intersection(slice_rect)
            if slice_geom and not slice_geom.isEmpty():
                if slice_geom.isMultipart():
                    parts = slice_geom.asGeometryCollection()
                    for part in parts:
                        if part and not part.isEmpty() and part.type() == QgsWkbTypes.PolygonGeometry:
                            divided_polygons.append(part)
                else:
                    divided_polygons.append(slice_geom)
        
        return divided_polygons
    
    def _divide_radial(self, geometry, num_divisions, layer_crs):
        """Divide polygon into radial slices (cake slices) from centroid."""
        if not geometry or geometry.isEmpty():
            return []
        
        import math
        
        # Get centroid
        centroid = geometry.centroid().asPoint()
        bbox = geometry.boundingBox()
        
        # Calculate radius (distance from centroid to farthest corner)
        corners = [
            QgsPointXY(bbox.xMinimum(), bbox.yMinimum()),
            QgsPointXY(bbox.xMaximum(), bbox.yMinimum()),
            QgsPointXY(bbox.xMaximum(), bbox.yMaximum()),
            QgsPointXY(bbox.xMinimum(), bbox.yMaximum())
        ]
        max_radius = 0
        for corner in corners:
            dx = corner.x() - centroid.x()
            dy = corner.y() - centroid.y()
            radius = math.sqrt(dx * dx + dy * dy)
            if radius > max_radius:
                max_radius = radius
        
        total_area, _ = self._calculate_area(geometry, layer_crs)
        if total_area is None or total_area <= 0:
            return []
        
        target_area = total_area / num_divisions
        # Area tolerance: 0.0001% of target area (for 99.9999% precision)
        area_tolerance = target_area * 0.000001
        # Angle tolerance: very small
        angle_tolerance = 0.0001  # 0.0001 degrees
        divided_polygons = []
        
        # Find slice angles using binary search with area-based convergence
        slice_angles = [0.0]
        
        for i in range(1, num_divisions):
            angle_low = slice_angles[-1]
            angle_high = 360.0
            max_iterations = 100  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                angle_mid = (angle_low + angle_high) / 2.0
                
                # Check angle tolerance
                if angle_high - angle_low < angle_tolerance:
                    break
                
                # Create wedge from previous angle to this angle
                wedge = self._create_wedge(centroid, max_radius * 2, slice_angles[-1], angle_mid)
                slice_geom = geometry.intersection(wedge)
                
                if slice_geom and not slice_geom.isEmpty():
                    slice_area, _ = self._calculate_area(slice_geom, layer_crs)
                    if slice_area:
                        area_diff = abs(slice_area - target_area)
                        # Check area tolerance
                        if area_diff < area_tolerance:
                            break
                        if slice_area < target_area:
                            angle_low = angle_mid
                        else:
                            angle_high = angle_mid
                    else:
                        angle_low = angle_mid
                else:
                    angle_low = angle_mid
                
                iteration += 1
            
            slice_angles.append((angle_low + angle_high) / 2.0)
        
        slice_angles.append(360.0)
        
        # Create divided polygons
        for i in range(num_divisions):
            angle_start = slice_angles[i]
            angle_end = slice_angles[i + 1]
            
            wedge = self._create_wedge(centroid, max_radius * 2, angle_start, angle_end)
            slice_geom = geometry.intersection(wedge)
            
            if slice_geom and not slice_geom.isEmpty():
                if slice_geom.isMultipart():
                    parts = slice_geom.asGeometryCollection()
                    for part in parts:
                        if part and not part.isEmpty() and part.type() == QgsWkbTypes.PolygonGeometry:
                            divided_polygons.append(part)
                else:
                    divided_polygons.append(slice_geom)
        
        return divided_polygons
    
    def _create_wedge(self, center, radius, angle_start, angle_end):
        """Create a wedge (pie slice) geometry."""
        import math
        
        # Convert angles to radians
        start_rad = math.radians(angle_start)
        end_rad = math.radians(angle_end)
        
        # Create points for the wedge
        points = [center]
        
        # Add points along the arc
        num_points = max(10, int((angle_end - angle_start) / 2))  # At least 10 points per 2 degrees
        for i in range(num_points + 1):
            angle = start_rad + (end_rad - start_rad) * (i / num_points)
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            points.append(QgsPointXY(x, y))
        
        # Close the polygon
        points.append(center)
        
        # Create polygon
        return QgsGeometry.fromPolygonXY([points])
    
    def _divide_grid(self, geometry, rows, cols, layer_crs):
        """Divide polygon into a grid of equal-area cells."""
        if not geometry or geometry.isEmpty():
            return []
        
        bbox = geometry.boundingBox()
        total_area, _ = self._calculate_area(geometry, layer_crs)
        if total_area is None or total_area <= 0:
            return []
        
        target_area = total_area / (rows * cols)
        divided_polygons = []
        
        # First, find horizontal slice positions
        y_min = bbox.yMinimum()
        y_max = bbox.yMaximum()
        y_slices = [y_min]
        
        for i in range(1, rows):
            y_low = y_slices[-1]
            y_high = y_max
            tolerance = (y_max - y_min) * 0.0001
            
            while y_high - y_low > tolerance:
                y_mid = (y_low + y_high) / 2.0
                
                # Create horizontal slice
                slice_rect = QgsGeometry.fromRect(
                    QgsRectangle(bbox.xMinimum(), y_slices[-1], bbox.xMaximum(), y_mid)
                )
                slice_geom = geometry.intersection(slice_rect)
                
                if slice_geom and not slice_geom.isEmpty():
                    slice_area, _ = self._calculate_area(slice_geom, layer_crs)
                    target_row_area = target_area * cols
                    if slice_area and slice_area < target_row_area:
                        y_low = y_mid
                    else:
                        y_high = y_mid
                else:
                    y_low = y_mid
            
            y_slices.append((y_low + y_high) / 2.0)
        
        y_slices.append(y_max)
        
        # For each row, find vertical slice positions
        for row_idx in range(rows):
            y_start = y_slices[row_idx]
            y_end = y_slices[row_idx + 1]
            
            # Create row polygon
            row_rect = QgsGeometry.fromRect(
                QgsRectangle(bbox.xMinimum(), y_start, bbox.xMaximum(), y_end)
            )
            row_geom = geometry.intersection(row_rect)
            
            if row_geom and row_geom.isEmpty():
                continue
            
            # Get row bounding box
            row_bbox = row_geom.boundingBox()
            x_min = row_bbox.xMinimum()
            x_max = row_bbox.xMaximum()
            
            # Find vertical slice positions for this row
            x_slices = [x_min]
            row_area, _ = self._calculate_area(row_geom, layer_crs)
            if row_area is None or row_area <= 0:
                continue
            
            target_col_area = row_area / cols
            col_area_tolerance = target_col_area * 0.000001
            x_coord_tolerance = (x_max - x_min) * 1e-10
            
            for i in range(1, cols):
                x_low = x_slices[-1]
                x_high = x_max
                max_iterations = 100  # Prevent infinite loops
                iteration = 0
                
                while iteration < max_iterations:
                    x_mid = (x_low + x_high) / 2.0
                    
                    # Check coordinate tolerance
                    if x_high - x_low < x_coord_tolerance:
                        break
                    
                    # Create column slice
                    col_rect = QgsGeometry.fromRect(
                        QgsRectangle(x_slices[-1], y_start, x_mid, y_end)
                    )
                    col_geom = row_geom.intersection(col_rect)
                    
                    if col_geom and not col_geom.isEmpty():
                        col_area, _ = self._calculate_area(col_geom, layer_crs)
                        if col_area:
                            area_diff = abs(col_area - target_col_area)
                            # Check area tolerance
                            if area_diff < col_area_tolerance:
                                break
                            if col_area < target_col_area:
                                x_low = x_mid
                            else:
                                x_high = x_mid
                        else:
                            x_low = x_mid
                    else:
                        x_low = x_mid
                    
                    iteration += 1
                
                x_slices.append((x_low + x_high) / 2.0)
            
            x_slices.append(x_max)
            
            # Create grid cells for this row
            for col_idx in range(cols):
                x_start = x_slices[col_idx]
                x_end = x_slices[col_idx + 1]
                
                cell_rect = QgsGeometry.fromRect(
                    QgsRectangle(x_start, y_start, x_end, y_end)
                )
                cell_geom = row_geom.intersection(cell_rect)
                
                if cell_geom and not cell_geom.isEmpty():
                    if cell_geom.isMultipart():
                        parts = cell_geom.asGeometryCollection()
                        for part in parts:
                            if part and not part.isEmpty() and part.type() == QgsWkbTypes.PolygonGeometry:
                                divided_polygons.append(part)
                    else:
                        divided_polygons.append(cell_geom)
        
        return divided_polygons
    
    def _create_divided_layer(self, layer_name, crs, source_fields=None):
        """
        Create a polygon layer for divided polygons.
        
        Args:
            layer_name (str): Name for the layer
            crs: Coordinate reference system
            source_fields (QgsFields): Source layer fields to copy (optional)
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            # Create memory layer
            layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            # Copy fields from source if provided
            if source_fields:
                fields_to_add = []
                for field in source_fields:
                    fields_to_add.append(field)
                layer.dataProvider().addAttributes(fields_to_add)
                layer.updateFields()
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create divided polygon layer: {str(e)}")
            return None

    def _build_layer_definition(self, layer, feature_backups=None):
        """
        Build a layer definition dict compatible with the create_layer undo handler.
        Includes fields (with qmeta_type) and features (geometry WKB base64 + attributes).
        """
        try:
            from base64 import b64encode
            from qgis.core import QgsWkbTypes

            ld = {
                'layer_name': layer.name(),
                'crs': layer.crs().authid() if layer.crs().isValid() else '',
                'geometry_type': QgsWkbTypes.displayString(layer.wkbType()),
                'fields': [],
                'features': []
            }

            # Fields
            for f in layer.fields():
                try:
                    qmeta = f.type()
                except Exception:
                    qmeta = None
                ld['fields'].append({'name': f.name(), 'qmeta_type': qmeta})

            # Features: prefer provided backups, otherwise build from layer features
            if feature_backups:
                ld['features'] = feature_backups
            else:
                # Build backups for all features in layer
                for feat in layer.getFeatures():
                    try:
                        fb = self.create_feature_backup(feat, layer)
                        ld['features'].append(fb)
                    except Exception:
                        continue

            return ld
        except Exception:
            return None
    
    def execute(self, context):
        """Execute the divide polygon into equal areas action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
            layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
            add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
            copy_attributes = bool(self.get_setting('copy_attributes', schema['copy_attributes']['default']))
            default_divisions = int(self.get_setting('default_divisions', schema['default_divisions']['default']))
            default_method = str(self.get_setting('default_division_method', schema['default_division_method']['default']))
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
        
        # Get the clicked feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Validate that this is a polygon layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return
        
        try:
            # Get feature geometry
            geometry = feature.geometry()
            if not geometry or geometry.isEmpty():
                self.show_error("Error", "Feature has no valid geometry")
                return
            
            # Calculate area for dialog
            total_area, _ = self._calculate_area(geometry, layer.crs())
            if total_area is None:
                self.show_error("Error", "Failed to calculate polygon area")
                return
            
            # Show input dialog
            dialog = DivisionInputDialog(None, default_divisions, default_method, total_area)
            if dialog.exec_() != QDialog.Accepted:
                return
            
            division_method = dialog.get_method()
            num_divisions = dialog.get_divisions()
            grid_rows = dialog.get_grid_rows() if division_method == 'grid' else None
            grid_cols = dialog.get_grid_cols() if division_method == 'grid' else None
            
            # Divide the polygon
            divided_geometries = self._divide_polygon(
                geometry, num_divisions, division_method, layer.crs(), grid_rows, grid_cols
            )
            
            if not divided_geometries:
                self.show_error("Error", "Failed to divide polygon into equal areas")
                return
            
            # Generate output layer name
            source_layer_name = layer.name()
            feature_id = feature.id()
            output_layer_name = self._generate_output_layer_name(layer_name_template, feature_id, source_layer_name)
            
            # Determine output path based on storage type
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Divided Polygon Layer As",
                    "",
                    "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                output_path = save_path
            else:
                output_path = None  # Temporary layer
            
            # Create divided layer
            source_fields = layer.fields() if copy_attributes else None
            divided_layer = self._create_divided_layer(
                output_layer_name,
                layer.crs(),
                source_fields
            )
            
            if not divided_layer:
                self.show_error("Error", "Failed to create divided polygon layer")
                return
            
            # Add divided polygons to layer using provider (capture assigned FIDs)
            provider = divided_layer.dataProvider()

            new_features = []
            for i, div_geom in enumerate(divided_geometries):
                new_feature = QgsFeature()
                new_feature.setGeometry(div_geom)

                # Copy attributes if requested
                if copy_attributes:
                    attrs = list(feature.attributes())
                    new_feature.setAttributes(attrs)
                else:
                    new_feature.setAttributes([])

                new_features.append(new_feature)

            # Attempt to add features via provider so IDs are assigned
            try:
                provider.addFeatures(new_features)
            except Exception:
                # Fallback: try layer.addFeature per feature
                for nf in new_features:
                    try:
                        divided_layer.addFeature(nf)
                    except Exception:
                        pass

            divided_layer.updateExtents()

            # Build feature backups for history (use actual features from layer)
            feature_backups = []
            # Try to map using ids from new_features when available
            seen_fids = set()
            for nf in new_features:
                fid = None
                try:
                    fid = int(nf.id())
                except Exception:
                    fid = None

                if fid is not None and fid >= 0:
                    try:
                        f_real = divided_layer.getFeature(fid)
                        if f_real:
                            fb = self.create_feature_backup(f_real, divided_layer)
                            feature_backups.append(fb)
                            seen_fids.add(fid)
                    except Exception:
                        pass

            # Fallback: find remaining features by geometry matching (if any)
            if len(feature_backups) < len(new_features):
                try:
                    # Build a set of WKB for newly created geometries
                    new_wkbs = [g.asWkb() for g in divided_geometries]
                    matched = 0
                    for feat in divided_layer.getFeatures():
                        if feat.id() in seen_fids:
                            continue
                        try:
                            if feat.geometry() and feat.geometry().asWkb() in new_wkbs:
                                fb = self.create_feature_backup(feat, divided_layer)
                                feature_backups.append(fb)
                                matched += 1
                                if matched >= (len(new_features) - len(seen_fids)):
                                    break
                        except Exception:
                            continue
                except Exception:
                    pass
            
            # Save to file if permanent
            if layer_storage_type == 'permanent' and output_path:
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    divided_layer,
                    output_path,
                    "UTF-8",
                    divided_layer.crs(),
                    "GPKG" if output_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load saved layer
                saved_layer = QgsVectorLayer(output_path, output_layer_name, "ogr")
                if saved_layer.isValid():
                    divided_layer = saved_layer
                else:
                    self.show_error("Error", "Failed to load saved layer")
                    return
            
            # Add to project if requested
            if add_to_project:
                QgsProject.instance().addMapLayer(divided_layer)
            
            # Zoom to layer if requested
            if zoom_to_layer and canvas:
                try:
                    # Get layer extent
                    layer_extent = divided_layer.extent()
                    
                    # Transform extent to canvas CRS if needed
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = divided_layer.crs()
                    
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
            
            # Record to history: create_layer with layer definition so it can be undone
            try:
                # Build layer definition including fields and feature backups
                layer_def = self._build_layer_definition(divided_layer, feature_backups)
                layers_desc = [self.create_layer_descriptor(divided_layer)]
                undo_payload = {'layer_definitions': [layer_def]} if layer_def is not None else None

                if undo_payload is not None:
                    self.record_to_history(
                        description=f"Divided polygon {feature.id()} into {len(divided_geometries)} parts",
                        undo_type='create_layer',
                        can_undo=True,
                        undo_payload=undo_payload,
                        layers=layers_desc,
                        features=feature_backups,
                        meta={'division_method': division_method, 'num_parts': len(divided_geometries)}
                    )
            except Exception:
                pass

            # Show success message if requested
            if show_success_message:
                storage_info = "saved to disk" if layer_storage_type == 'permanent' else "created as temporary layer"

                method_names = {
                    'vertical': 'vertical stripes',
                    'horizontal': 'horizontal stripes',
                    'radial': 'radial slices',
                    'grid': 'grid cells'
                }
                method_name = method_names.get(division_method, 'parts')

                if division_method == 'grid':
                    message = f"Polygon divided into {grid_rows}×{grid_cols} grid ({grid_rows * grid_cols} equal-area cells).\n\n"
                else:
                    message = f"Polygon divided into {num_divisions} equal-area {method_name}.\n\n"

                message += f"Divided layer '{output_layer_name}' {storage_info} successfully.\n"
                message += f"Created {len(divided_geometries)} polygon features."

                self.show_info("Polygon Divided", message)
        
        except Exception as e:
            self.show_error("Error", f"Failed to divide polygon: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
divide_polygon_into_equal_areas = DividePolygonIntoEqualAreasAction()

