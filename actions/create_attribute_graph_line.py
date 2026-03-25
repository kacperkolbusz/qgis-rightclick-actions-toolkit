"""
Create Attribute Graph for Line Layer Action for Right-click Utilities and Shortcuts Hub

Creates a bar graph visualization of numeric attributes for line features.
Allows users to select which numeric field to visualize, displaying values for each feature.
Supports exporting graphs, visual presets, and sorting/filtering options.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                QLabel, QComboBox, QSizePolicy, QWidget, QFileDialog,
                                QGroupBox, QRadioButton, QCheckBox, QSpinBox, QDoubleSpinBox,
                                QToolButton, QMenu, QAction, QGridLayout, QLineEdit, QColorDialog, QScrollArea)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.utils import iface
from qgis.core import QgsWkbTypes
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.style as mplstyle
import numpy as np
import os
from datetime import datetime


class AttributeGraphDialog(QDialog):
    """Dialog for displaying attribute graphs."""
    
    def __init__(self, layer, fields, settings, parent=None):
        """
        Initialize the attribute graph dialog.
        
        Args:
            layer: The QGIS vector layer containing the features
            fields: List of numeric field names available for graphing
            settings: Dictionary of settings for the graph
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Attribute Graph")
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

        # Default figure DPI and desired dialog defaults (pixels)
        self.figure_dpi = 100
        try:
            self.default_graph_width = int(self.settings.get('default_graph_width', 800))
            self.default_graph_height = int(self.settings.get('default_graph_height', 600))
        except Exception:
            self.default_graph_width = 800
            self.default_graph_height = 600

        # Compute default figure size in inches for matplotlib
        try:
            self.figure_width = float(self.default_graph_width) / float(self.figure_dpi)
            self.figure_height = float(self.default_graph_height) / float(self.figure_dpi)
        except Exception:
            self.figure_width = 8.0
            self.figure_height = 6.0
        
        # Data storage
        self.feature_ids = []
        self.values = []
        self.field_name = ""
        
        # Graph style settings
        self.style_preset = self.settings.get('style_preset', 'default')
        self.bar_color = self.settings.get('bar_color', '#1f77b4')
        self.show_grid = self.settings.get('show_grid', True)
        self.show_values_on_bars = False  # User-controlled in dialog, not in settings
        self.values_decimal_places = 2  # User-controlled in dialog, not in settings
        self.sort_order = self.settings.get('sort_order', 'none')
        self.show_top_n = self.settings.get('show_top_n', 0)  # 0 means show all
        self.min_value = None
        self.max_value = None
        
        # Axis range settings (user-controlled in dialog)
        self.use_custom_x_range = False
        self.x_min = 0.0
        self.x_max = 10.0
        self.use_custom_y_range = False
        self.y_min = 0.0
        self.y_max = 100.0
        
        # Advanced style settings
        self.bar_width = 0.8
        self.bar_edge_color = '#000000'
        self.bar_edge_width = 0.5
        self.horizontal = False
        self.title_font_size = 14
        self.axis_label_font_size = 12
        self.tick_label_font_size = 10
        self.figure_width = 8.0
        self.figure_height = 6.0
        
        # Customizable graph labels
        self.graph_title = self.settings.get('graph_title', '')
        self.x_axis_label = self.settings.get('x_axis_label', '')
        self.y_axis_label = self.settings.get('y_axis_label', '')
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface."""
        # Create scroll area for the entire dialog
        self.scroll_area = QScrollArea()
        # Make the scroll area resizable so content adapts to window size
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Create content widget
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        # Make the dialog compact but scaled to the default graph size
        min_w = max(600, int(self.default_graph_width * 0.75))
        min_h = max(400, int(self.default_graph_height * 0.75))
        content_widget.setMinimumSize(min_w, min_h)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)
        
        # Title
        title_label = QLabel(f"Attribute Graph for Layer: {self.layer.name()}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        main_layout.addWidget(title_label)

        # Quick toggle to show/hide advanced controls (keeps initial UI simple)
        self.show_advanced_btn = QPushButton("Show advanced options ▾")
        self.show_advanced_btn.setCheckable(True)
        self.show_advanced_btn.toggled.connect(self.toggle_advanced)
        main_layout.addWidget(self.show_advanced_btn)
        
        # Control panel (top section) - compact grid layout
        from qgis.PyQt.QtWidgets import QGridLayout
        control_panel = QGridLayout()
        control_panel.setHorizontalSpacing(8)
        control_panel.setVerticalSpacing(6)
        control_panel.setContentsMargins(0, 0, 0, 0)
        
        # Field selection
        field_group = QGroupBox("Field Selection")
        field_layout = QVBoxLayout(field_group)
        field_label = QLabel("Select field to graph:")
        self.field_combo = QComboBox()
        self.field_combo.addItem("-- Select Field --")  # Default "none" option
        self.field_combo.addItems(self.fields)
        self.field_combo.currentTextChanged.connect(self.update_data_and_graph)
        field_layout.addWidget(field_label)
        field_layout.addWidget(self.field_combo)
        # Auto-select the only field if layer has exactly one numeric field (improves UX)
        if len(self.fields) == 1:
            self.field_combo.setCurrentIndex(1)
        
        # Sorting options
        sort_group = QGroupBox("Sorting")
        sort_layout = QVBoxLayout(sort_group)
        self.sort_none_radio = QRadioButton("None")
        self.sort_asc_radio = QRadioButton("Ascending")
        self.sort_desc_radio = QRadioButton("Descending")
        
        # Set initial state based on settings
        if self.sort_order == 'ascending':
            self.sort_asc_radio.setChecked(True)
        elif self.sort_order == 'descending':
            self.sort_desc_radio.setChecked(True)
        else:
            self.sort_none_radio.setChecked(True)
            
        self.sort_none_radio.toggled.connect(lambda: self.set_sort_order('none'))
        self.sort_asc_radio.toggled.connect(lambda: self.set_sort_order('ascending'))
        self.sort_desc_radio.toggled.connect(lambda: self.set_sort_order('descending'))
        
        sort_layout.addWidget(self.sort_none_radio)
        sort_layout.addWidget(self.sort_asc_radio)
        sort_layout.addWidget(self.sort_desc_radio)
        # Filtering options
        filter_group = QGroupBox("Filtering")
        filter_layout = QVBoxLayout(filter_group)
        
        # Top N features
        top_n_layout = QHBoxLayout()
        top_n_layout.addWidget(QLabel("Show top:"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(0, 1000)
        self.top_n_spin.setValue(self.show_top_n)
        self.top_n_spin.setSpecialValueText("All")  # 0 means show all
        self.top_n_spin.valueChanged.connect(self.set_top_n)
        top_n_layout.addWidget(self.top_n_spin)
        top_n_layout.addWidget(QLabel("features"))
        filter_layout.addLayout(top_n_layout)
        
        # Value range filter
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("Value range:"))
        self.min_value_spin = QDoubleSpinBox()
        self.min_value_spin.setRange(-1000000, 1000000)
        self.min_value_spin.setDecimals(2)
        self.min_value_spin.valueChanged.connect(self.set_min_value)
        
        self.max_value_spin = QDoubleSpinBox()
        self.max_value_spin.setRange(-1000000, 1000000)
        self.max_value_spin.setDecimals(2)
        self.max_value_spin.valueChanged.connect(self.set_max_value)
        
        range_layout.addWidget(self.min_value_spin)
        range_layout.addWidget(QLabel("to"))
        range_layout.addWidget(self.max_value_spin)
        filter_layout.addLayout(range_layout)
        
        # Apply filter button
        self.apply_filter_btn = QPushButton("Apply Filters")
        self.apply_filter_btn.clicked.connect(self.update_graph)
        filter_layout.addWidget(self.apply_filter_btn)
        
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
        
        # Bar color picker
        bar_color_layout = QHBoxLayout()
        bar_color_layout.addWidget(QLabel("Bar color:"))
        self.bar_color_btn = QPushButton()
        color = QColor(self.bar_color)
        self.bar_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
        self.bar_color_btn.setText(color.name())
        self.bar_color_btn.clicked.connect(self.choose_bar_color)
        bar_color_layout.addWidget(self.bar_color_btn)
        style_layout.addLayout(bar_color_layout)
        
        # Grid lines
        self.show_grid_check = QCheckBox("Show grid lines")
        self.show_grid_check.setChecked(self.show_grid)
        self.show_grid_check.toggled.connect(self.set_show_grid)
        style_layout.addWidget(self.show_grid_check)
        
        # Show values on bars
        self.show_values_check = QCheckBox("Show values on top of bars")
        self.show_values_check.setChecked(self.show_values_on_bars)
        self.show_values_check.toggled.connect(self.set_show_values_on_bars)
        style_layout.addWidget(self.show_values_check)
        
        # Precision control for values on bars (positive = decimal places, negative = round to 10^abs(value))
        precision_layout = QHBoxLayout()
        precision_layout.addWidget(QLabel("Precision:"))
        self.values_decimal_spin = QSpinBox()
        self.values_decimal_spin.setRange(-10, 10)
        self.values_decimal_spin.setValue(self.values_decimal_places)
        self.values_decimal_spin.setEnabled(self.show_values_on_bars)
        self.values_decimal_spin.valueChanged.connect(self.set_values_decimal_places)
        precision_layout.addWidget(self.values_decimal_spin)
        precision_label = QLabel("(pos=decimals, neg=round to 10^n)")
        precision_label.setStyleSheet("font-size: 9px; color: #666;")
        precision_layout.addWidget(precision_label)
        precision_layout.addStretch()
        style_layout.addLayout(precision_layout)
        
        # Advanced options
        # Advanced options are hidden by default and toggled via the button above
        self.advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(self.advanced_group)
        
        # Bar width
        bar_width_layout = QHBoxLayout()
        bar_width_layout.addWidget(QLabel("Bar width:"))
        self.bar_width_spin = QDoubleSpinBox()
        self.bar_width_spin.setRange(0.1, 2.0)
        self.bar_width_spin.setDecimals(2)
        self.bar_width_spin.setValue(self.bar_width)
        self.bar_width_spin.setSingleStep(0.1)
        self.bar_width_spin.valueChanged.connect(self.set_bar_width)
        bar_width_layout.addWidget(self.bar_width_spin)
        bar_width_layout.addStretch()
        advanced_layout.addLayout(bar_width_layout)
        
        # Bar edge color
        bar_edge_color_layout = QHBoxLayout()
        bar_edge_color_layout.addWidget(QLabel("Bar edge color:"))
        self.bar_edge_color_btn = QPushButton()
        edge_color = QColor(self.bar_edge_color)
        self.bar_edge_color_btn.setStyleSheet(f"background-color: {edge_color.name()}; border: 1px solid #ccc; min-width: 80px;")
        self.bar_edge_color_btn.setText(edge_color.name())
        self.bar_edge_color_btn.clicked.connect(self.choose_bar_edge_color)
        bar_edge_color_layout.addWidget(self.bar_edge_color_btn)
        advanced_layout.addLayout(bar_edge_color_layout)
        
        # Bar edge width
        bar_edge_width_layout = QHBoxLayout()
        bar_edge_width_layout.addWidget(QLabel("Bar edge width:"))
        self.bar_edge_width_spin = QDoubleSpinBox()
        self.bar_edge_width_spin.setRange(0.0, 3.0)
        self.bar_edge_width_spin.setDecimals(1)
        self.bar_edge_width_spin.setValue(self.bar_edge_width)
        self.bar_edge_width_spin.valueChanged.connect(self.set_bar_edge_width)
        bar_edge_width_layout.addWidget(self.bar_edge_width_spin)
        bar_edge_width_layout.addStretch()
        advanced_layout.addLayout(bar_edge_width_layout)
        
        # Horizontal orientation
        self.horizontal_check = QCheckBox("Horizontal bars")
        self.horizontal_check.setChecked(self.horizontal)
        self.horizontal_check.toggled.connect(self.set_horizontal)
        advanced_layout.addWidget(self.horizontal_check)
        
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
        
        # Axis range options
        self.axis_range_group = QGroupBox("Axis Ranges")
        axis_range_layout = QVBoxLayout(self.axis_range_group)
        
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
        
        # Graph labels
        self.labels_group = QGroupBox("Graph Labels")
        labels_layout = QVBoxLayout(self.labels_group)
        
        # Graph title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Leave empty to use field name")
        self.title_edit.setText(self.graph_title)
        self.title_edit.textChanged.connect(self.set_graph_title)
        title_layout.addWidget(self.title_edit)
        labels_layout.addLayout(title_layout)
        
        # X-axis label
        x_label_layout = QHBoxLayout()
        x_label_layout.addWidget(QLabel("X-axis:"))
        self.x_label_edit = QLineEdit()
        self.x_label_edit.setPlaceholderText("Leave empty to use 'Feature ID'")
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
        
        # Arrange groups in a compact 2-column grid
        control_panel.addWidget(field_group, 0, 0)
        control_panel.addWidget(sort_group, 0, 1)
        control_panel.addWidget(filter_group, 1, 0)
        control_panel.addWidget(style_group, 1, 1)
        control_panel.addWidget(self.advanced_group, 2, 0)
        control_panel.addWidget(self.axis_range_group, 2, 1)
        control_panel.addWidget(self.labels_group, 3, 0, 1, 2)
        
        main_layout.addLayout(control_panel)
        
        # Graph area
        self.graph_widget = QWidget()
        self.graph_layout = QVBoxLayout(self.graph_widget)
        
        # Create matplotlib figure using configured DPI and size
        self.figure = Figure(figsize=(self.figure_width, self.figure_height), dpi=self.figure_dpi)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graph_layout.addWidget(self.canvas)
        
        main_layout.addWidget(self.graph_widget)
        
        # Bottom button bar
        button_layout = QHBoxLayout()
        
        # Export button with dropdown menu
        export_btn = QToolButton()
        export_btn.setText("Export")
        export_menu = QMenu()
        
        export_png_action = QAction("Export as PNG", self)
        export_png_action.triggered.connect(lambda: self.export_graph("png"))
        export_menu.addAction(export_png_action)
        
        export_jpg_action = QAction("Export as JPG", self)
        export_jpg_action.triggered.connect(lambda: self.export_graph("jpg"))
        export_menu.addAction(export_jpg_action)
        
        export_pdf_action = QAction("Export as PDF", self)
        export_pdf_action.triggered.connect(lambda: self.export_graph("pdf"))
        export_menu.addAction(export_pdf_action)
        
        export_svg_action = QAction("Export as SVG", self)
        export_svg_action.triggered.connect(lambda: self.export_graph("svg"))
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
        
        # Set scroll area as main layout
        dialog_layout = QVBoxLayout()
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(self.scroll_area)
        self.setLayout(dialog_layout)
        # Ensure figure uses the calculated size
        try:
            self.update_figure_size()
        except Exception:
            pass

    def toggle_advanced(self, checked):
        """Show or hide advanced UI sections to reduce clutter by default."""
        visible = bool(checked)
        # Ensure the groups exist before toggling
        try:
            self.advanced_group.setVisible(visible)
            self.axis_range_group.setVisible(visible)
            self.labels_group.setVisible(visible)
        except Exception:
            pass
        self.show_advanced_btn.setText("Hide advanced options ▴" if visible else "Show advanced options ▾")
    
    def update_data_and_graph(self, field_name=None):
        """
        Update data and graph with the selected field.
        
        Args:
            field_name: The field name to graph (optional, uses current selection if None)
        """
        if field_name is None:
            field_name = self.field_combo.currentText()
        
        # Skip if no field selected or if it's the default placeholder
        if not field_name or field_name == "-- Select Field --":
            return
        
        self.field_name = field_name
        
        # Get data from features
        self.feature_ids = []
        self.values = []
        self.original_indices = []
        
        for i, feature in enumerate(self.layer.getFeatures()):
            self.feature_ids.append(str(feature.id()))
            self.original_indices.append(i)
            value = feature[field_name]
            # Handle NULL values
            if value is None or (isinstance(value, (int, float)) and (np.isnan(value) or np.isinf(value))):
                self.values.append(0)
            else:
                try:
                    self.values.append(float(value))
                except (ValueError, TypeError):
                    self.values.append(0)
        
        # Always update range for value filters when field changes
        if self.values:
            min_val = min(self.values)
            max_val = max(self.values)
        else:
            min_val = 0
            max_val = 100
        
        # Update the spin boxes and internal values
        self.min_value_spin.setValue(min_val)
        self.max_value_spin.setValue(max_val)
        self.min_value = min_val
        self.max_value = max_val
        
        # Update default axis ranges (but don't override if user has custom ranges enabled)
        if not self.use_custom_y_range:
            # Set default y-axis range with some padding
            y_padding = (max_val - min_val) * 0.1 if max_val != min_val else max(abs(min_val), abs(max_val)) * 0.1 or 1
            self.y_min = min_val - y_padding
            self.y_max = max_val + y_padding
            self.y_min_spin.setValue(self.y_min)
            self.y_max_spin.setValue(self.y_max)
        
        # X-axis range is based on number of features, update if not custom
        if not self.use_custom_x_range:
            num_features = len(self.values)
            self.x_min = -0.5
            self.x_max = max(num_features - 0.5, 0.5)
            self.x_min_spin.setValue(self.x_min)
            self.x_max_spin.setValue(self.x_max)
        
        # Update the graph
        self.update_graph()

    # Many helper methods (setters, update_graph, export_graph) are identical to the point/polygon versions
    # For brevity, we'll reuse the same implementations below.

    def set_sort_order(self, order):
        self.sort_order = order
        self.update_graph()

    def set_top_n(self, value):
        self.show_top_n = value

    def set_min_value(self, value):
        self.min_value = value

    def set_max_value(self, value):
        self.max_value = value

    def set_style_preset(self, preset):
        self.style_preset = preset
        self.update_graph()

    def set_show_grid(self, show):
        self.show_grid = show
        self.update_graph()

    def set_show_values_on_bars(self, show):
        self.show_values_on_bars = show
        self.values_decimal_spin.setEnabled(show)
        self.update_graph()

    def set_values_decimal_places(self, places):
        self.values_decimal_places = places
        self.update_graph()

    def set_use_custom_x_range(self, use):
        self.use_custom_x_range = use
        self.x_min_spin.setEnabled(use)
        self.x_max_spin.setEnabled(use)
        self.update_graph()

    def set_x_min(self, value):
        self.x_min = value
        self.update_graph()

    def set_x_max(self, value):
        self.x_max = value
        self.update_graph()

    def set_use_custom_y_range(self, use):
        self.use_custom_y_range = use
        self.y_min_spin.setEnabled(use)
        self.y_max_spin.setEnabled(use)
        self.update_graph()

    def set_y_min(self, value):
        self.y_min = value
        self.update_graph()

    def set_y_max(self, value):
        self.y_max = value
        self.update_graph()

    def choose_bar_color(self):
        color = QColorDialog.getColor(QColor(self.bar_color), self, "Choose Bar Color")
        if color.isValid():
            self.bar_color = color.name()
            self.bar_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
            self.bar_color_btn.setText(color.name())
            self.update_graph()

    def set_graph_title(self, title):
        self.graph_title = title
        self.update_graph()

    def set_x_axis_label(self, label):
        self.x_axis_label = label
        self.update_graph()

    def set_y_axis_label(self, label):
        self.y_axis_label = label
        self.update_graph()

    def set_bar_width(self, width):
        self.bar_width = width
        self.update_graph()

    def set_bar_edge_color(self, color):
        self.bar_edge_color = color
        self.update_graph()

    def choose_bar_edge_color(self):
        color = QColorDialog.getColor(QColor(self.bar_edge_color), self, "Choose Bar Edge Color")
        if color.isValid():
            self.bar_edge_color = color.name()
            self.bar_edge_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
            self.bar_edge_color_btn.setText(color.name())
            self.update_graph()

    def set_bar_edge_width(self, width):
        self.bar_edge_width = width
        self.update_graph()

    def set_horizontal(self, horizontal):
        self.horizontal = horizontal
        self.update_graph()

    def set_title_font_size(self, size):
        self.title_font_size = size
        self.update_graph()

    def set_axis_label_font_size(self, size):
        self.axis_label_font_size = size
        self.update_graph()

    def set_tick_label_font_size(self, size):
        self.tick_label_font_size = size
        self.update_graph()

    def set_figure_width(self, width):
        self.figure_width = width
        self.update_figure_size()
        self.update_graph()

    def set_figure_height(self, height):
        self.figure_height = height
        self.update_figure_size()
        self.update_graph()

    def update_figure_size(self):
        self.figure.set_size_inches(self.figure_width, self.figure_height)
        self.canvas.draw()

    def update_graph(self):
        if not self.field_name or not self.values:
            return
        
        with plt.style.context(self.style_preset):
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            display_indices = list(range(len(self.values)))
            display_values = list(self.values)
            display_ids = list(self.feature_ids)
            filtered_data = [(i, val, fid) for i, val, fid in zip(display_indices, display_values, display_ids) 
                            if self.min_value <= val <= self.max_value]
            if filtered_data:
                display_indices, display_values, display_ids = zip(*filtered_data)
            else:
                display_indices, display_values, display_ids = [], [], []
            if self.sort_order != 'none' and display_values:
                sorted_data = sorted(zip(display_indices, display_values, display_ids), 
                                    key=lambda x: x[1], 
                                    reverse=(self.sort_order == 'descending'))
                display_indices, display_values, display_ids = zip(*sorted_data)
            if self.show_top_n > 0 and len(display_values) > self.show_top_n:
                display_indices = display_indices[:self.show_top_n]
                display_values = display_values[:self.show_top_n]
                display_ids = display_ids[:self.show_top_n]
            if display_values:
                if self.horizontal:
                    bars = ax.barh(range(len(display_values)), display_values, height=self.bar_width, 
                                  color=self.bar_color, edgecolor=self.bar_edge_color, linewidth=self.bar_edge_width)
                else:
                    bars = ax.bar(range(len(display_values)), display_values, width=self.bar_width, 
                                 color=self.bar_color, edgecolor=self.bar_edge_color, linewidth=self.bar_edge_width)
                title = self.graph_title if self.graph_title else f"{self.field_name} by Feature"
                x_label = self.x_axis_label if self.x_axis_label else "Feature ID"
                y_label = self.y_axis_label if self.y_axis_label else self.field_name
                ax.set_title(title, fontsize=self.title_font_size)
                ax.set_xlabel(x_label, fontsize=self.axis_label_font_size)
                ax.set_ylabel(y_label, fontsize=self.axis_label_font_size)
                ax.tick_params(labelsize=self.tick_label_font_size)
                ax.grid(self.show_grid)
                if len(display_ids) > 20:
                    step = max(1, len(display_ids) // 20)
                    ax.set_xticks(range(0, len(display_ids), step))
                    ax.set_xticklabels([display_ids[i] for i in range(0, len(display_ids), step)], 
                                      rotation=45, ha='right')
                else:
                    ax.set_xticks(range(len(display_ids)))
                    ax.set_xticklabels(display_ids, rotation=45, ha='right')
                if self.show_values_on_bars:
                    for i, rect in enumerate(bars):
                        value = display_values[i]
                        if self.values_decimal_places >= 0:
                            format_str = f'{{:.{self.values_decimal_places}f}}'
                            formatted_value = format_str.format(value)
                        else:
                            rounding_factor = 10 ** abs(self.values_decimal_places)
                            rounded_value = round(value / rounding_factor) * rounding_factor
                            formatted_value = f'{rounded_value:.0f}' if abs(self.values_decimal_places) >= 1 else f'{rounded_value:.1f}'
                        if self.horizontal:
                            width = rect.get_width()
                            ax.text(width + 0.01 * max(display_values), rect.get_y() + rect.get_height()/2.,
                                   formatted_value, ha='left', va='center', rotation=0)
                        else:
                            height = rect.get_height()
                            ax.text(rect.get_x() + rect.get_width()/2., height + 0.01 * max(display_values),
                                   formatted_value, ha='center', va='bottom', rotation=0)
                if self.horizontal:
                    if self.use_custom_y_range:
                        ax.set_xlim(self.y_min, self.y_max)
                    if self.use_custom_x_range:
                        ax.set_ylim(self.x_min, self.x_max)
                else:
                    if self.use_custom_x_range:
                        ax.set_xlim(self.x_min, self.x_max)
                    if self.use_custom_y_range:
                        ax.set_ylim(self.y_min, self.y_max)
            else:
                ax.text(0.5, 0.5, "No data to display with current filters", 
                       ha='center', va='center', transform=ax.transAxes)
            self.figure.tight_layout()
            self.canvas.draw()

    def export_graph(self, format_type):
        if not self.field_name:
            return
        settings = QSettings()
        last_dir = settings.value("RightClickUtilities/export_graph_dir", os.path.expanduser("~"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{self.layer.name()}_{self.field_name}_{timestamp}.{format_type}"
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Graph", 
            os.path.join(last_dir, default_filename),
            f"{format_type.upper()} Files (*.{format_type})"
        )
        if file_path:
            settings.setValue("RightClickUtilities/export_graph_dir", os.path.dirname(file_path))
            try:
                self.figure.savefig(file_path, format=format_type, dpi=300, bbox_inches='tight')
                QLabel(f"Graph exported to {file_path}").setWindowTitle("Export Successful")
            except Exception as e:
                QLabel(f"Failed to export graph: {str(e)}").setWindowTitle("Export Failed")


class CreateAttributeGraphLineAction(BaseAction):
    """Action to create attribute graphs for line features."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_attribute_graph_line"
        self.name = "Create Attribute Graph"
        self.category = "Analysis"
        self.description = "Create a bar graph visualization of numeric attributes for line features. Allows selection of which numeric field to visualize, displaying values for each feature in the layer. Supports exporting graphs, visual presets, and sorting/filtering options."
        self.enabled = True
        
        # Action scoping - works on layers (affects all features in layer)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with lines
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        return {
            'max_features_warning': {
                'type': 'int',
                'default': 100,
                'label': 'Maximum Features Warning',
                'description': 'Show warning when attempting to graph layers with more features than this limit',
                'min': 10,
                'max': 1000,
                'step': 10,
            },
            'default_graph_width': {
                'type': 'int',
                'default': 1600,
                'label': 'Default Graph Width',
                'description': 'Default width of the graph dialog in pixels',
                'min': 800,
                'max': 3840,
                'step': 50,
            },
            'default_graph_height': {
                'type': 'int',
                'default': 900,
                'label': 'Default Graph Height',
                'description': 'Default height of the graph dialog in pixels',
                'min': 600,
                'max': 2160,
                'step': 50,
            },
            'style_preset': {
                'type': 'choice',
                'default': 'default',
                'label': 'Default Style Preset',
                'description': 'Default visual style preset for the graph (can be changed in graph dialog)',
                'options': ['default', 'classic', 'bmh', 'fivethirtyeight'],
            },
            'bar_color': {
                'type': 'color',
                'default': '#1f77b4',
                'label': 'Default Bar Color',
                'description': 'Default color for the bars in the graph (can be changed in graph dialog)',
            },
            'show_grid': {
                'type': 'bool',
                'default': True,
                'label': 'Default Show Grid Lines',
                'description': 'Default setting for showing grid lines (can be changed in graph dialog)',
            },
            'graph_title': {
                'type': 'str',
                'default': '',
                'label': 'Default Graph Title',
                'description': 'Default title for the graph (leave empty to use field name)',
            },
            'x_axis_label': {
                'type': 'str',
                'default': '',
                'label': 'Default X-axis Label',
                'description': 'Default label for the x-axis (leave empty to use "Feature ID")',
            },
            'y_axis_label': {
                'type': 'str',
                'default': '',
                'label': 'Default Y-axis Label',
                'description': 'Default label for the y-axis (leave empty to use field name)',
            },
            'sort_order': {
                'type': 'choice',
                'default': 'none',
                'label': 'Default Sort Order',
                'description': 'Default sorting order for the bars',
                'options': ['none', 'ascending', 'descending'],
            },
            'show_top_n': {
                'type': 'int',
                'default': 0,
                'label': 'Show Top N Features',
                'description': 'Show only the top N features by default (0 = show all)',
                'min': 0,
                'max': 1000,
                'step': 1,
            },
            'default_export_format': {
                'type': 'choice',
                'default': 'png',
                'label': 'Default Export Format',
                'description': 'Default file format when exporting graphs',
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
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def execute(self, context):
        try:
            max_features_warning = int(self.get_setting('max_features_warning', 100))
            default_graph_width = int(self.get_setting('default_graph_width', 1600))
            default_graph_height = int(self.get_setting('default_graph_height', 900))
            style_preset = str(self.get_setting('style_preset', 'default'))
            bar_color = str(self.get_setting('bar_color', '#1f77b4'))
            show_grid = bool(self.get_setting('show_grid', True))
            graph_title = str(self.get_setting('graph_title', ''))
            x_axis_label = str(self.get_setting('x_axis_label', ''))
            y_axis_label = str(self.get_setting('y_axis_label', ''))
            sort_order = str(self.get_setting('sort_order', 'none'))
            show_top_n = int(self.get_setting('show_top_n', 0))
            default_export_format = str(self.get_setting('default_export_format', 'png'))
            export_dpi = int(self.get_setting('export_dpi', 300))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.show_error("Error", "This action only works with line layers")
            return
        feature_count = layer.featureCount()
        if feature_count == 0:
            self.show_warning("Empty Layer", "The selected layer has no features to graph.")
            return
        if feature_count > max_features_warning:
            if not self.confirm_action(
                "Large Layer Warning",
                f"The selected layer has {feature_count} features, which may make the graph crowded or slow to generate. Continue anyway?"
            ):
                return
        numeric_fields = []
        for field in layer.fields():
            if field.isNumeric():
                numeric_fields.append(field.name())
        if not numeric_fields:
            self.show_warning("No Numeric Fields", 
                             "The selected layer has no numeric fields to graph. Only numeric fields can be used for graphing.")
            return
        graph_settings = {
            'style_preset': style_preset,
            'bar_color': bar_color,
            'show_grid': show_grid,
            'sort_order': sort_order,
            'show_top_n': show_top_n,
            'default_graph_width': default_graph_width,
            'default_graph_height': default_graph_height,
            'default_export_format': default_export_format,
            'export_dpi': export_dpi,
            'graph_title': graph_title,
            'x_axis_label': x_axis_label,
            'y_axis_label': y_axis_label,
        }
        try:
            dialog = AttributeGraphDialog(layer, numeric_fields, graph_settings)
            dialog.resize(default_graph_width, default_graph_height)
            dialog.exec_()
            try:
                from ..history_manager import get_history_manager
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}
                meta = {
                    'layer': layer_desc,
                    'field': getattr(dialog, 'field_name', '') or None,
                    'settings': graph_settings
                }
                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Created attribute graph for layer {layer.name()}",
                    meta=meta
                )
            except Exception:
                pass
        except Exception as e:
            self.show_error("Error", f"Failed to create attribute graph: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_attribute_graph_line_action = CreateAttributeGraphLineAction()
