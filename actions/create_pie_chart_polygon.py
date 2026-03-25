"""
Create Pie Chart for Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Creates a pie chart visualization of attribute values for polygon features.
Allows users to select any field to visualize, displaying value distribution as proportions.
Works with text, numeric, and other field types. Supports exporting charts, visual presets, and customization options.
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                QLabel, QComboBox, QSizePolicy, QWidget, QFileDialog,
                                QGroupBox, QRadioButton, QCheckBox, QSpinBox, QDoubleSpinBox,
                                QToolButton, QMenu, QAction, QGridLayout, QLineEdit, QScrollArea, QColorDialog)
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
from collections import Counter


class PieChartDialog(QDialog):
    """Dialog for displaying pie charts."""
    
    def __init__(self, layer, fields, settings, parent=None):
        """
        Initialize the pie chart dialog.
        
        Args:
            layer: The QGIS vector layer containing the features
            fields: List of field names available for charting (any field type)
            settings: Dictionary of settings for the chart
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Pie Chart")
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
        self.values = []
        self.field_name = ""
        
        # Chart style settings
        self.style_preset = self.settings.get('style_preset', 'default')
        self.show_percentages = self.settings.get('show_percentages', True)
        self.show_labels = self.settings.get('show_labels', True)
        self.start_angle = self.settings.get('start_angle', 0)
        self.explode_smallest = self.settings.get('explode_smallest', False)
        self.min_percentage = self.settings.get('min_percentage', 0.0)  # Hide slices below this percentage
        
        # Advanced style settings
        self.color_scheme = 'Set3'  # matplotlib colormap name
        self.edge_color = '#ffffff'
        self.edge_width = 1.0
        self.shadow = False
        self.text_position = 'auto'  # 'auto', 'inside', 'outside'
        self.title_font_size = 14
        self.label_font_size = 10
        self.figure_width = 8.0
        self.figure_height = 6.0
        
        # Customizable chart labels
        self.chart_title = self.settings.get('chart_title', '')
        
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
        title_label = QLabel(f"Pie Chart for Layer: {self.layer.name()}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        main_layout.addWidget(title_label)
        
        # Control panel (top section)
        control_panel = QHBoxLayout()
        
        # Field selection
        field_group = QGroupBox("Field Selection")
        field_layout = QVBoxLayout(field_group)
        field_label = QLabel("Select field to chart:")
        self.field_combo = QComboBox()
        self.field_combo.addItem("-- Select Field --")  # Default "none" option
        self.field_combo.addItems(self.fields)
        self.field_combo.currentTextChanged.connect(self.update_data_and_chart)
        field_layout.addWidget(field_label)
        field_layout.addWidget(self.field_combo)
        control_panel.addWidget(field_group)
        
        # Display options
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)
        
        # Show percentages
        self.show_percentages_check = QCheckBox("Show percentages")
        self.show_percentages_check.setChecked(self.show_percentages)
        self.show_percentages_check.toggled.connect(self.set_show_percentages)
        display_layout.addWidget(self.show_percentages_check)
        
        # Show labels
        self.show_labels_check = QCheckBox("Show labels")
        self.show_labels_check.setChecked(self.show_labels)
        self.show_labels_check.toggled.connect(self.set_show_labels)
        display_layout.addWidget(self.show_labels_check)
        
        # Explode smallest slice
        self.explode_smallest_check = QCheckBox("Explode smallest slice")
        self.explode_smallest_check.setChecked(self.explode_smallest)
        self.explode_smallest_check.toggled.connect(self.set_explode_smallest)
        display_layout.addWidget(self.explode_smallest_check)
        
        # Minimum percentage to show
        min_perc_layout = QHBoxLayout()
        min_perc_layout.addWidget(QLabel("Min % to show:"))
        self.min_percentage_spin = QDoubleSpinBox()
        self.min_percentage_spin.setRange(0.0, 10.0)
        self.min_percentage_spin.setDecimals(1)
        self.min_percentage_spin.setValue(self.min_percentage)
        self.min_percentage_spin.setSuffix("%")
        self.min_percentage_spin.valueChanged.connect(self.set_min_percentage)
        min_perc_layout.addWidget(self.min_percentage_spin)
        min_perc_layout.addStretch()
        display_layout.addLayout(min_perc_layout)
        
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
        
        # Start angle
        start_angle_layout = QHBoxLayout()
        start_angle_layout.addWidget(QLabel("Start angle:"))
        self.start_angle_spin = QSpinBox()
        self.start_angle_spin.setRange(0, 360)
        self.start_angle_spin.setValue(self.start_angle)
        self.start_angle_spin.setSuffix("°")
        self.start_angle_spin.valueChanged.connect(self.set_start_angle)
        start_angle_layout.addWidget(self.start_angle_spin)
        start_angle_layout.addStretch()
        style_layout.addLayout(start_angle_layout)
        
        control_panel.addWidget(style_group)
        
        # Advanced options
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(advanced_group)
        
        # Color scheme
        color_scheme_layout = QHBoxLayout()
        color_scheme_layout.addWidget(QLabel("Color scheme:"))
        self.color_scheme_combo = QComboBox()
        self.color_scheme_combo.addItems(['Set3', 'Set2', 'Set1', 'Pastel1', 'Pastel2', 'tab10', 'tab20', 'viridis', 'plasma', 'inferno'])
        self.color_scheme_combo.setCurrentText(self.color_scheme)
        self.color_scheme_combo.currentTextChanged.connect(self.set_color_scheme)
        color_scheme_layout.addWidget(self.color_scheme_combo)
        advanced_layout.addLayout(color_scheme_layout)
        
        # Edge color
        edge_color_layout = QHBoxLayout()
        edge_color_layout.addWidget(QLabel("Edge color:"))
        self.edge_color_btn = QPushButton()
        edge_color = QColor(self.edge_color)
        self.edge_color_btn.setStyleSheet(f"background-color: {edge_color.name()}; border: 1px solid #ccc; min-width: 80px;")
        self.edge_color_btn.setText(edge_color.name())
        self.edge_color_btn.clicked.connect(self.choose_edge_color)
        edge_color_layout.addWidget(self.edge_color_btn)
        advanced_layout.addLayout(edge_color_layout)
        
        # Edge width
        edge_width_layout = QHBoxLayout()
        edge_width_layout.addWidget(QLabel("Edge width:"))
        self.edge_width_spin = QDoubleSpinBox()
        self.edge_width_spin.setRange(0.0, 5.0)
        self.edge_width_spin.setDecimals(1)
        self.edge_width_spin.setValue(self.edge_width)
        self.edge_width_spin.valueChanged.connect(self.set_edge_width)
        edge_width_layout.addWidget(self.edge_width_spin)
        edge_width_layout.addStretch()
        advanced_layout.addLayout(edge_width_layout)
        
        # Shadow
        self.shadow_check = QCheckBox("Shadow effect")
        self.shadow_check.setChecked(self.shadow)
        self.shadow_check.toggled.connect(self.set_shadow)
        advanced_layout.addWidget(self.shadow_check)
        
        # Text position
        text_pos_layout = QHBoxLayout()
        text_pos_layout.addWidget(QLabel("Text position:"))
        self.text_position_combo = QComboBox()
        self.text_position_combo.addItems(['auto', 'inside', 'outside'])
        self.text_position_combo.setCurrentText(self.text_position)
        self.text_position_combo.currentTextChanged.connect(self.set_text_position)
        text_pos_layout.addWidget(self.text_position_combo)
        advanced_layout.addLayout(text_pos_layout)
        
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
        
        label_font_layout = QHBoxLayout()
        label_font_layout.addWidget(QLabel("Label font size:"))
        self.label_font_size_spin = QSpinBox()
        self.label_font_size_spin.setRange(6, 18)
        self.label_font_size_spin.setValue(self.label_font_size)
        self.label_font_size_spin.valueChanged.connect(self.set_label_font_size)
        label_font_layout.addWidget(self.label_font_size_spin)
        label_font_layout.addStretch()
        advanced_layout.addLayout(label_font_layout)
        
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
        
        # Chart labels
        labels_group = QGroupBox("Chart Labels")
        labels_layout = QVBoxLayout(labels_group)
        
        # Chart title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Leave empty to use field name")
        self.title_edit.setText(self.chart_title)
        self.title_edit.textChanged.connect(self.set_chart_title)
        title_layout.addWidget(self.title_edit)
        labels_layout.addLayout(title_layout)
        
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
        Update data and chart with the selected field.
        
        Args:
            field_name: The field name to chart (optional, uses current selection if None)
        """
        if field_name is None:
            field_name = self.field_combo.currentText()
        
        # Skip if no field selected or if it's the default placeholder
        if not field_name or field_name == "-- Select Field --":
            return
        
        self.field_name = field_name
        
        # Get data from features (works with any field type - text, numeric, etc.)
        self.values = []
        
        for feature in self.layer.getFeatures():
            value = feature[field_name]
            # Handle NULL values
            if value is None:
                continue
            # Handle NaN/Inf for numeric values
            if isinstance(value, (int, float)) and (np.isnan(value) or np.isinf(value)):
                continue
            # Add value as-is (can be string, number, etc.)
            self.values.append(value)
        
        # Update the chart
        self.update_chart()
    
    def set_show_percentages(self, show):
        """Set whether to show percentages."""
        self.show_percentages = show
        self.update_chart()
    
    def set_show_labels(self, show):
        """Set whether to show labels."""
        self.show_labels = show
        self.update_chart()
    
    def set_explode_smallest(self, explode):
        """Set whether to explode the smallest slice."""
        self.explode_smallest = explode
        self.update_chart()
    
    def set_min_percentage(self, value):
        """Set the minimum percentage to show."""
        self.min_percentage = value
        self.update_chart()
    
    def set_style_preset(self, preset):
        """Set the style preset for the chart."""
        self.style_preset = preset
        self.update_chart()
    
    def set_start_angle(self, angle):
        """Set the start angle for the pie chart."""
        self.start_angle = angle
        self.update_chart()
    
    def set_chart_title(self, title):
        """Set the chart title."""
        self.chart_title = title
        self.update_chart()
    
    def set_color_scheme(self, scheme):
        """Set the color scheme."""
        self.color_scheme = scheme
        self.update_chart()
    
    def set_edge_color(self, color):
        """Set the edge color."""
        self.edge_color = color
        self.update_chart()
    
    def choose_edge_color(self):
        """Open color dialog to choose edge color."""
        color = QColorDialog.getColor(QColor(self.edge_color), self, "Choose Edge Color")
        if color.isValid():
            self.edge_color = color.name()
            self.edge_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc; min-width: 80px;")
            self.edge_color_btn.setText(color.name())
            self.update_chart()
    
    def set_edge_width(self, width):
        """Set the edge width."""
        self.edge_width = width
        self.update_chart()
    
    def set_shadow(self, shadow):
        """Set whether to show shadow."""
        self.shadow = shadow
        self.update_chart()
    
    def set_text_position(self, position):
        """Set the text position."""
        self.text_position = position
        self.update_chart()
    
    def set_title_font_size(self, size):
        """Set the title font size."""
        self.title_font_size = size
        self.update_chart()
    
    def set_label_font_size(self, size):
        """Set the label font size."""
        self.label_font_size = size
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
        if not self.field_name or not self.values:
            return
        
        # Apply style preset
        with plt.style.context(self.style_preset):
            # Clear the figure
            self.figure.clear()
            
            # Create subplot
            ax = self.figure.add_subplot(111)
            
            # Aggregate values (count occurrences by value)
            # For pie charts, we show unique values and their counts
            # Works with any data type (text, numbers, etc.)
            value_counts = Counter(self.values)
            labels_list = []
            sizes_list = []
            
            total = sum(value_counts.values())
            
            # Filter by minimum percentage if set
            for value, count in value_counts.items():
                percentage = (count / total) * 100 if total > 0 else 0
                if percentage >= self.min_percentage:
                    # Convert value to string for display (handles any type)
                    labels_list.append(str(value))
                    sizes_list.append(count)
            
            if not sizes_list:
                ax.text(0.5, 0.5, "No data to display with current filters", 
                       ha='center', va='center', transform=ax.transAxes)
                self.figure.tight_layout()
                self.canvas.draw()
                return
            
            # Calculate percentages
            total_filtered = sum(sizes_list)
            percentages = [(size / total_filtered) * 100 if total_filtered > 0 else 0 for size in sizes_list]
            
            # Create explode array if needed
            explode = None
            if self.explode_smallest and sizes_list:
                explode = [0.0] * len(sizes_list)
                min_index = sizes_list.index(min(sizes_list))
                explode[min_index] = 0.1
            
            # Create pie chart with color scheme
            try:
                cmap = plt.cm.get_cmap(self.color_scheme)
                colors = cmap(np.linspace(0, 1, len(sizes_list)))
            except:
                # Fallback to Set3 if colormap not found
                colors = plt.cm.Set3(np.linspace(0, 1, len(sizes_list)))
            
            # Prepare labels
            pie_labels = None
            use_autopct = False
            if self.show_labels:
                if self.show_percentages:
                    pie_labels = [f'{label}\n{percent:.1f}%' for label, percent in zip(labels_list, percentages)]
                else:
                    pie_labels = labels_list
            elif self.show_percentages:
                pie_labels = [f'{percent:.1f}%' for percent in percentages]
            else:
                # No labels or percentages, use autopct
                use_autopct = True
            
            # Determine textprops based on text position
            textprops = {'fontsize': self.label_font_size}
            if self.text_position == 'inside':
                textprops['color'] = 'white'
            elif self.text_position == 'outside':
                textprops['color'] = 'black'
            
            # Handle different matplotlib versions - newer versions return 2 values when autopct=None
            pie_result = ax.pie(
                sizes_list,
                labels=pie_labels,
                autopct='%1.1f%%' if use_autopct else None,
                startangle=self.start_angle,
                explode=explode,
                colors=colors,
                wedgeprops={'edgecolor': self.edge_color, 'linewidth': self.edge_width},
                textprops=textprops,
                shadow=self.shadow
            )
            
            # Unpack result based on what matplotlib returned
            if len(pie_result) == 3:
                wedges, texts, autotexts = pie_result
            else:
                wedges, texts = pie_result
                autotexts = []
            
            # Set title with custom font size
            title = self.chart_title if self.chart_title else f"{self.field_name} Distribution"
            ax.set_title(title, fontsize=self.title_font_size)
            
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
        if not self.field_name:
            return
        
        # Get the export directory from settings or use default
        settings = QSettings()
        last_dir = settings.value("RightClickUtilities/export_chart_dir", os.path.expanduser("~"))
        
        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{self.layer.name()}_{self.field_name}_pie_{timestamp}.{format_type}"
        
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
            
            # Save the figure using configured DPI when available
            try:
                export_dpi = int(self.settings.get('export_dpi', 300)) if isinstance(self.settings, dict) else 300
                self.figure.savefig(file_path, format=format_type, dpi=export_dpi, bbox_inches='tight')
                # Show success message
                QLabel(f"Chart exported to {file_path}").setWindowTitle("Export Successful")
            except Exception as e:
                QLabel(f"Failed to export chart: {str(e)}").setWindowTitle("Export Failed")


class CreatePieChartPolygonAction(BaseAction):
    """Action to create pie charts for polygon features."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_pie_chart_polygon"
        self.name = "Create Pie Chart"
        self.category = "Analysis"
        self.description = "Create a pie chart visualization of attribute values for polygon features. Allows selection of any field to visualize, displaying value distribution as proportions. Works with text, numeric, and other field types. Supports exporting charts, visual presets, and customization options."
        self.enabled = True
        
        # Action scoping - works on layers (affects all features in layer)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
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
            'show_percentages': {
                'type': 'bool',
                'default': True,
                'label': 'Default Show Percentages',
                'description': 'Default setting for showing percentages (can be changed in chart dialog)',
            },
            'show_labels': {
                'type': 'bool',
                'default': True,
                'label': 'Default Show Labels',
                'description': 'Default setting for showing labels (can be changed in chart dialog)',
            },
            'start_angle': {
                'type': 'int',
                'default': 0,
                'label': 'Default Start Angle',
                'description': 'Default start angle for the pie chart in degrees (can be changed in chart dialog)',
                'min': 0,
                'max': 360,
                'step': 15,
            },
            'explode_smallest': {
                'type': 'bool',
                'default': False,
                'label': 'Default Explode Smallest',
                'description': 'Default setting for exploding the smallest slice (can be changed in chart dialog)',
            },
            'min_percentage': {
                'type': 'float',
                'default': 0.0,
                'label': 'Default Minimum Percentage',
                'description': 'Default minimum percentage to show slices (can be changed in chart dialog)',
                'min': 0.0,
                'max': 10.0,
                'step': 0.1,
            },
            
            # Chart labels
            'chart_title': {
                'type': 'str',
                'default': '',
                'label': 'Default Chart Title',
                'description': 'Default title for the chart (leave empty to use field name)',
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
        """Execute the create pie chart action."""
        # Get settings with proper type conversion
        try:
            # Display settings
            max_features_warning = int(self.get_setting('max_features_warning', 1000))
            default_chart_width = int(self.get_setting('default_chart_width', 800))
            default_chart_height = int(self.get_setting('default_chart_height', 600))
            
            # Style settings
            style_preset = str(self.get_setting('style_preset', 'default'))
            show_percentages = bool(self.get_setting('show_percentages', True))
            show_labels = bool(self.get_setting('show_labels', True))
            start_angle = int(self.get_setting('start_angle', 0))
            explode_smallest = bool(self.get_setting('explode_smallest', False))
            min_percentage = float(self.get_setting('min_percentage', 0.0))
            
            # Chart labels
            chart_title = str(self.get_setting('chart_title', ''))
            
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
            self.show_warning("Empty Layer", "The selected layer has no features to chart.")
            return
        
        if feature_count > max_features_warning:
            if not self.confirm_action(
                "Large Layer Warning",
                f"The selected layer has {feature_count} features, which may make the chart crowded or slow to generate. Continue anyway?"
            ):
                return
        
        # Get all fields from the layer (pie charts work with any field type)
        available_fields = []
        for field in layer.fields():
            available_fields.append(field.name())
        
        if not available_fields:
            self.show_warning("No Fields", 
                             "The selected layer has no fields to chart.")
            return
        
        # Collect all settings to pass to the dialog
        chart_settings = {
            'style_preset': style_preset,
            'show_percentages': show_percentages,
            'show_labels': show_labels,
            'start_angle': start_angle,
            'explode_smallest': explode_smallest,
            'min_percentage': min_percentage,
            'default_export_format': default_export_format,
            'export_dpi': export_dpi,
            'chart_title': chart_title,
        }
        
        # Create and show the chart dialog
        try:
            dialog = PieChartDialog(layer, available_fields, chart_settings)
            dialog.resize(default_chart_width, default_chart_height)
            dialog.exec_()

            # Record informational history entry (non-undoable)
            try:
                hm = get_history_manager()
                desc = f"Displayed pie chart for layer '{layer.name()}'"
                meta = {
                    'layer_id': layer.id(),
                    'layer_name': layer.name(),
                    'field': getattr(dialog, 'field_name', ''),
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
            self.show_error("Error", f"Failed to create pie chart: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_pie_chart_polygon_action = CreatePieChartPolygonAction()

