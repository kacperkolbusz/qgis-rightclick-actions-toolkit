"""
Create Line Chart for Point Layer Action for Right-click Utilities and Shortcuts Hub

Creates a line chart visualization of numeric attributes for point features.
Allows users to select two numeric fields to visualize, displaying trends and relationships over an ordered sequence.
Supports exporting charts, visual presets, and customization options.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                QLabel, QComboBox, QSizePolicy, QWidget, QFileDialog,
                                QGroupBox, QRadioButton, QCheckBox, QSpinBox, QDoubleSpinBox,
                                QToolButton, QMenu, QAction, QGridLayout, QLineEdit, QColorDialog, QScrollArea)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.utils import iface
from ..history_manager import get_history_manager
from qgis.core import QgsWkbTypes
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.style as mplstyle
import numpy as np
import os
from datetime import datetime


class LineChartDialog(QDialog):
    """Dialog for displaying line charts."""
    
    def __init__(self, layer, fields, settings, parent=None):
        """
        Initialize the line chart dialog.
        
        Args:
            layer: The QGIS vector layer containing the features
            fields: List of numeric field names available for plotting
            settings: Dictionary of settings for the chart
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Line Chart")
        self.setModal(True)
        
        # Set dialog size to match QGIS main window size
        try:
            main_window = iface.mainWindow()
            if main_window:
                qgis_size = main_window.size()
                self.resize(qgis_size.width(), qgis_size.height())
            else:
                self.resize(1200, 800)
        except:
            self.resize(1200, 800)
        
        self.layer = layer
        self.fields = fields
        self.settings = settings
        
        # Data storage
        self.x_values = []
        self.y_values = []
        self.feature_ids = []
        self.x_field_name = ""
        self.y_field_name = ""
        
        # Chart style settings
        self.style_preset = self.settings.get('style_preset', 'default')
        self.line_color = self.settings.get('line_color', '#1f77b4')
        self.line_width = self.settings.get('line_width', 2)
        self.marker_style = self.settings.get('marker_style', 'o')
        self.marker_size = self.settings.get('marker_size', 6)
        self.show_markers = self.settings.get('show_markers', True)
        self.show_grid = self.settings.get('show_grid', True)
        self.show_labels = self.settings.get('show_labels', False)
        self.sort_by_x = self.settings.get('sort_by_x', True)
        
        # Axis range settings (user-controlled in dialog)
        self.use_custom_x_range = False
        self.x_min = 0.0
        self.x_max = 100.0
        self.use_custom_y_range = False
        self.y_min = 0.0
        self.y_max = 100.0
        
        # Advanced style settings
        self.line_style = '-'  # '-', '--', '-.', ':'
        self.fill_area = False
        self.fill_alpha = 0.3
        self.title_font_size = 14
        self.axis_label_font_size = 12
        self.tick_label_font_size = 10
        self.figure_width = 8.0
        self.figure_height = 6.0
        
        # Customizable chart labels
        self.chart_title = self.settings.get('chart_title', '')
        self.x_axis_label = self.settings.get('x_axis_label', '')
        self.y_axis_label = self.settings.get('y_axis_label', '')
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Create scroll area for the entire dialog
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)  # Set to False to enable scrolling
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Create content widget
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        content_widget.setMinimumSize(800, 600)  # Set minimum size to ensure scrolling works
        
        # Title
        title_label = QLabel(f"Line Chart for Layer: {self.layer.name()}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        main_layout.addWidget(title_label)
        
        # Control panel (top section)
        control_panel = QHBoxLayout()
        
        # Field selection
        field_group = QGroupBox("Field Selection")
        field_layout = QVBoxLayout(field_group)
        
        # X-axis field
        x_field_layout = QHBoxLayout()
        x_field_layout.addWidget(QLabel("X-axis field:"))
        self.x_field_combo = QComboBox()
        self.x_field_combo.addItem("-- Select Field --")
        self.x_field_combo.addItems(self.fields)
        self.x_field_combo.currentTextChanged.connect(self.update_data_and_chart)
        x_field_layout.addWidget(self.x_field_combo)
        field_layout.addLayout(x_field_layout)
        
        # Y-axis field
        y_field_layout = QHBoxLayout()
        y_field_layout.addWidget(QLabel("Y-axis field:"))
        self.y_field_combo = QComboBox()
        self.y_field_combo.addItem("-- Select Field --")
        self.y_field_combo.addItems(self.fields)
        self.y_field_combo.currentTextChanged.connect(self.update_data_and_chart)
        y_field_layout.addWidget(self.y_field_combo)
        field_layout.addLayout(y_field_layout)
        
        control_panel.addWidget(field_group)
        
        # Display options
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)
        
        # Sort by X
        self.sort_by_x_check = QCheckBox("Sort by X-axis")
        self.sort_by_x_check.setChecked(self.sort_by_x)
        self.sort_by_x_check.toggled.connect(self.set_sort_by_x)
        display_layout.addWidget(self.sort_by_x_check)
        
        # Show labels
        self.show_labels_check = QCheckBox("Show feature labels")
        self.show_labels_check.setChecked(self.show_labels)
        self.show_labels_check.toggled.connect(self.set_show_labels)
        display_layout.addWidget(self.show_labels_check)
        
        control_panel.addWidget(display_group)
        
        # Style options
        style_group = QGroupBox("Style")
        style_layout = QVBoxLayout(style_group)
        
        # Style presets
        style_preset_layout = QHBoxLayout()
        style_preset_layout.addWidget(QLabel("Preset:"))
        self.style_preset_combo = QComboBox()
        self.style_preset_combo.addItems(['default', 'classic', 'bmh', 'fivethirtyeight'])
        self.style_preset_combo.setCurrentText(self.style_preset)
        self.style_preset_combo.currentTextChanged.connect(self.set_style_preset)
        style_preset_layout.addWidget(self.style_preset_combo)
        style_layout.addLayout(style_preset_layout)
        
        # Line color picker
        line_color_layout = QHBoxLayout()
        line_color_layout.addWidget(QLabel("Line color:"))
        self.line_color_btn = QPushButton()
        color = QColor(self.line_color)
        self.line_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
        self.line_color_btn.setText(color.name())
        self.line_color_btn.clicked.connect(self.choose_line_color)
        line_color_layout.addWidget(self.line_color_btn)
        style_layout.addLayout(line_color_layout)
        
        # Line width
        line_width_layout = QHBoxLayout()
        line_width_layout.addWidget(QLabel("Line width:"))
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(self.line_width)
        self.line_width_spin.valueChanged.connect(self.set_line_width)
        line_width_layout.addWidget(self.line_width_spin)
        line_width_layout.addStretch()
        style_layout.addLayout(line_width_layout)
        
        # Show markers
        self.show_markers_check = QCheckBox("Show markers")
        self.show_markers_check.setChecked(self.show_markers)
        self.show_markers_check.toggled.connect(self.set_show_markers)
        style_layout.addWidget(self.show_markers_check)
        
        # Marker style
        marker_style_layout = QHBoxLayout()
        marker_style_layout.addWidget(QLabel("Marker style:"))
        self.marker_style_combo = QComboBox()
        self.marker_style_combo.addItems(['o', 's', '^', 'v', 'D', 'x', '+', '*'])
        self.marker_style_combo.setCurrentText(self.marker_style)
        self.marker_style_combo.setEnabled(self.show_markers)
        self.marker_style_combo.currentTextChanged.connect(self.set_marker_style)
        marker_style_layout.addWidget(self.marker_style_combo)
        style_layout.addLayout(marker_style_layout)
        
        # Marker size
        marker_size_layout = QHBoxLayout()
        marker_size_layout.addWidget(QLabel("Marker size:"))
        self.marker_size_spin = QSpinBox()
        self.marker_size_spin.setRange(1, 20)
        self.marker_size_spin.setValue(self.marker_size)
        self.marker_size_spin.setEnabled(self.show_markers)
        self.marker_size_spin.valueChanged.connect(self.set_marker_size)
        marker_size_layout.addWidget(self.marker_size_spin)
        marker_size_layout.addStretch()
        style_layout.addLayout(marker_size_layout)
        
        # Grid lines
        self.show_grid_check = QCheckBox("Show grid lines")
        self.show_grid_check.setChecked(self.show_grid)
        self.show_grid_check.toggled.connect(self.set_show_grid)
        style_layout.addWidget(self.show_grid_check)
        
        control_panel.addWidget(style_group)
        
        # Advanced options
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(advanced_group)
        
        # Line style
        line_style_layout = QHBoxLayout()
        line_style_layout.addWidget(QLabel("Line style:"))
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(['-', '--', '-.', ':'])
        self.line_style_combo.setCurrentText(self.line_style)
        self.line_style_combo.currentTextChanged.connect(self.set_line_style)
        line_style_layout.addWidget(self.line_style_combo)
        advanced_layout.addLayout(line_style_layout)
        
        # Fill area under line
        self.fill_area_check = QCheckBox("Fill area under line")
        self.fill_area_check.setChecked(self.fill_area)
        self.fill_area_check.toggled.connect(self.set_fill_area)
        advanced_layout.addWidget(self.fill_area_check)
        
        # Fill alpha
        fill_alpha_layout = QHBoxLayout()
        fill_alpha_layout.addWidget(QLabel("Fill transparency:"))
        self.fill_alpha_spin = QDoubleSpinBox()
        self.fill_alpha_spin.setRange(0.0, 1.0)
        self.fill_alpha_spin.setDecimals(2)
        self.fill_alpha_spin.setSingleStep(0.1)
        self.fill_alpha_spin.setValue(self.fill_alpha)
        self.fill_alpha_spin.setEnabled(self.fill_area)
        self.fill_alpha_spin.valueChanged.connect(self.set_fill_alpha)
        fill_alpha_layout.addWidget(self.fill_alpha_spin)
        fill_alpha_layout.addStretch()
        advanced_layout.addLayout(fill_alpha_layout)
        
        # Font sizes
        title_font_layout = QHBoxLayout()
        title_font_layout.addWidget(QLabel("Title font size:"))
        self.title_font_size_spin = QSpinBox()
        self.title_font_size_spin.setRange(8, 24)
        self.title_font_size_spin.setValue(self.title_font_size)
        self.title_font_size_spin.valueChanged.connect(self.set_title_font_size)
        title_font_layout.addWidget(self.title_font_size_spin)
        title_font_layout.addStretch()
        advanced_layout.addLayout(title_font_layout)
        
        axis_font_layout = QHBoxLayout()
        axis_font_layout.addWidget(QLabel("Axis label font size:"))
        self.axis_label_font_size_spin = QSpinBox()
        self.axis_label_font_size_spin.setRange(8, 20)
        self.axis_label_font_size_spin.setValue(self.axis_label_font_size)
        self.axis_label_font_size_spin.valueChanged.connect(self.set_axis_label_font_size)
        axis_font_layout.addWidget(self.axis_label_font_size_spin)
        axis_font_layout.addStretch()
        advanced_layout.addLayout(axis_font_layout)
        
        tick_font_layout = QHBoxLayout()
        tick_font_layout.addWidget(QLabel("Tick label font size:"))
        self.tick_label_font_size_spin = QSpinBox()
        self.tick_label_font_size_spin.setRange(6, 16)
        self.tick_label_font_size_spin.setValue(self.tick_label_font_size)
        self.tick_label_font_size_spin.valueChanged.connect(self.set_tick_label_font_size)
        tick_font_layout.addWidget(self.tick_label_font_size_spin)
        tick_font_layout.addStretch()
        advanced_layout.addLayout(tick_font_layout)
        
        # Figure size
        fig_width_layout = QHBoxLayout()
        fig_width_layout.addWidget(QLabel("Figure width:"))
        self.figure_width_spin = QDoubleSpinBox()
        self.figure_width_spin.setRange(4.0, 16.0)
        self.figure_width_spin.setDecimals(1)
        self.figure_width_spin.setValue(self.figure_width)
        self.figure_width_spin.setSuffix(" in")
        self.figure_width_spin.valueChanged.connect(self.set_figure_width)
        fig_width_layout.addWidget(self.figure_width_spin)
        fig_width_layout.addStretch()
        advanced_layout.addLayout(fig_width_layout)
        
        fig_height_layout = QHBoxLayout()
        fig_height_layout.addWidget(QLabel("Figure height:"))
        self.figure_height_spin = QDoubleSpinBox()
        self.figure_height_spin.setRange(3.0, 12.0)
        self.figure_height_spin.setDecimals(1)
        self.figure_height_spin.setValue(self.figure_height)
        self.figure_height_spin.setSuffix(" in")
        self.figure_height_spin.valueChanged.connect(self.set_figure_height)
        fig_height_layout.addWidget(self.figure_height_spin)
        fig_height_layout.addStretch()
        advanced_layout.addLayout(fig_height_layout)
        
        control_panel.addWidget(advanced_group)
        
        # Axis range options
        axis_range_group = QGroupBox("Axis Ranges")
        axis_range_layout = QVBoxLayout(axis_range_group)
        
        # X-axis range
        x_range_layout = QHBoxLayout()
        self.use_custom_x_check = QCheckBox("Custom X-axis range:")
        self.use_custom_x_check.setChecked(self.use_custom_x_range)
        self.use_custom_x_check.toggled.connect(self.set_use_custom_x_range)
        x_range_layout.addWidget(self.use_custom_x_check)
        
        x_range_layout.addWidget(QLabel("Min:"))
        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setRange(-1000000, 1000000)
        self.x_min_spin.setDecimals(2)
        self.x_min_spin.setValue(self.x_min)
        self.x_min_spin.setEnabled(self.use_custom_x_range)
        self.x_min_spin.valueChanged.connect(self.set_x_min)
        x_range_layout.addWidget(self.x_min_spin)
        
        x_range_layout.addWidget(QLabel("Max:"))
        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setRange(-1000000, 1000000)
        self.x_max_spin.setDecimals(2)
        self.x_max_spin.setValue(self.x_max)
        self.x_max_spin.setEnabled(self.use_custom_x_range)
        self.x_max_spin.valueChanged.connect(self.set_x_max)
        x_range_layout.addWidget(self.x_max_spin)
        axis_range_layout.addLayout(x_range_layout)
        
        # Y-axis range
        y_range_layout = QHBoxLayout()
        self.use_custom_y_check = QCheckBox("Custom Y-axis range:")
        self.use_custom_y_check.setChecked(self.use_custom_y_range)
        self.use_custom_y_check.toggled.connect(self.set_use_custom_y_range)
        y_range_layout.addWidget(self.use_custom_y_check)
        
        y_range_layout.addWidget(QLabel("Min:"))
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-1000000, 1000000)
        self.y_min_spin.setDecimals(2)
        self.y_min_spin.setValue(self.y_min)
        self.y_min_spin.setEnabled(self.use_custom_y_range)
        self.y_min_spin.valueChanged.connect(self.set_y_min)
        y_range_layout.addWidget(self.y_min_spin)
        
        y_range_layout.addWidget(QLabel("Max:"))
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-1000000, 1000000)
        self.y_max_spin.setDecimals(2)
        self.y_max_spin.setValue(self.y_max)
        self.y_max_spin.setEnabled(self.use_custom_y_range)
        self.y_max_spin.valueChanged.connect(self.set_y_max)
        y_range_layout.addWidget(self.y_max_spin)
        axis_range_layout.addLayout(y_range_layout)
        
        control_panel.addWidget(axis_range_group)
        
        # Chart labels
        labels_group = QGroupBox("Chart Labels")
        labels_layout = QVBoxLayout(labels_group)
        
        # Chart title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Leave empty to use field names")
        self.title_edit.setText(self.chart_title)
        self.title_edit.textChanged.connect(self.set_chart_title)
        title_layout.addWidget(self.title_edit)
        labels_layout.addLayout(title_layout)
        
        # X-axis label
        x_label_layout = QHBoxLayout()
        x_label_layout.addWidget(QLabel("X-axis:"))
        self.x_label_edit = QLineEdit()
        self.x_label_edit.setPlaceholderText("Leave empty to use field name")
        self.x_label_edit.setText(self.x_axis_label)
        self.x_label_edit.textChanged.connect(self.set_x_axis_label)
        x_label_layout.addWidget(self.x_label_edit)
        labels_layout.addLayout(x_label_layout)
        
        # Y-axis label
        y_label_layout = QHBoxLayout()
        y_label_layout.addWidget(QLabel("Y-axis:"))
        self.y_label_edit = QLineEdit()
        self.y_label_edit.setPlaceholderText("Leave empty to use field name")
        self.y_label_edit.setText(self.y_axis_label)
        self.y_label_edit.textChanged.connect(self.set_y_axis_label)
        y_label_layout.addWidget(self.y_label_edit)
        labels_layout.addLayout(y_label_layout)
        
        control_panel.addWidget(labels_group)
        
        main_layout.addLayout(control_panel)
        
        # Chart area
        self.chart_widget = QWidget()
        self.chart_layout = QVBoxLayout(self.chart_widget)
        
        # Create matplotlib figure
        self.figure = Figure(figsize=(self.figure_width, self.figure_height), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chart_layout.addWidget(self.canvas)
        
        main_layout.addWidget(self.chart_widget)
        
        # Bottom button bar
        button_layout = QHBoxLayout()
        
        # Export button with dropdown menu
        export_btn = QToolButton()
        export_btn.setText("Export")
        export_menu = QMenu()
        
        export_png_action = QAction("Export as PNG", self)
        export_png_action.triggered.connect(lambda: self.export_chart("png"))
        export_menu.addAction(export_png_action)
        
        export_jpg_action = QAction("Export as JPG", self)
        export_jpg_action.triggered.connect(lambda: self.export_chart("jpg"))
        export_menu.addAction(export_jpg_action)
        
        export_pdf_action = QAction("Export as PDF", self)
        export_pdf_action.triggered.connect(lambda: self.export_chart("pdf"))
        export_menu.addAction(export_pdf_action)
        
        export_svg_action = QAction("Export as SVG", self)
        export_svg_action.triggered.connect(lambda: self.export_chart("svg"))
        export_menu.addAction(export_svg_action)
        
        export_btn.setMenu(export_menu)
        export_btn.setPopupMode(QToolButton.InstantPopup)
        button_layout.addWidget(export_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        # Set content widget to scroll area
        self.scroll_area.setWidget(content_widget)
        self.scroll_area.setWidgetResizable(False)  # Ensure scrolling works
        
        # Set scroll area as main layout
        dialog_layout = QVBoxLayout()
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(self.scroll_area)
        self.setLayout(dialog_layout)
    
    def update_data_and_chart(self, field_name=None):
        """
        Update data and chart with the selected fields.
        
        Args:
            field_name: The field name that changed (optional, uses current selections if None)
        """
        x_field_name = self.x_field_combo.currentText()
        y_field_name = self.y_field_combo.currentText()
        
        # Skip if fields not selected
        if not x_field_name or x_field_name == "-- Select Field --":
            return
        if not y_field_name or y_field_name == "-- Select Field --":
            return
        
        self.x_field_name = x_field_name
        self.y_field_name = y_field_name
        
        # Get data from features
        data_points = []
        
        for feature in self.layer.getFeatures():
            x_value = feature[x_field_name]
            y_value = feature[y_field_name]
            
            # Handle NULL values - skip features with missing data
            if x_value is None or y_value is None:
                continue
            
            # Handle NaN/Inf for numeric values
            if isinstance(x_value, (int, float)) and (np.isnan(x_value) or np.isinf(x_value)):
                continue
            if isinstance(y_value, (int, float)) and (np.isnan(y_value) or np.isinf(y_value)):
                continue
            
            try:
                # Convert to float for plotting
                x_float = float(x_value)
                y_float = float(y_value)
                data_points.append({
                    'x': x_float,
                    'y': y_float,
                    'fid': str(feature.id())
                })
            except (ValueError, TypeError):
                # Skip non-numeric values
                continue
        
        # Sort by X if enabled
        if self.sort_by_x:
            data_points.sort(key=lambda p: p['x'])
        
        # Extract sorted values
        self.x_values = [p['x'] for p in data_points]
        self.y_values = [p['y'] for p in data_points]
        self.feature_ids = [p['fid'] for p in data_points]
        
        # Update default axis ranges (but don't override if user has custom ranges enabled)
        if not self.use_custom_x_range and self.x_values:
            x_padding = (max(self.x_values) - min(self.x_values)) * 0.1 if max(self.x_values) != min(self.x_values) else max(abs(min(self.x_values)), abs(max(self.x_values))) * 0.1 or 1
            self.x_min = min(self.x_values) - x_padding
            self.x_max = max(self.x_values) + x_padding
            self.x_min_spin.setValue(self.x_min)
            self.x_max_spin.setValue(self.x_max)
        
        if not self.use_custom_y_range and self.y_values:
            y_padding = (max(self.y_values) - min(self.y_values)) * 0.1 if max(self.y_values) != min(self.y_values) else max(abs(min(self.y_values)), abs(max(self.y_values))) * 0.1 or 1
            self.y_min = min(self.y_values) - y_padding
            self.y_max = max(self.y_values) + y_padding
            self.y_min_spin.setValue(self.y_min)
            self.y_max_spin.setValue(self.y_max)
        
        # Update the chart
        self.update_chart()
    
    def set_sort_by_x(self, sort):
        """Set whether to sort by X-axis."""
        self.sort_by_x = sort
        self.update_data_and_chart()
    
    def set_show_labels(self, show):
        """Set whether to show feature labels."""
        self.show_labels = show
        self.update_chart()
    
    def set_style_preset(self, preset):
        """Set the style preset for the chart."""
        self.style_preset = preset
        self.update_chart()
    
    def set_line_color(self, color):
        """Set the line color."""
        self.line_color = color
        self.update_chart()
    
    def choose_line_color(self):
        """Open color dialog to choose line color."""
        color = QColorDialog.getColor(QColor(self.line_color), self, "Choose Line Color")
        if color.isValid():
            self.line_color = color.name()
            self.line_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
            self.line_color_btn.setText(color.name())
            self.update_chart()
    
    def set_line_width(self, width):
        """Set the line width."""
        self.line_width = width
        self.update_chart()
    
    def set_show_markers(self, show):
        """Set whether to show markers."""
        self.show_markers = show
        self.marker_style_combo.setEnabled(show)
        self.marker_size_spin.setEnabled(show)
        self.update_chart()
    
    def set_marker_style(self, style):
        """Set the marker style."""
        self.marker_style = style
        self.update_chart()
    
    def set_marker_size(self, size):
        """Set the marker size."""
        self.marker_size = size
        self.update_chart()
    
    def set_show_grid(self, show):
        """Set whether to show grid lines."""
        self.show_grid = show
        self.update_chart()
    
    def set_use_custom_x_range(self, use):
        """Set whether to use custom x-axis range."""
        self.use_custom_x_range = use
        self.x_min_spin.setEnabled(use)
        self.x_max_spin.setEnabled(use)
        self.update_chart()
    
    def set_x_min(self, value):
        """Set the minimum x-axis value."""
        self.x_min = value
        self.update_chart()
    
    def set_x_max(self, value):
        """Set the maximum x-axis value."""
        self.x_max = value
        self.update_chart()
    
    def set_use_custom_y_range(self, use):
        """Set whether to use custom y-axis range."""
        self.use_custom_y_range = use
        self.y_min_spin.setEnabled(use)
        self.y_max_spin.setEnabled(use)
        self.update_chart()
    
    def set_y_min(self, value):
        """Set the minimum y-axis value."""
        self.y_min = value
        self.update_chart()
    
    def set_y_max(self, value):
        """Set the maximum y-axis value."""
        self.y_max = value
        self.update_chart()
    
    def set_chart_title(self, title):
        """Set the chart title."""
        self.chart_title = title
        self.update_chart()
    
    def set_x_axis_label(self, label):
        """Set the x-axis label."""
        self.x_axis_label = label
        self.update_chart()
    
    def set_y_axis_label(self, label):
        """Set the y-axis label."""
        self.y_axis_label = label
        self.update_chart()
    
    def set_line_style(self, style):
        """Set the line style."""
        self.line_style = style
        self.update_chart()
    
    def set_fill_area(self, fill):
        """Set whether to fill area under line."""
        self.fill_area = fill
        self.fill_alpha_spin.setEnabled(fill)
        self.update_chart()
    
    def set_fill_alpha(self, alpha):
        """Set the fill transparency."""
        self.fill_alpha = alpha
        self.update_chart()
    
    def set_title_font_size(self, size):
        """Set the title font size."""
        self.title_font_size = size
        self.update_chart()
    
    def set_axis_label_font_size(self, size):
        """Set the axis label font size."""
        self.axis_label_font_size = size
        self.update_chart()
    
    def set_tick_label_font_size(self, size):
        """Set the tick label font size."""
        self.tick_label_font_size = size
        self.update_chart()
    
    def set_figure_width(self, width):
        """Set the figure width."""
        self.figure_width = width
        self.update_figure_size()
        self.update_chart()
    
    def set_figure_height(self, height):
        """Set the figure height."""
        self.figure_height = height
        self.update_figure_size()
        self.update_chart()
    
    def update_figure_size(self):
        """Update the figure size."""
        self.figure.set_size_inches(self.figure_width, self.figure_height)
        self.canvas.draw()
    
    def update_chart(self):
        """Update the chart with current settings."""
        if not self.x_field_name or not self.y_field_name or not self.x_values or not self.y_values:
            return
        
        # Apply style preset
        with plt.style.context(self.style_preset):
            # Clear the figure
            self.figure.clear()
            
            # Create subplot
            ax = self.figure.add_subplot(111)
            
            # Prepare marker style
            marker = self.marker_style if self.show_markers else None
            
            # Create line chart with style
            ax.plot(self.x_values, self.y_values, 
                   color=self.line_color, 
                   linewidth=self.line_width,
                   linestyle=self.line_style,
                   marker=marker,
                   markersize=self.marker_size,
                   markerfacecolor=self.line_color,
                   markeredgecolor='black',
                   markeredgewidth=0.5)
            
            # Fill area under line if enabled
            if self.fill_area:
                ax.fill_between(self.x_values, self.y_values, alpha=self.fill_alpha, color=self.line_color)
            
            # Add feature labels if enabled
            if self.show_labels:
                for i, (x, y, fid) in enumerate(zip(self.x_values, self.y_values, self.feature_ids)):
                    ax.annotate(fid, (x, y), xytext=(5, 5), textcoords='offset points', fontsize=8)
            
            # Set labels and title using custom labels or defaults
            title = self.chart_title if self.chart_title else f"{self.y_field_name} vs {self.x_field_name}"
            x_label = self.x_axis_label if self.x_axis_label else self.x_field_name
            y_label = self.y_axis_label if self.y_axis_label else self.y_field_name
            
            ax.set_title(title, fontsize=self.title_font_size)
            ax.set_xlabel(x_label, fontsize=self.axis_label_font_size)
            ax.set_ylabel(y_label, fontsize=self.axis_label_font_size)
            ax.tick_params(labelsize=self.tick_label_font_size)
            
            # Set grid
            ax.grid(self.show_grid)
            
            # Set custom axis ranges if enabled
            if self.use_custom_x_range:
                ax.set_xlim(self.x_min, self.x_max)
            if self.use_custom_y_range:
                ax.set_ylim(self.y_min, self.y_max)
            
            # Adjust layout
            self.figure.tight_layout()
            
            # Refresh canvas
            self.canvas.draw()
    
    def export_chart(self, format_type):
        """
        Export the chart as an image file.
        
        Args:
            format_type: The file format to export (png, jpg, pdf, svg)
        """
        if not self.x_field_name or not self.y_field_name:
            return
        
        # Get the export directory from settings or use default
        settings = QSettings()
        last_dir = settings.value("RightClickUtilities/export_chart_dir", os.path.expanduser("~"))
        
        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{self.layer.name()}_{self.x_field_name}_vs_{self.y_field_name}_line_{timestamp}.{format_type}"
        
        # Show file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Chart", 
            os.path.join(last_dir, default_filename),
            f"{format_type.upper()} Files (*.{format_type})"
        )
        
        if file_path:
            # Save the directory for next time
            settings.setValue("RightClickUtilities/export_chart_dir", os.path.dirname(file_path))
            
            # Save the figure
            try:
                self.figure.savefig(file_path, format=format_type, dpi=300, bbox_inches='tight')
                # Show success message
                QLabel(f"Chart exported to {file_path}").setWindowTitle("Export Successful")
            except Exception as e:
                QLabel(f"Failed to export chart: {str(e)}").setWindowTitle("Export Failed")


class CreateLineChartPointAction(BaseAction):
    """Action to create line charts for point features."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_line_chart_point"
        self.name = "Create Line Chart"
        self.category = "Analysis"
        self.description = "Create a line chart visualization of numeric attributes for point features. Allows selection of two numeric fields to visualize, displaying trends and relationships over an ordered sequence. Supports exporting charts, visual presets, and customization options."
        self.enabled = True
        
        # Action scoping - works on layers (affects all features in layer)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with points
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    def supports_undo(self) -> bool:
        """This action is informational (creates a chart) and is NOT undoable."""
        return False

    def get_undo_category(self) -> str:
        """Return undo category for consistency with the guide: 'informational' (no undo)."""
        return 'informational'
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # Display settings
            'max_features_warning': {
                'type': 'int',
                'default': 1000,
                'label': 'Maximum Features Warning',
                'description': 'Show warning when attempting to chart layers with more features than this limit',
                'min': 10,
                'max': 10000,
                'step': 100,
            },
            'default_chart_width': {
                'type': 'int',
                'default': 800,
                'label': 'Default Chart Width',
                'description': 'Default width of the chart dialog in pixels',
                'min': 400,
                'max': 1600,
                'step': 50,
            },
            'default_chart_height': {
                'type': 'int',
                'default': 600,
                'label': 'Default Chart Height',
                'description': 'Default height of the chart dialog in pixels',
                'min': 300,
                'max': 1200,
                'step': 50,
            },
            
            # Style settings (defaults only - actual values controlled in dialog)
            'style_preset': {
                'type': 'choice',
                'default': 'default',
                'label': 'Default Style Preset',
                'description': 'Default visual style preset for the chart (can be changed in chart dialog)',
                'options': ['default', 'classic', 'bmh', 'fivethirtyeight'],
            },
            'line_color': {
                'type': 'color',
                'default': '#1f77b4',
                'label': 'Default Line Color',
                'description': 'Default color for the line in the chart (can be changed in chart dialog)',
            },
            'line_width': {
                'type': 'int',
                'default': 2,
                'label': 'Default Line Width',
                'description': 'Default width for the line in the chart (can be changed in chart dialog)',
                'min': 1,
                'max': 10,
                'step': 1,
            },
            'show_markers': {
                'type': 'bool',
                'default': True,
                'label': 'Default Show Markers',
                'description': 'Default setting for showing markers on data points (can be changed in chart dialog)',
            },
            'marker_style': {
                'type': 'choice',
                'default': 'o',
                'label': 'Default Marker Style',
                'description': 'Default marker style for data points (can be changed in chart dialog)',
                'options': ['o', 's', '^', 'v', 'D', 'x', '+', '*'],
            },
            'marker_size': {
                'type': 'int',
                'default': 6,
                'label': 'Default Marker Size',
                'description': 'Default size for markers (can be changed in chart dialog)',
                'min': 1,
                'max': 20,
                'step': 1,
            },
            'show_grid': {
                'type': 'bool',
                'default': True,
                'label': 'Default Show Grid Lines',
                'description': 'Default setting for showing grid lines (can be changed in chart dialog)',
            },
            'show_labels': {
                'type': 'bool',
                'default': False,
                'label': 'Default Show Labels',
                'description': 'Default setting for showing feature labels (can be changed in chart dialog)',
            },
            'sort_by_x': {
                'type': 'bool',
                'default': True,
                'label': 'Default Sort by X-axis',
                'description': 'Default setting for sorting data by X-axis values (can be changed in chart dialog)',
            },
            
            # Chart labels
            'chart_title': {
                'type': 'str',
                'default': '',
                'label': 'Default Chart Title',
                'description': 'Default title for the chart (leave empty to use field names)',
            },
            'x_axis_label': {
                'type': 'str',
                'default': '',
                'label': 'Default X-axis Label',
                'description': 'Default label for the x-axis (leave empty to use field name)',
            },
            'y_axis_label': {
                'type': 'str',
                'default': '',
                'label': 'Default Y-axis Label',
                'description': 'Default label for the y-axis (leave empty to use field name)',
            },
            
            # Export settings
            'default_export_format': {
                'type': 'choice',
                'default': 'png',
                'label': 'Default Export Format',
                'description': 'Default file format when exporting charts',
                'options': ['png', 'jpg', 'pdf', 'svg'],
            },
            'export_dpi': {
                'type': 'int',
                'default': 300,
                'label': 'Export DPI',
                'description': 'Resolution (dots per inch) for exported images',
                'min': 72,
                'max': 600,
                'step': 1,
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """Get a setting value for this action."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def execute(self, context):
        """Execute the create line chart action."""
        # Get settings with proper type conversion
        try:
            # Display settings
            max_features_warning = int(self.get_setting('max_features_warning', 1000))
            default_chart_width = int(self.get_setting('default_chart_width', 800))
            default_chart_height = int(self.get_setting('default_chart_height', 600))
            
            # Style settings
            style_preset = str(self.get_setting('style_preset', 'default'))
            line_color = str(self.get_setting('line_color', '#1f77b4'))
            line_width = int(self.get_setting('line_width', 2))
            show_markers = bool(self.get_setting('show_markers', True))
            marker_style = str(self.get_setting('marker_style', 'o'))
            marker_size = int(self.get_setting('marker_size', 6))
            show_grid = bool(self.get_setting('show_grid', True))
            show_labels = bool(self.get_setting('show_labels', False))
            sort_by_x = bool(self.get_setting('sort_by_x', True))
            
            # Chart labels
            chart_title = str(self.get_setting('chart_title', ''))
            x_axis_label = str(self.get_setting('x_axis_label', ''))
            y_axis_label = str(self.get_setting('y_axis_label', ''))
            
            # Export settings
            default_export_format = str(self.get_setting('default_export_format', 'png'))
            export_dpi = int(self.get_setting('export_dpi', 300))
            
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Verify it's a point layer
        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "This action only works with point layers")
            return
        
        # Check feature count
        feature_count = layer.featureCount()
        if feature_count == 0:
            self.show_warning("Empty Layer", "The selected layer has no features to chart.")
            return
        
        if feature_count > max_features_warning:
            if not self.confirm_action(
                "Large Layer Warning",
                f"The selected layer has {feature_count} features, which may make the chart crowded or slow to generate. Continue anyway?"
            ):
                return
        
        # Get numeric fields from the layer (line charts need numeric data)
        numeric_fields = []
        for field in layer.fields():
            if field.isNumeric():
                numeric_fields.append(field.name())
        
        if not numeric_fields:
            self.show_warning("No Numeric Fields", 
                             "The selected layer has no numeric fields to chart. Line charts require numeric fields for both X and Y axes.")
            return
        
        if len(numeric_fields) < 2:
            self.show_warning("Insufficient Fields", 
                             "The selected layer has only one numeric field. Line charts require at least two numeric fields (one for X-axis and one for Y-axis).")
            return
        
        # Collect all settings to pass to the dialog
        chart_settings = {
            'style_preset': style_preset,
            'line_color': line_color,
            'line_width': line_width,
            'show_markers': show_markers,
            'marker_style': marker_style,
            'marker_size': marker_size,
            'show_grid': show_grid,
            'show_labels': show_labels,
            'sort_by_x': sort_by_x,
            'default_export_format': default_export_format,
            'export_dpi': export_dpi,
            'chart_title': chart_title,
            'x_axis_label': x_axis_label,
            'y_axis_label': y_axis_label,
        }
        
        # Create and show the chart dialog
        try:
            dialog = LineChartDialog(layer, numeric_fields, chart_settings)
            dialog.resize(default_chart_width, default_chart_height)
            dialog.exec_()

            # Record informational history entry (non-undoable) so users can see the chart action in history
            try:
                hm = get_history_manager()
                desc = f"Displayed line chart for layer '{layer.name()}' ({len(numeric_fields)} numeric fields)"
                meta = {
                    'layer_id': layer.id(),
                    'layer_name': layer.name(),
                    'x_field': getattr(dialog, 'x_field_name', ''),
                    'y_field': getattr(dialog, 'y_field_name', ''),
                    'settings': chart_settings
                }
                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=desc,
                    meta=meta
                )
            except Exception:
                pass

        except Exception as e:
            self.show_error("Error", f"Failed to create line chart: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_line_chart_point_action = CreateLineChartPointAction()

