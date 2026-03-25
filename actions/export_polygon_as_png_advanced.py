"""
Export Polygon as PNG Advanced Action for Right-click Utilities and Shortcuts Hub

This is a copy of the original export polygon action to serve as an "advanced"
variant; additional features will be added later.
"""

from .base_action import BaseAction
import os
from datetime import datetime


class ExportPolygonAsPngAdvancedAction(BaseAction):
    """
    Action to export the selected polygon feature as a PNG image (advanced).
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "export_polygon_as_png_advanced"
        self.name = "Export Polygon as PNG (Advanced)"
        self.category = "Export"
        self.description = "Advanced export: export the selected polygon feature as a PNG image showing only the borders. This advanced copy will receive new features later."
        self.enabled = True
        
        # Action scoping configuration - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
        
        # Debug output
        print(f"ExportPolygonAsPngAdvancedAction initialized: {self.action_id}")
    
    def get_settings_schema(self):
        return {
            'border_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Border Color',
                'description': 'Color for the polygon border in the exported PNG',
            },
            'border_width': {
                'type': 'int',
                'default': 2,
                'label': 'Border Width (pixels)',
                'description': 'Width of the polygon border in pixels',
                'min': 1,
                'max': 10,
                'step': 1,
            },
            'background_color': {
                'type': 'color',
                'default': '#FFFFFF',
                'label': 'Background Color',
                'description': 'Background color for the exported PNG',
            },
            'image_size': {
                'type': 'int',
                'default': 800,
                'label': 'Image Size (pixels)',
                'description': 'Size of the exported PNG image (square)',
                'min': 200,
                'max': 2000,
                'step': 50,
            },
            'padding_percentage': {
                'type': 'float',
                'default': 10.0,
                'label': 'Padding Percentage',
                'description': 'Percentage of padding around the polygon in the image',
                'min': 0.0,
                'max': 50.0,
                'step': 1.0,
            },
            'save_directory': {
                'type': 'directory_path',
                'default': '~\/Downloads',
                'label': 'Save Directory',
                'description': 'Directory where PNG files will be saved',
            },
            'filename_template': {
                'type': 'str',
                'default': 'polygon_{feature_id}_{timestamp}',
                'label': 'Filename Template',
                'description': 'Template for PNG filenames. Available variables: {feature_id}, {timestamp}, {date}, {time}',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when PNG is saved successfully',
            },
            # Title defaults and controls
            'default_title_font_size': {
                'type': 'int',
                'default': 24,
                'label': 'Title Font Size',
                'description': 'Default font size for the title in the preview/export (points)',
                'min': 8,
                'max': 200,
                'step': 1,
            },
            'default_title_font_color': {
                'type': 'color',
                'default': '#000000',
                'label': 'Title Font Color',
                'description': 'Default title font color',
            },
            'default_title_bg_opacity': {
                'type': 'float',
                'default': 0.8,
                'label': 'Title Background Opacity',
                'description': 'Default opacity for the title background rectangle (0.0 - 1.0)',
                'min': 0.0,
                'max': 1.0,
                'step': 0.05,
            },
            'default_title_position': {
                'type': 'choice',
                'default': 'top',
                'label': 'Title Position',
                'description': 'Default title position on the image',
                'options': ['top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right'],
            },
            'default_title_alignment': {
                'type': 'choice',
                'default': 'center',
                'label': 'Title Alignment',
                'description': 'Default horizontal alignment for the title',
                'options': ['center', 'left', 'right'],
            },
            'default_title_padding': {
                'type': 'int',
                'default': 10,
                'label': 'Title Padding (px)',
                'description': 'Default padding (in pixels) around the title rectangle',
                'min': 0,
                'max': 200,
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
            from qgis.PyQt.QtCore import QSettings, QSize, QRectF, QPointF, Qt
            from qgis.PyQt.QtGui import QColor, QPainter, QPen, QBrush, QImage, QPolygonF, QTransform, QPixmap
            from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QDialog, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QMessageBox
            from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, 
                                 QgsCoordinateTransform, QgsRectangle, QgsWkbTypes, QgsMapSettings,
                                 QgsRenderContext, QgsMapRendererCustomPainterJob, QgsSingleSymbolRenderer,
                                 QgsSymbol, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer, QgsMapLayer)
            from qgis.gui import QgsMapCanvas
        except ImportError as e:
            self.show_error("Error", f"Failed to import required modules: {str(e)}")
            return
        
        try:
            schema = self.get_settings_schema()
            border_color = str(self.get_setting('border_color', schema['border_color']['default']))
            border_width = int(self.get_setting('border_width', schema['border_width']['default']))
            background_color = str(self.get_setting('background_color', schema['background_color']['default']))
            image_size = int(self.get_setting('image_size', schema['image_size']['default']))
            padding_percentage = float(self.get_setting('padding_percentage', schema['padding_percentage']['default']))
            save_directory = str(self.get_setting('save_directory', schema['save_directory']['default']))
            filename_template = str(self.get_setting('filename_template', schema['filename_template']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))

            # Title defaults
            default_title_font_size = int(self.get_setting('default_title_font_size', schema['default_title_font_size']['default']))
            default_title_font_color = str(self.get_setting('default_title_font_color', schema['default_title_font_color']['default']))
            default_title_bg_opacity = float(self.get_setting('default_title_bg_opacity', schema['default_title_bg_opacity']['default']))
            default_title_position = str(self.get_setting('default_title_position', schema['default_title_position']['default']))
            default_title_alignment = str(self.get_setting('default_title_alignment', schema['default_title_alignment']['default']))
            default_title_padding = int(self.get_setting('default_title_padding', schema['default_title_padding']['default']))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        if not canvas:
            self.show_error("Error", "Canvas not available")
            return
        
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            geometry = feature.geometry()
            if not geometry:
                self.show_error("Error", "Feature has no geometry")
                return
            
            extent = geometry.boundingBox()
            if extent.isEmpty():
                self.show_error("Error", "Feature has empty extent")
                return
            
            width = extent.width()
            height = extent.height()
            padding_x = width * (padding_percentage / 100.0)
            padding_y = height * (padding_percentage / 100.0)
            
            padded_extent = QgsRectangle(
                extent.xMinimum() - padding_x,
                extent.yMinimum() - padding_y,
                extent.xMaximum() + padding_x,
                extent.yMaximum() + padding_y
            )
            
            image = QImage(image_size, image_size, QImage.Format_ARGB32)
            image.fill(QColor(background_color))
            
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            
            map_settings = QgsMapSettings()
            map_settings.setOutputSize(QSize(image_size, image_size))
            map_settings.setExtent(padded_extent)
            map_settings.setDestinationCrs(layer.crs())
            map_settings.setBackgroundColor(QColor(background_color))
            
            canvas_layers = []
            for canvas_layer in canvas.layers():
                if canvas_layer.isValid():
                    layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(canvas_layer.id())
                    if layer_tree_layer and layer_tree_layer.isVisible():
                        canvas_layers.append(canvas_layer)
            
            temp_layer = self.create_temp_layer_with_feature(layer, feature, border_color, border_width)
            
            all_layers = canvas_layers + [temp_layer]
            map_settings.setLayers(all_layers)
            
            job = QgsMapRendererCustomPainterJob(map_settings, painter)
            job.renderSynchronously()
            
            painter.end()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            date = datetime.now().strftime("%Y%m%d")
            time = datetime.now().strftime("%H%M%S")
            
            filename = filename_template.format(
                feature_id=feature.id(),
                timestamp=timestamp,
                date=date,
                time=time
            )
            
            if not filename.endswith('.png'):
                filename += '.png'
            
            if save_directory.startswith('~'):
                save_directory = os.path.expanduser(save_directory)
            
            os.makedirs(save_directory, exist_ok=True)
            
            file_path = os.path.join(save_directory, filename)
            
            # Show preview dialog and allow user to Save/Save As/Cancel
            saved_path_holder = {'path': None}

            pixmap = QPixmap.fromImage(image)
            dialog = QDialog()
            dialog.setWindowTitle("Export Preview")
            dlg_layout = QVBoxLayout(dialog)

            # Determine screen available size and resize dialog so full preview fits when possible
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                max_w = max(200, avail.width() - 100)
                max_h = max(200, avail.height() - 150)
            else:
                max_w = min(1200, pixmap.width() + 40)
                max_h = min(800, pixmap.height() + 80)

            desired_w = min(pixmap.width() + 40, max_w)
            desired_h = min(pixmap.height() + 80, max_h)
            dialog.resize(desired_w, desired_h)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            # Scale displayed pixmap only if it doesn't fit the dialog
            display_pix = pixmap
            if pixmap.width() > desired_w - 40 or pixmap.height() > desired_h - 120:
                display_pix = pixmap.scaled(desired_w - 40, desired_h - 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(display_pix)
            scroll.setWidget(label)
            dlg_layout.addWidget(scroll)

            # Title input and controls for preview
            from qgis.PyQt.QtWidgets import QLineEdit, QSpinBox, QComboBox, QColorDialog, QDoubleSpinBox
            from qgis.PyQt.QtGui import QFont

            title_layout = QHBoxLayout()
            title_label = QLabel("Title:")
            title_input = QLineEdit()
            title_input.setPlaceholderText("Enter image title (optional)")
            title_layout.addWidget(title_label)
            title_layout.addWidget(title_input)
            dlg_layout.addLayout(title_layout)

            controls_layout = QHBoxLayout()
            # Font size
            font_size_label = QLabel("Font Size:")
            font_size_spin = QSpinBox()
            font_size_spin.setRange(8, 200)
            font_size_spin.setValue(default_title_font_size)
            controls_layout.addWidget(font_size_label)
            controls_layout.addWidget(font_size_spin)
            # Position
            position_label = QLabel("Position:")
            position_combo = QComboBox()
            position_combo.addItems(["Top", "Bottom", "Left", "Right", "Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"])
            pos_map = {'top': 0, 'bottom': 1, 'left': 2, 'right': 3, 'top_left': 4, 'top_right': 5, 'bottom_left': 6, 'bottom_right': 7}
            position_combo.setCurrentIndex(pos_map.get(default_title_position, 0))
            controls_layout.addWidget(position_label)
            controls_layout.addWidget(position_combo)
            # Alignment
            align_label = QLabel("Align:")
            align_combo = QComboBox()
            align_combo.addItems(["Center", "Left", "Right"])
            align_map = {'center': 0, 'left': 1, 'right': 2}
            align_combo.setCurrentIndex(align_map.get(default_title_alignment, 0))
            controls_layout.addWidget(align_label)
            controls_layout.addWidget(align_combo)
            # Font color button
            font_color_btn = QPushButton("Font Color")
            font_color = QColor(default_title_font_color)
            def pick_font_color():
                nonlocal font_color
                c = QColorDialog.getColor(font_color)
                if c.isValid():
                    font_color = c
                    font_color_btn.setStyleSheet(f"background-color: {c.name()}")
                    update_preview()
            font_color_btn.clicked.connect(pick_font_color)
            font_color_btn.setStyleSheet(f"background-color: {font_color.name()}")
            controls_layout.addWidget(font_color_btn)
            # Background opacity
            bg_opacity_label = QLabel("BG Opacity:")
            bg_opacity_spin = QDoubleSpinBox()
            bg_opacity_spin.setRange(0.0, 1.0)
            bg_opacity_spin.setSingleStep(0.05)
            bg_opacity_spin.setValue(default_title_bg_opacity)
            controls_layout.addWidget(bg_opacity_label)
            controls_layout.addWidget(bg_opacity_spin)
            # Padding
            padding_label = QLabel("Padding:")
            padding_spin = QSpinBox()
            padding_spin.setRange(0, 200)
            padding_spin.setValue(default_title_padding)
            controls_layout.addWidget(padding_label)
            controls_layout.addWidget(padding_spin)

            # Embedded image controls
            embed_layout = QHBoxLayout()
            embed_btn = QPushButton("Browse Image...")
            embed_preview_label = QLabel()
            embed_preview_label.setFixedSize(80, 80)
            embed_preview_label.setAlignment(Qt.AlignCenter)
            embed_layout.addWidget(embed_btn)
            embed_layout.addWidget(embed_preview_label)
            embed_size_label = QLabel("Embed Size %:")
            embed_size_spin = QSpinBox()
            embed_size_spin.setRange(5, 200)
            embed_size_spin.setValue(50)
            embed_layout.addWidget(embed_size_label)
            embed_layout.addWidget(embed_size_spin)
            embed_pos_label = QLabel("Embed Pos:")
            embed_pos_combo = QComboBox()
            embed_pos_combo.addItems(["Center","Top","Bottom","Left","Right","Top-Left","Top-Right","Bottom-Left","Bottom-Right"])
            embed_layout.addWidget(embed_pos_label)
            embed_layout.addWidget(embed_pos_combo)
            dlg_layout.addLayout(embed_layout)

            embedded_pixmap = None
            embedded_path = None

            def browse_embed():
                nonlocal embedded_pixmap, embedded_path
                path, _ = QFileDialog.getSaveFileName(None, "Choose image to embed", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)")
                # QFileDialog.getSaveFileName used to keep consistent imports; allow open as well
                if not path:
                    # try open dialog fallback
                    path, _ = QFileDialog.getOpenFileName(None, "Choose image to embed", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)")
                if path:
                    try:
                        pm = QPixmap(path)
                        if not pm.isNull():
                            embedded_pixmap = pm
                            embedded_path = path
                            thumb = pm.scaled(embed_preview_label.width(), embed_preview_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            embed_preview_label.setPixmap(thumb)
                            update_preview()
                    except Exception:
                        pass

            embed_btn.clicked.connect(browse_embed)
            embed_size_spin.valueChanged.connect(lambda _: update_preview())
            embed_pos_combo.currentIndexChanged.connect(lambda _: update_preview())

            dlg_layout.addLayout(controls_layout)

            btn_layout = QHBoxLayout()
            save_btn = QPushButton("Save")
            save_as_btn = QPushButton("Save As...")
            cancel_btn = QPushButton("Cancel")
            btn_layout.addWidget(save_btn)
            btn_layout.addWidget(save_as_btn)
            btn_layout.addWidget(cancel_btn)
            dlg_layout.addLayout(btn_layout)

            # Helper to render image + title into a QPixmap for preview
            def render_preview_pixmap(title_text: str, font_size: int, font_qcolor: QColor, bg_opacity: float, position: str, alignment: str, padding: int):
                preview_img = QImage(image)  # copy
                need_embed = embedded_pixmap is not None
                if not (title_text or need_embed):
                    return QPixmap.fromImage(preview_img)

                p = QPainter(preview_img)
                p.setRenderHint(QPainter.Antialiasing)

                margin = padding
                # draw embedded image first if provided
                try:
                    if embedded_pixmap is not None:
                        esz = embed_size_spin.value()
                        # target width as percent of image width
                        target_w = max(1, int(preview_img.width() * (esz / 100.0)))
                        target_h = int(embedded_pixmap.height() * (target_w / embedded_pixmap.width())) if embedded_pixmap.width() > 0 else target_w
                        epos_idx = embed_pos_combo.currentIndex()
                        # compute embedded rect position
                        if epos_idx == 0:  # center
                            ex = (preview_img.width() - target_w) // 2
                            ey = (preview_img.height() - target_h) // 2
                        elif epos_idx == 1:  # top
                            ex = (preview_img.width() - target_w) // 2
                            ey = margin
                        elif epos_idx == 2:  # bottom
                            ex = (preview_img.width() - target_w) // 2
                            ey = preview_img.height() - target_h - margin
                        elif epos_idx == 3:  # left
                            ex = margin
                            ey = (preview_img.height() - target_h) // 2
                        elif epos_idx == 4:  # right
                            ex = preview_img.width() - target_w - margin
                            ey = (preview_img.height() - target_h) // 2
                        elif epos_idx == 5:  # top_left
                            ex = margin
                            ey = margin
                        elif epos_idx == 6:  # top_right
                            ex = preview_img.width() - target_w - margin
                            ey = margin
                        elif epos_idx == 7:  # bottom_left
                            ex = margin
                            ey = preview_img.height() - target_h - margin
                        elif epos_idx == 8:  # bottom_right
                            ex = preview_img.width() - target_w - margin
                            ey = preview_img.height() - target_h - margin
                        else:
                            ex = (preview_img.width() - target_w) // 2
                            ey = (preview_img.height() - target_h) // 2
                        p.drawPixmap(QRectF(ex, ey, target_w, target_h).toRect(), embedded_pixmap)
                except Exception:
                    pass

                if title_text:
                    font = QFont()
                    font.setPointSize(font_size)
                    font.setBold(True)
                    p.setFont(font)
                    # Measure text
                    metrics = p.fontMetrics()
                    text_width = metrics.horizontalAdvance(title_text)
                    text_height = metrics.height()
                    rect_w = text_width + margin * 2
                    rect_h = text_height + margin // 2
                    rect_x = (preview_img.width() - rect_w) // 2
                    pos = position.lower()
                    if pos == 'top':
                        rect_y = margin
                    elif pos == 'bottom':
                        rect_y = preview_img.height() - rect_h - margin
                    elif pos == 'left':
                        rect_y = (preview_img.height() - rect_h) // 2
                        rect_x = margin
                    elif pos == 'right':
                        rect_y = (preview_img.height() - rect_h) // 2
                        rect_x = preview_img.width() - rect_w - margin
                    elif pos == 'top_left':
                        rect_x = margin
                        rect_y = margin
                    elif pos == 'top_right':
                        rect_x = preview_img.width() - rect_w - margin
                        rect_y = margin
                    elif pos == 'bottom_left':
                        rect_x = margin
                        rect_y = preview_img.height() - rect_h - margin
                    elif pos == 'bottom_right':
                        rect_x = preview_img.width() - rect_w - margin
                        rect_y = preview_img.height() - rect_h - margin
                    alpha = max(0, min(255, int(bg_opacity * 255)))
                    bg_color = QColor(255, 255, 255, alpha)
                    p.setBrush(QBrush(bg_color))
                    p.setPen(Qt.NoPen)
                    p.drawRect(rect_x, rect_y, rect_w, rect_h)
                    # Draw text
                    p.setPen(font_qcolor)
                    align_flag = Qt.AlignHCenter
                    if alignment.lower() == 'left':
                        align_flag = Qt.AlignLeft
                    elif alignment.lower() == 'right':
                        align_flag = Qt.AlignRight
                    p.drawText(QRectF(rect_x, rect_y, rect_w, rect_h), align_flag | Qt.AlignVCenter, title_text)

                p.end()
                return QPixmap.fromImage(preview_img)

            # Update preview from current controls
            def update_preview():
                try:
                    t = title_input.text()
                    fs = font_size_spin.value()
                    fc = font_color
                    bo = bg_opacity_spin.value()
                    idx = position_combo.currentIndex()
                    pos = ['top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right'][idx] if 0 <= idx < 8 else 'top'
                    aln = ['center', 'left', 'right'][align_combo.currentIndex()]
                    pad = padding_spin.value()
                    pix = render_preview_pixmap(t, fs, fc, bo, pos, aln, pad)
                    # scale preview to dialog if needed so entire image is visible
                    dw = dialog.width() - 40
                    dh = dialog.height() - 120
                    display = pix
                    if pix.width() > dw or pix.height() > dh:
                        display = pix.scaled(dw, dh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    label.setPixmap(display)
                except Exception:
                    pass

            # Connect signals
            title_input.textChanged.connect(lambda _: update_preview())
            font_size_spin.valueChanged.connect(lambda _: update_preview())
            position_combo.currentIndexChanged.connect(lambda _: update_preview())
            align_combo.currentIndexChanged.connect(lambda _: update_preview())
            bg_opacity_spin.valueChanged.connect(lambda _: update_preview())
            padding_spin.valueChanged.connect(lambda _: update_preview())
            # initialize preview
            update_preview()

            def on_save():
                # Save to default file_path, drawing title with user controls
                title_text = title_input.text().strip()
                final_img = QImage(image)  # copy
                need_embed = embedded_pixmap is not None
                if title_text or need_embed:
                    p = QPainter(final_img)
                    p.setRenderHint(QPainter.Antialiasing)
                    pad = padding_spin.value()
                    # draw embedded image first if present
                    try:
                        if need_embed:
                            esz = embed_size_spin.value()
                            target_w = max(1, int(final_img.width() * (esz / 100.0)))
                            target_h = int(embedded_pixmap.height() * (target_w / embedded_pixmap.width())) if embedded_pixmap.width() > 0 else target_w
                            epos_idx = embed_pos_combo.currentIndex()
                            if epos_idx == 0:  # center
                                ex = (final_img.width() - target_w) // 2
                                ey = (final_img.height() - target_h) // 2
                            elif epos_idx == 1:  # top
                                ex = (final_img.width() - target_w) // 2
                                ey = pad
                            elif epos_idx == 2:  # bottom
                                ex = (final_img.width() - target_w) // 2
                                ey = final_img.height() - target_h - pad
                            elif epos_idx == 3:  # left
                                ex = pad
                                ey = (final_img.height() - target_h) // 2
                            elif epos_idx == 4:  # right
                                ex = final_img.width() - target_w - pad
                                ey = (final_img.height() - target_h) // 2
                            elif epos_idx == 5:  # top_left
                                ex = pad
                                ey = pad
                            elif epos_idx == 6:  # top_right
                                ex = final_img.width() - target_w - pad
                                ey = pad
                            elif epos_idx == 7:  # bottom_left
                                ex = pad
                                ey = final_img.height() - target_h - pad
                            elif epos_idx == 8:  # bottom_right
                                ex = final_img.width() - target_w - pad
                                ey = final_img.height() - target_h - pad
                            else:
                                ex = (final_img.width() - target_w) // 2
                                ey = (final_img.height() - target_h) // 2
                            p.drawPixmap(QRectF(ex, ey, target_w, target_h).toRect(), embedded_pixmap)
                    except Exception:
                        pass
                    if title_text:
                        fs = font_size_spin.value()
                        font = QFont()
                        font.setPointSize(fs)
                        font.setBold(True)
                        p.setFont(font)
                        metrics = p.fontMetrics()
                        text_width = metrics.horizontalAdvance(title_text)
                        text_height = metrics.height()
                        rect_w = text_width + pad * 2
                        rect_h = text_height + pad // 2
                        pos_index = position_combo.currentIndex()
                        # compute rect_x, rect_y for all supported positions including corners
                        if pos_index == 0:  # top
                            rect_x = (final_img.width() - rect_w) // 2
                            rect_y = pad
                        elif pos_index == 1:  # bottom
                            rect_x = (final_img.width() - rect_w) // 2
                            rect_y = final_img.height() - rect_h - pad
                        elif pos_index == 2:  # left
                            rect_x = pad
                            rect_y = (final_img.height() - rect_h) // 2
                        elif pos_index == 3:  # right
                            rect_x = final_img.width() - rect_w - pad
                            rect_y = (final_img.height() - rect_h) // 2
                        elif pos_index == 4:  # top_left
                            rect_x = pad
                            rect_y = pad
                        elif pos_index == 5:  # top_right
                            rect_x = final_img.width() - rect_w - pad
                            rect_y = pad
                        elif pos_index == 6:  # bottom_left
                            rect_x = pad
                            rect_y = final_img.height() - rect_h - pad
                        elif pos_index == 7:  # bottom_right
                            rect_x = final_img.width() - rect_w - pad
                            rect_y = final_img.height() - rect_h - pad
                        else:
                            rect_x = (final_img.width() - rect_w) // 2
                            rect_y = pad
                        alpha = max(0, min(255, int(bg_opacity_spin.value() * 255)))
                        bg_color = QColor(255, 255, 255, alpha)
                        p.setBrush(QBrush(bg_color))
                        p.setPen(Qt.NoPen)
                        p.drawRect(rect_x, rect_y, rect_w, rect_h)
                        # Draw text
                        p.setPen(font_color)
                        aln = ['center', 'left', 'right'][align_combo.currentIndex()]
                        align_flag = Qt.AlignHCenter
                        if aln == 'left':
                            align_flag = Qt.AlignLeft
                        elif aln == 'right':
                            align_flag = Qt.AlignRight
                        p.drawText(QRectF(rect_x, rect_y, rect_w, rect_h), align_flag | Qt.AlignVCenter, title_text)
                    p.end()
                if final_img.save(file_path, 'PNG'):
                    saved_path_holder['path'] = file_path
                    dialog.accept()
                else:
                    QMessageBox.critical(None, "Error", "Failed to save PNG file")

            def on_save_as():
                target, _ = QFileDialog.getSaveFileName(None, "Save PNG As", file_path, "PNG Files (*.png)")
                if target:
                    if not target.lower().endswith('.png'):
                        target += '.png'
                    title_text = title_input.text().strip()
                    final_img = QImage(image)
                    need_embed = embedded_pixmap is not None
                    if title_text or need_embed:
                        p = QPainter(final_img)
                        p.setRenderHint(QPainter.Antialiasing)
                        pad = padding_spin.value()
                        # draw embedded first if present
                        try:
                            if need_embed:
                                esz = embed_size_spin.value()
                                target_w = max(1, int(final_img.width() * (esz / 100.0)))
                                target_h = int(embedded_pixmap.height() * (target_w / embedded_pixmap.width())) if embedded_pixmap.width() > 0 else target_w
                                epos_idx = embed_pos_combo.currentIndex()
                                if epos_idx == 0:  # center
                                    ex = (final_img.width() - target_w) // 2
                                    ey = (final_img.height() - target_h) // 2
                                elif epos_idx == 1:  # top
                                    ex = (final_img.width() - target_w) // 2
                                    ey = pad
                                elif epos_idx == 2:  # bottom
                                    ex = (final_img.width() - target_w) // 2
                                    ey = final_img.height() - target_h - pad
                                elif epos_idx == 3:  # left
                                    ex = pad
                                    ey = (final_img.height() - target_h) // 2
                                elif epos_idx == 4:  # right
                                    ex = final_img.width() - target_w - pad
                                    ey = (final_img.height() - target_h) // 2
                                elif epos_idx == 5:  # top_left
                                    ex = pad
                                    ey = pad
                                elif epos_idx == 6:  # top_right
                                    ex = final_img.width() - target_w - pad
                                    ey = pad
                                elif epos_idx == 7:  # bottom_left
                                    ex = pad
                                    ey = final_img.height() - target_h - pad
                                elif epos_idx == 8:  # bottom_right
                                    ex = final_img.width() - target_w - pad
                                    ey = final_img.height() - target_h - pad
                                else:
                                    ex = (final_img.width() - target_w) // 2
                                    ey = (final_img.height() - target_h) // 2
                                p.drawPixmap(QRectF(ex, ey, target_w, target_h).toRect(), embedded_pixmap)
                        except Exception:
                            pass
                        if title_text:
                            fs = font_size_spin.value()
                            font = QFont()
                            font.setPointSize(fs)
                            font.setBold(True)
                            p.setFont(font)
                            metrics = p.fontMetrics()
                            text_width = metrics.horizontalAdvance(title_text)
                            text_height = metrics.height()
                            rect_w = text_width + pad * 2
                            rect_h = text_height + pad // 2
                            pos_index = position_combo.currentIndex()
                            if pos_index == 0:  # top
                                rect_x = (final_img.width() - rect_w) // 2
                                rect_y = pad
                            elif pos_index == 1:  # bottom
                                rect_x = (final_img.width() - rect_w) // 2
                                rect_y = final_img.height() - rect_h - pad
                            elif pos_index == 2:  # left
                                rect_x = pad
                                rect_y = (final_img.height() - rect_h) // 2
                            elif pos_index == 3:  # right
                                rect_x = final_img.width() - rect_w - pad
                                rect_y = (final_img.height() - rect_h) // 2
                            elif pos_index == 4:  # top_left
                                rect_x = pad
                                rect_y = pad
                            elif pos_index == 5:  # top_right
                                rect_x = final_img.width() - rect_w - pad
                                rect_y = pad
                            elif pos_index == 6:  # bottom_left
                                rect_x = pad
                                rect_y = final_img.height() - rect_h - pad
                            elif pos_index == 7:  # bottom_right
                                rect_x = final_img.width() - rect_w - pad
                                rect_y = final_img.height() - rect_h - pad
                            else:
                                rect_x = (final_img.width() - rect_w) // 2
                                rect_y = pad
                            alpha = max(0, min(255, int(bg_opacity_spin.value() * 255)))
                            bg_color = QColor(255, 255, 255, alpha)
                            p.setBrush(QBrush(bg_color))
                            p.setPen(Qt.NoPen)
                            p.drawRect(rect_x, rect_y, rect_w, rect_h)
                            p.setPen(font_color)
                            aln = ['center', 'left', 'right'][align_combo.currentIndex()]
                            align_flag = Qt.AlignHCenter
                            if aln == 'left':
                                align_flag = Qt.AlignLeft
                            elif aln == 'right':
                                align_flag = Qt.AlignRight
                            p.drawText(QRectF(rect_x, rect_y, rect_w, rect_h), align_flag | Qt.AlignVCenter, title_text)
                        p.end()
                    if final_img.save(target, 'PNG'):
                        saved_path_holder['path'] = target
                        QMessageBox.information(None, "Export Successful", f"File saved: {target}")
                        dialog.accept()
                    else:
                        QMessageBox.critical(None, "Error", "Failed to save PNG file")

            def on_cancel():
                dialog.reject()

            save_btn.clicked.connect(on_save)
            save_as_btn.clicked.connect(on_save_as)
            cancel_btn.clicked.connect(on_cancel)

            if dialog.exec_() == QDialog.Accepted:
                final_path = saved_path_holder.get('path') or file_path
                # If Save was used and file already exists at final_path this will be the same file
                if os.path.exists(final_path):
                    if show_success_message:
                        self.show_info("Export Successful", 
                            f"Polygon exported as PNG successfully!\n"
                            f"File: {os.path.basename(final_path)}\n"
                            f"Location: {os.path.dirname(final_path)}\n"
                            f"Size: {image_size}x{image_size} pixels")
                    try:
                        self.record_informational(
                            description=f"Exported polygon {feature.id()} to PNG: {final_path}",
                            meta={'file_path': final_path, 'feature_id': feature.id(), 'image_size': image_size}
                        )
                    except Exception:
                        pass
                else:
                    # If for some reason the file doesn't exist, attempt save
                    if image.save(final_path, 'PNG'):
                        if show_success_message:
                            self.show_info("Export Successful", 
                                f"Polygon exported as PNG successfully!\n"
                                f"File: {os.path.basename(final_path)}\n"
                                f"Location: {os.path.dirname(final_path)}\n"
                                f"Size: {image_size}x{image_size} pixels")
                        try:
                            self.record_informational(
                                description=f"Exported polygon {feature.id()} to PNG: {final_path}",
                                meta={'file_path': final_path, 'feature_id': feature.id(), 'image_size': image_size}
                            )
                        except Exception:
                            pass
                    else:
                        self.show_error("Error", "Failed to save PNG file")
            else:
                # User cancelled preview; do nothing
                return
            
        except Exception as e:
            self.show_error("Error", f"Failed to export polygon as PNG: {str(e)}")
    
    def create_temp_layer_with_feature(self, original_layer, feature, border_color, border_width):
        try:
            from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields, QgsField,
                                 QgsSingleSymbolRenderer, QgsSymbol, QgsSimpleFillSymbolLayer,
                                 QgsSimpleLineSymbolLayer, QgsMemoryProviderUtils)
            from qgis.PyQt.QtGui import QColor
            
            geometry_type = original_layer.geometryType()
            temp_layer = QgsMemoryProviderUtils.createMemoryLayer(
                f"temp_polygon_{feature.id()}", 
                original_layer.fields(), 
                geometry_type, 
                original_layer.crs()
            )
            
            temp_layer.dataProvider().addFeature(feature)
            temp_layer.updateExtents()
            
            symbol = QgsSymbol.defaultSymbol(geometry_type)
            
            if symbol.symbolLayerCount() > 0:
                fill_layer = symbol.symbolLayer(0)
                if hasattr(fill_layer, 'setFillColor'):
                    fill_layer.setFillColor(QColor(0, 0, 0, 0))
                if hasattr(fill_layer, 'setStrokeColor'):
                    fill_layer.setStrokeColor(QColor(border_color))
                if hasattr(fill_layer, 'setStrokeWidth'):
                    fill_layer.setStrokeWidth(border_width)
            
            renderer = QgsSingleSymbolRenderer(symbol)
            temp_layer.setRenderer(renderer)
            
            return temp_layer
            
        except Exception as e:
            return original_layer
    
    def supports_undo(self):
        return False

    def get_undo_category(self):
        return "export"



# REQUIRED: Create global instance for automatic discovery
export_polygon_as_png_advanced_action = ExportPolygonAsPngAdvancedAction()
