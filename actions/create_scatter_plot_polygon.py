"""
Create Scatter Plot for Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Creates a scatter plot visualization of numeric attributes for polygon features.
Allows users to select two numeric fields to visualize, displaying relationships between values.
Supports exporting plots, visual presets, and customization options.
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


class ScatterPlotDialog(QDialog):
    """Dialog for displaying scatter plots."""
    
    def __init__(self, layer, fields, settings, parent=None):
        """
        Initialize the scatter plot dialog.
        
        Args:
            layer: The QGIS vector layer containing the features
            fields: List of numeric field names available for plotting
            settings: Dictionary of settings for the plot
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Scatter Plot")
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
        
        # Plot style settings
        self.style_preset = self.settings.get('style_preset', 'default')
        self.point_color = self.settings.get('point_color', '#1f77b4')
        self.point_size = self.settings.get('point_size', 50)
        self.show_grid = self.settings.get('show_grid', True)
        self.show_labels = self.settings.get('show_labels', False)
        self.show_trend_line = self.settings.get('show_trend_line', False)
        
        # Axis range settings (user-controlled in dialog)
        self.use_custom_x_range = False
        self.x_min = 0.0
        self.x_max = 100.0
        self.use_custom_y_range = False
        self.y_min = 0.0
        self.y_max = 100.0
        
        # Advanced style settings
        self.point_alpha = 0.6
        self.point_edge_color = '#000000'
        self.point_edge_width = 0.5
        self.title_font_size = 14
        self.axis_label_font_size = 12
        self.tick_label_font_size = 10
        self.figure_width = 8.0
        self.figure_height = 6.0
        
        # Customizable plot labels
        self.plot_title = self.settings.get('plot_title', '')
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
        title_label = QLabel(f"Scatter Plot for Layer: {self.layer.name()}")
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
        self.x_field_combo.currentTextChanged.connect(self.update_data_and_plot)
        x_field_layout.addWidget(self.x_field_combo)
        field_layout.addLayout(x_field_layout)
        
        # Y-axis field
        y_field_layout = QHBoxLayout()
        y_field_layout.addWidget(QLabel("Y-axis field:"))
        self.y_field_combo = QComboBox()
        self.y_field_combo.addItem("-- Select Field --")
        self.y_field_combo.addItems(self.fields)
        self.y_field_combo.currentTextChanged.connect(self.update_data_and_plot)
        y_field_layout.addWidget(self.y_field_combo)
        field_layout.addLayout(y_field_layout)
        
        control_panel.addWidget(field_group)
        
        # Display options
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)
        
        # Show labels
        self.show_labels_check = QCheckBox("Show feature labels")
        self.show_labels_check.setChecked(self.show_labels)
        self.show_labels_check.toggled.connect(self.set_show_labels)
        display_layout.addWidget(self.show_labels_check)
        
        # Show trend line
        self.show_trend_line_check = QCheckBox("Show trend line")
        self.show_trend_line_check.setChecked(self.show_trend_line)
        self.show_trend_line_check.toggled.connect(self.set_show_trend_line)
        display_layout.addWidget(self.show_trend_line_check)
        
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
        
        # Point color picker
        point_color_layout = QHBoxLayout()
        point_color_layout.addWidget(QLabel("Point color:"))
        self.point_color_btn = QPushButton()
        color = QColor(self.point_color)
        self.point_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
        self.point_color_btn.setText(color.name())
        self.point_color_btn.clicked.connect(self.choose_point_color)
        point_color_layout.addWidget(self.point_color_btn)
        style_layout.addLayout(point_color_layout)
        
        # Point size
        point_size_layout = QHBoxLayout()
        point_size_layout.addWidget(QLabel("Point size:"))
        self.point_size_spin = QSpinBox()
        self.point_size_spin.setRange(1, 500)
        self.point_size_spin.setValue(self.point_size)
        self.point_size_spin.valueChanged.connect(self.set_point_size)
        point_size_layout.addWidget(self.point_size_spin)
        point_size_layout.addStretch()
        style_layout.addLayout(point_size_layout)
        
        # Grid lines
        self.show_grid_check = QCheckBox("Show grid lines")
        self.show_grid_check.setChecked(self.show_grid)
        self.show_grid_check.toggled.connect(self.set_show_grid)
        style_layout.addWidget(self.show_grid_check)
        
        control_panel.addWidget(style_group)
        
        # Advanced options
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(advanced_group)
        
        # Point transparency
        point_alpha_layout = QHBoxLayout()
        point_alpha_layout.addWidget(QLabel("Point transparency:"))
        self.point_alpha_spin = QDoubleSpinBox()
        self.point_alpha_spin.setRange(0.0, 1.0)
        self.point_alpha_spin.setDecimals(2)
        self.point_alpha_spin.setSingleStep(0.1)
        self.point_alpha_spin.setValue(self.point_alpha)
        self.point_alpha_spin.valueChanged.connect(self.set_point_alpha)
        point_alpha_layout.addWidget(self.point_alpha_spin)
        point_alpha_layout.addStretch()
        advanced_layout.addLayout(point_alpha_layout)
        
        # Point edge color
        point_edge_color_layout = QHBoxLayout()
        point_edge_color_layout.addWidget(QLabel("Point edge color:"))
        self.point_edge_color_btn = QPushButton()
        edge_color = QColor(self.point_edge_color)
        self.point_edge_color_btn.setStyleSheet(f"background-color: {edge_color.name()}; border: 1px solid #ccc; min-width: 80px;")
        self.point_edge_color_btn.setText(edge_color.name())
        self.point_edge_color_btn.clicked.connect(self.choose_point_edge_color)
        point_edge_color_layout.addWidget(self.point_edge_color_btn)
        advanced_layout.addLayout(point_edge_color_layout)
        
        # Point edge width
        point_edge_width_layout = QHBoxLayout()
        point_edge_width_layout.addWidget(QLabel("Point edge width:"))
        self.point_edge_width_spin = QDoubleSpinBox()
        self.point_edge_width_spin.setRange(0.0, 3.0)
        self.point_edge_width_spin.setDecimals(1)
        self.point_edge_width_spin.setValue(self.point_edge_width)
        self.point_edge_width_spin.valueChanged.connect(self.set_point_edge_width)
        point_edge_width_layout.addWidget(self.point_edge_width_spin)
        point_edge_width_layout.addStretch()
        advanced_layout.addLayout(point_edge_width_layout)
        
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
        
        # Plot labels
        labels_group = QGroupBox("Plot Labels")
        labels_layout = QVBoxLayout(labels_group)
        
        # Plot title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Leave empty to use field names")
        self.title_edit.setText(self.plot_title)
        self.title_edit.textChanged.connect(self.set_plot_title)
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
        
        # Plot area
        self.plot_widget = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_widget)
        
        # Create matplotlib figure
        self.figure = Figure(figsize=(self.figure_width, self.figure_height), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_layout.addWidget(self.canvas)
        
        main_layout.addWidget(self.plot_widget)
        
        # Bottom button bar
        button_layout = QHBoxLayout()
        
        # Export button with dropdown menu
        export_btn = QToolButton()
        export_btn.setText("Export")
        export_menu = QMenu()
        
        export_png_action = QAction("Export as PNG", self)
        export_png_action.triggered.connect(lambda: self.export_plot("png"))
        export_menu.addAction(export_png_action)
        
        export_jpg_action = QAction("Export as JPG", self)
        export_jpg_action.triggered.connect(lambda: self.export_plot("jpg"))
        export_menu.addAction(export_jpg_action)
        
        export_pdf_action = QAction("Export as PDF", self)
        export_pdf_action.triggered.connect(lambda: self.export_plot("pdf"))
        export_menu.addAction(export_pdf_action)
        
        export_svg_action = QAction("Export as SVG", self)
        export_svg_action.triggered.connect(lambda: self.export_plot("svg"))
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
    
    def update_data_and_plot(self, field_name=None):
        """
        Update data and plot with the selected fields.
        
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
        self.x_values = []
        self.y_values = []
        self.feature_ids = []
        
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
                self.x_values.append(x_float)
                self.y_values.append(y_float)
                self.feature_ids.append(str(feature.id()))
            except (ValueError, TypeError):
                # Skip non-numeric values
                continue
        
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
        
        # Update the plot
        self.update_plot()
    
    def set_show_labels(self, show):
        """Set whether to show feature labels."""
        self.show_labels = show
        self.update_plot()
    
    def set_show_trend_line(self, show):
        """Set whether to show trend line."""
        self.show_trend_line = show
        self.update_plot()
    
    def set_style_preset(self, preset):
        """Set the style preset for the plot."""
        self.style_preset = preset
        self.update_plot()
    
    def set_point_color(self, color):
        """Set the point color."""
        self.point_color = color
        self.update_plot()
    
    def choose_point_color(self):
        """Open color dialog to choose point color."""
        color = QColorDialog.getColor(QColor(self.point_color), self, "Choose Point Color")
        if color.isValid():
            self.point_color = color.name()
            self.point_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
            self.point_color_btn.setText(color.name())
            self.update_plot()
    
    def set_point_size(self, size):
        """Set the point size."""
        self.point_size = size
        self.update_plot()
    
    def set_show_grid(self, show):
        """Set whether to show grid lines."""
        self.show_grid = show
        self.update_plot()
    
    def set_use_custom_x_range(self, use):
        """Set whether to use custom x-axis range."""
        self.use_custom_x_range = use
        self.x_min_spin.setEnabled(use)
        self.x_max_spin.setEnabled(use)
        self.update_plot()
    
    def set_x_min(self, value):
        """Set the minimum x-axis value."""
        self.x_min = value
        self.update_plot()
    
    def set_x_max(self, value):
        """Set the maximum x-axis value."""
        self.x_max = value
        self.update_plot()
    
    def set_use_custom_y_range(self, use):
        """Set whether to use custom y-axis range."""
        self.use_custom_y_range = use
        self.y_min_spin.setEnabled(use)
        self.y_max_spin.setEnabled(use)
        self.update_plot()
    
    def set_y_min(self, value):
        """Set the minimum y-axis value."""
        self.y_min = value
        self.update_plot()
    
    def set_y_max(self, value):
        """Set the maximum y-axis value."""
        self.y_max = value
        self.update_plot()
    
    def set_plot_title(self, title):
        """Set the plot title."""
        self.plot_title = title
        self.update_plot()
    
    def set_x_axis_label(self, label):
        """Set the x-axis label."""
        self.x_axis_label = label
        self.update_plot()
    
    def set_y_axis_label(self, label):
        """Set the y-axis label."""
        self.y_axis_label = label
        self.update_plot()
    
    def set_point_alpha(self, alpha):
        """Set the point transparency."""
        self.point_alpha = alpha
        self.update_plot()
    
    def set_point_edge_color(self, color):
        """Set the point edge color."""
        self.point_edge_color = color
        self.update_plot()
    
    def choose_point_edge_color(self):
        """Open color dialog to choose point edge color."""
        color = QColorDialog.getColor(QColor(self.point_edge_color), self, "Choose Point Edge Color")
        if color.isValid():
            self.point_edge_color = color.name()
            self.point_edge_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
            self.point_edge_color_btn.setText(color.name())
            self.update_plot()
    
    def set_point_edge_width(self, width):
        """Set the point edge width."""
        self.point_edge_width = width
        self.update_plot()
    
    def set_title_font_size(self, size):
        """Set the title font size."""
        self.title_font_size = size
        self.update_plot()
    
    def set_axis_label_font_size(self, size):
        """Set the axis label font size."""
        self.axis_label_font_size = size
        self.update_plot()
    
    def set_tick_label_font_size(self, size):
        """Set the tick label font size."""
        self.tick_label_font_size = size
        self.update_plot()
    
    def set_figure_width(self, width):
        """Set the figure width."""
        self.figure_width = width
        self.update_figure_size()
        self.update_plot()
    
    def set_figure_height(self, height):
        """Set the figure height."""
        self.figure_height = height
        self.update_figure_size()
        self.update_plot()
    
    def update_figure_size(self):
        """Update the figure size."""
        self.figure.set_size_inches(self.figure_width, self.figure_height)
        self.canvas.draw()
    
    def update_plot(self):
        """Update the plot with current settings."""
        if not self.x_field_name or not self.y_field_name or not self.x_values or not self.y_values:
            return
        
        # Apply style preset
        with plt.style.context(self.style_preset):
            # Clear the figure
            self.figure.clear()
            
            # Create subplot
            ax = self.figure.add_subplot(111)
            
            # Create scatter plot with advanced options
            ax.scatter(self.x_values, self.y_values, s=self.point_size, c=self.point_color, 
                      alpha=self.point_alpha, edgecolors=self.point_edge_color, linewidths=self.point_edge_width)
            
            # Add feature labels if enabled
            if self.show_labels:
                for i, (x, y, fid) in enumerate(zip(self.x_values, self.y_values, self.feature_ids)):
                    ax.annotate(fid, (x, y), xytext=(5, 5), textcoords='offset points', fontsize=8)
            
            # Add trend line if enabled
            if self.show_trend_line and len(self.x_values) > 1:
                try:
                    # Calculate linear regression
                    z = np.polyfit(self.x_values, self.y_values, 1)
                    p = np.poly1d(z)
                    x_trend = np.linspace(min(self.x_values), max(self.x_values), 100)
                    y_trend = p(x_trend)
                    ax.plot(x_trend, y_trend, "r--", alpha=0.8, linewidth=2, label=f'Trend: y={z[0]:.2f}x+{z[1]:.2f}')
                    ax.legend()
                except:
                    pass  # Skip trend line if calculation fails
            
            # Set labels and title using custom labels or defaults
            title = self.plot_title if self.plot_title else f"{self.y_field_name} vs {self.x_field_name}"
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
    
    def export_plot(self, format_type):
        """
        Export the plot as an image file.
        
        Args:
            format_type: The file format to export (png, jpg, pdf, svg)
        """
        if not self.x_field_name or not self.y_field_name:
            return
        
        # Get the export directory from settings or use default
        settings = QSettings()
        last_dir = settings.value("RightClickUtilities/export_plot_dir", os.path.expanduser("~"))
        
        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{self.layer.name()}_{self.x_field_name}_vs_{self.y_field_name}_scatter_{timestamp}.{format_type}"
        
        # Show file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Plot", 
            os.path.join(last_dir, default_filename),
            f"{format_type.upper()} Files (*.{format_type})"
        )
        
        if file_path:
            # Save the directory for next time
            settings.setValue("RightClickUtilities/export_plot_dir", os.path.dirname(file_path))
            
            # Save the figure using configured DPI when available
            try:
                export_dpi = int(self.settings.get('export_dpi', 300)) if isinstance(self.settings, dict) else 300
                self.figure.savefig(file_path, format=format_type, dpi=export_dpi, bbox_inches='tight')
                # Show success message
                QLabel(f"Plot exported to {file_path}").setWindowTitle("Export Successful")
            except Exception as e:
                QLabel(f"Failed to export plot: {str(e)}").setWindowTitle("Export Failed")


class CreateScatterPlotPolygonAction(BaseAction):
    """Action to create scatter plots for polygon features."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_scatter_plot_polygon"
        self.name = "Create Scatter Plot"
        self.category = "Analysis"
        self.description = "Create a scatter plot visualization of numeric attributes for polygon features. Allows selection of two numeric fields to visualize, displaying relationships between values. Supports exporting plots, visual presets, and customization options."
        self.enabled = True
        
        # Action scoping - works on layers (affects all features in layer)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def supports_undo(self) -> bool:
        """This action is informational (creates a plot) and is NOT undoable."""
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
                'description': 'Show warning when attempting to plot layers with more features than this limit',
                'min': 10,
                'max': 10000,
                'step': 100,
            },
            'default_plot_width': {
                'type': 'int',
                'default': 800,
                'label': 'Default Plot Width',
                'description': 'Default width of the plot dialog in pixels',
                'min': 400,
                'max': 1600,
                'step': 50,
            },
            'default_plot_height': {
                'type': 'int',
                'default': 600,
                'label': 'Default Plot Height',
                'description': 'Default height of the plot dialog in pixels',
                'min': 300,
                'max': 1200,
                'step': 50,
            },
            
            # Style settings (defaults only - actual values controlled in dialog)
            'style_preset': {
                'type': 'choice',
                'default': 'default',
                'label': 'Default Style Preset',
                'description': 'Default visual style preset for the plot (can be changed in plot dialog)',
                'options': ['default', 'classic', 'bmh', 'fivethirtyeight'],
            },
            'point_color': {
                'type': 'color',
                'default': '#1f77b4',
                'label': 'Default Point Color',
                'description': 'Default color for the points in the plot (can be changed in plot dialog)',
            },
            'point_size': {
                'type': 'int',
                'default': 50,
                'label': 'Default Point Size',
                'description': 'Default size for the points in the plot (can be changed in plot dialog)',
                'min': 1,
                'max': 500,
                'step': 5,
            },
            'show_grid': {
                'type': 'bool',
                'default': True,
                'label': 'Default Show Grid Lines',
                'description': 'Default setting for showing grid lines (can be changed in plot dialog)',
            },
            'show_labels': {
                'type': 'bool',
                'default': False,
                'label': 'Default Show Labels',
                'description': 'Default setting for showing feature labels (can be changed in plot dialog)',
            },
            'show_trend_line': {
                'type': 'bool',
                'default': False,
                'label': 'Default Show Trend Line',
                'description': 'Default setting for showing trend line (can be changed in plot dialog)',
            },
            
            # Plot labels
            'plot_title': {
                'type': 'str',
                'default': '',
                'label': 'Default Plot Title',
                'description': 'Default title for the plot (leave empty to use field names)',
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
                'description': 'Default file format when exporting plots',
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
        """Execute the create scatter plot action."""
        # Get settings with proper type conversion
        try:
            # Display settings
            max_features_warning = int(self.get_setting('max_features_warning', 1000))
            default_plot_width = int(self.get_setting('default_plot_width', 800))
            default_plot_height = int(self.get_setting('default_plot_height', 600))
            
            # Style settings
            style_preset = str(self.get_setting('style_preset', 'default'))
            point_color = str(self.get_setting('point_color', '#1f77b4'))
            point_size = int(self.get_setting('point_size', 50))
            show_grid = bool(self.get_setting('show_grid', True))
            show_labels = bool(self.get_setting('show_labels', False))
            show_trend_line = bool(self.get_setting('show_trend_line', False))
            
            # Plot labels
            plot_title = str(self.get_setting('plot_title', ''))
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
        
        # Verify it's a polygon layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return
        
        # Check feature count
        feature_count = layer.featureCount()
        if feature_count == 0:
            self.show_warning("Empty Layer", "The selected layer has no features to plot.")
            return
        
        if feature_count > max_features_warning:
            if not self.confirm_action(
                "Large Layer Warning",
                f"The selected layer has {feature_count} features, which may make the plot crowded or slow to generate. Continue anyway?"
            ):
                return
        
        # Get numeric fields from the layer (scatter plots need numeric data)
        numeric_fields = []
        for field in layer.fields():
            if field.isNumeric():
                numeric_fields.append(field.name())
        
        if not numeric_fields:
            self.show_warning("No Numeric Fields", 
                             "The selected layer has no numeric fields to plot. Scatter plots require numeric fields for both X and Y axes.")
            return
        
        if len(numeric_fields) < 2:
            self.show_warning("Insufficient Fields", 
                             "The selected layer has only one numeric field. Scatter plots require at least two numeric fields (one for X-axis and one for Y-axis).")
            return
        
        # Collect all settings to pass to the dialog
        plot_settings = {
            'style_preset': style_preset,
            'point_color': point_color,
            'point_size': point_size,
            'show_grid': show_grid,
            'show_labels': show_labels,
            'show_trend_line': show_trend_line,
            'default_export_format': default_export_format,
            'export_dpi': export_dpi,
            'plot_title': plot_title,
            'x_axis_label': x_axis_label,
            'y_axis_label': y_axis_label,
        }
        
        # Create and show the plot dialog
        try:
            dialog = ScatterPlotDialog(layer, numeric_fields, plot_settings)
            dialog.resize(default_plot_width, default_plot_height)
            dialog.exec_()

            # Record informational history entry (non-undoable)
            try:
                hm = get_history_manager()
                desc = f"Displayed scatter plot for layer '{layer.name()}'"
                meta = {
                    'layer_id': layer.id(),
                    'layer_name': layer.name(),
                    'x_field': getattr(dialog, 'x_field_name', ''),
                    'y_field': getattr(dialog, 'y_field_name', ''),
                    'settings': plot_settings
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
            self.show_error("Error", f"Failed to create scatter plot: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_scatter_plot_polygon_action = CreateScatterPlotPolygonAction()

