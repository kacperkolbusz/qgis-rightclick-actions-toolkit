"""
Show Line Attribute Table Action for Right-click Utilities and Shortcuts Hub

Places an Excel-like two-row attribute table annotation anchored to a
representative point on a line feature (midpoint by default). Behaves
identically to the point version: live preview, appearance presets,
per-layer saved field lists, undo/redo, and dedicated annotation layers
per annotated feature.
"""

from .base_action import BaseAction

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QScrollArea, QWidget, QFrame, QApplication,
    QGroupBox, QSpinBox, QComboBox, QToolButton, QSizePolicy,
    QColorDialog, QListWidget, QListWidgetItem, QAbstractItemView
)
from qgis.PyQt.QtCore import Qt, QSettings, QRectF, QPointF
from qgis.PyQt.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath,
    QFontDatabase, QPixmap, QIcon
)
from qgis.core import (
    QgsWkbTypes, QgsPointXY, QgsRectangle,
    QgsAnnotationItem, QgsAnnotationLayer,
)
from qgis.utils import iface


# ---------------------------------------------------------------------------
# Defaults / helpers
# ---------------------------------------------------------------------------

_DEFAULT_APPEARANCE = {
    "font_family":    "",          # "" = system default
    "font_size":      9,
    "header_bg":      "#217346",
    "header_fg":      "#FFFFFF",
    "value_bg":       "#FFFFFF",
    "value_bg_alt":   "#EAF4EE",
    "grid_color":     "#B0B0B0",
    "border_color":   "#155A30",
    "anchor_color":   "#217346",
    "value_fg":       "#111111",
    "shadow":         True,
    "corner_radius":  5,
    "leader_style":   "dot",       # "dot" | "dash" | "solid" | "none"
    "show_anchor":    True,        # draw leader line + anchor dot
    "placement":      "top",        # top | bottom | left | right | top-left | top-right | bottom-left | bottom-right
    "orientation":    "horizontal", # horizontal | vertical
    # For line geometries: where along the line to anchor the annotation
    "line_position":  "midpoint",   # midpoint | start | end
}

_LEADER_STYLES = ["dot", "dash", "solid", "none"]

# (label, placement_id, grid_row, grid_col)
_PLACEMENT_CELLS = [
    ("↖", "top-left",     0, 0),
    ("↑", "top",          0, 1),
    ("↗", "top-right",    0, 2),
    ("←", "left",         1, 0),
    ("·", "center",       1, 1),
    ("→", "right",        1, 2),
    ("↙", "bottom-left",  2, 0),
    ("↓", "bottom",       2, 1),
    ("↘", "bottom-right", 2, 2),
]
_APPEARANCE_SETTINGS_KEY = "RightClickUtilities/show_line_attribute_table/appearance"

# Allowed line anchor positions
_LINE_POSITION_OPTIONS = [
    ("Midpoint", "midpoint"),
    ("Start of line", "start"),
    ("End of line", "end"),
]


# Reuse the same presets as the point version for consistent UX
_APPEARANCE_PRESETS = [
    {"name": "Default Classic", "values": dict(_DEFAULT_APPEARANCE)},
    {
        "name": "Dark Mode",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#2E3440",
            "header_fg": "#ECEFF4",
            "value_bg": "#3B4252",
            "value_bg_alt": "#434C5E",
            "grid_color": "#4C566A",
            "border_color": "#2E3440",
            "anchor_color": "#88C0D0",
            "value_fg": "#ECEFF4",
            "shadow": True,
            "corner_radius": 6,
            "leader_style": "solid",
            "show_anchor": True,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Light",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#F7F7F7",
            "header_fg": "#111111",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#FAFAFA",
            "grid_color": "#E0E0E0",
            "border_color": "#D0D0D0",
            "anchor_color": "#217346",
            "value_fg": "#111111",
            "shadow": False,
            "corner_radius": 4,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "High Contrast",
        "values": {
            "font_family": "",
            "font_size": 10,
            "header_bg": "#000000",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#FFF9C4",
            "grid_color": "#000000",
            "border_color": "#000000",
            "anchor_color": "#FF0000",
            "value_fg": "#000000",
            "shadow": False,
            "corner_radius": 0,
            "leader_style": "solid",
            "show_anchor": True,
            "placement": "right",
            "orientation": "vertical",
        },
    },
    {
        "name": "Muted Pastel",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#88BDB6",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#F0F8F8",
            "grid_color": "#DCEFEA",
            "border_color": "#B9DCCE",
            "anchor_color": "#7FB6AE",
            "value_fg": "#333333",
            "shadow": True,
            "corner_radius": 8,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Blue Accent",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#1E88E5",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#E3F2FD",
            "grid_color": "#BBDEFB",
            "border_color": "#90CAF9",
            "anchor_color": "#1976D2",
            "value_fg": "#0D47A1",
            "shadow": True,
            "corner_radius": 6,
            "leader_style": "dash",
            "show_anchor": True,
            "placement": "top-right",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Monochrome",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#222222",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#F0F0F0",
            "grid_color": "#CCCCCC",
            "border_color": "#444444",
            "anchor_color": "#666666",
            "value_fg": "#111111",
            "shadow": False,
            "corner_radius": 3,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "bottom",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Compact Small",
        "values": {
            "font_family": "",
            "font_size": 7,
            "header_bg": "#2E7D32",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#F3F7F3",
            "grid_color": "#C8E6C9",
            "border_color": "#A5D6A7",
            "anchor_color": "#2E7D32",
            "value_fg": "#111111",
            "shadow": False,
            "corner_radius": 3,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "right",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Large Print",
        "values": {
            "font_family": "",
            "font_size": 14,
            "header_bg": "#1B5E20",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#E8F5E9",
            "grid_color": "#C8E6C9",
            "border_color": "#2E7D32",
            "anchor_color": "#388E3C",
            "value_fg": "#111111",
            "shadow": True,
            "corner_radius": 8,
            "leader_style": "solid",
            "show_anchor": True,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Minimal No Anchor",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#FFFFFF",
            "header_fg": "#111111",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#FFFFFF",
            "grid_color": "#E0E0E0",
            "border_color": "#E0E0E0",
            "anchor_color": "#FFFFFF",
            "value_fg": "#111111",
            "shadow": False,
            "corner_radius": 2,
            "leader_style": "none",
            "show_anchor": False,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Sunset Warm",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#FF7043",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFF3E0",
            "value_bg_alt": "#FFF8E1",
            "grid_color": "#FFDAB9",
            "border_color": "#FF8A65",
            "anchor_color": "#FF7043",
            "value_fg": "#4E342E",
            "shadow": True,
            "corner_radius": 6,
            "leader_style": "dash",
            "show_anchor": True,
            "placement": "bottom-right",
            "orientation": "horizontal",
        },
    },

    # Additional presets
    {
        "name": "Neon Glow",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#00FFC8",
            "header_fg": "#000000",
            "value_bg": "#001219",
            "value_bg_alt": "#001F2D",
            "grid_color": "#003049",
            "border_color": "#00E5FF",
            "anchor_color": "#00FFC8",
            "value_fg": "#E6F7FF",
            "shadow": True,
            "corner_radius": 6,
            "leader_style": "solid",
            "show_anchor": True,
            "placement": "top-right",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Forest Deep",
        "values": {
            "font_family": "",
            "font_size": 10,
            "header_bg": "#154734",
            "header_fg": "#E6F4EA",
            "value_bg": "#F7FBF7",
            "value_bg_alt": "#EEF7EE",
            "grid_color": "#C9E6D8",
            "border_color": "#123B2A",
            "anchor_color": "#2E7D32",
            "value_fg": "#153D2E",
            "shadow": False,
            "corner_radius": 8,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "left",
            "orientation": "vertical",
        },
    },
    {
        "name": "Earth Tones",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#8D6E63",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFF6F1",
            "value_bg_alt": "#FEF2EA",
            "grid_color": "#D7C4B6",
            "border_color": "#6D4C41",
            "anchor_color": "#A1887F",
            "value_fg": "#3E2723",
            "shadow": False,
            "corner_radius": 6,
            "leader_style": "dash",
            "show_anchor": True,
            "placement": "bottom-left",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Candy Pop",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#FF6B6B",
            "header_fg": "#FFFFFF",
            "value_bg": "#FFF5F7",
            "value_bg_alt": "#FFF0F3",
            "grid_color": "#FFD1DC",
            "border_color": "#FF9AA2",
            "anchor_color": "#FF6B6B",
            "value_fg": "#40233A",
            "shadow": True,
            "corner_radius": 10,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Slate Minimal",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#263238",
            "header_fg": "#CFD8DC",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#FAFAFA",
            "grid_color": "#ECEFF1",
            "border_color": "#37474F",
            "anchor_color": "#90A4AE",
            "value_fg": "#263238",
            "shadow": False,
            "corner_radius": 2,
            "leader_style": "none",
            "show_anchor": False,
            "placement": "top",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Retro 70s",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#D2691E",
            "header_fg": "#FFF7E6",
            "value_bg": "#FFF7E0",
            "value_bg_alt": "#FFF0D9",
            "grid_color": "#E6C8B2",
            "border_color": "#B5651D",
            "anchor_color": "#D2691E",
            "value_fg": "#40231A",
            "shadow": True,
            "corner_radius": 8,
            "leader_style": "dash",
            "show_anchor": True,
            "placement": "bottom",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Sci-Fi Cyan",
        "values": {
            "font_family": "",
            "font_size": 10,
            "header_bg": "#003542",
            "header_fg": "#18FFFF",
            "value_bg": "#001B22",
            "value_bg_alt": "#001018",
            "grid_color": "#004D61",
            "border_color": "#00BCD4",
            "anchor_color": "#00E5FF",
            "value_fg": "#BEEFFF",
            "shadow": True,
            "corner_radius": 4,
            "leader_style": "solid",
            "show_anchor": True,
            "placement": "right",
            "orientation": "horizontal",
        },
    },
    {
        "name": "Glass Frost",
        "values": {
            "font_family": "",
            "font_size": 9,
            "header_bg": "#E3F2FD",
            "header_fg": "#0D47A1",
            "value_bg": "#FFFFFF",
            "value_bg_alt": "#F7FBFF",
            "grid_color": "#E0F2F8",
            "border_color": "#B3E5FC",
            "anchor_color": "#64B5F6",
            "value_fg": "#0D47A1",
            "shadow": True,
            "corner_radius": 12,
            "leader_style": "dot",
            "show_anchor": True,
            "placement": "top-left",
            "orientation": "horizontal",
        },
    },
]


def _load_saved_appearance():
    """Load persisted appearance from QSettings, falling back to defaults."""
    try:
        raw = QSettings().value(_APPEARANCE_SETTINGS_KEY, None)
        if isinstance(raw, dict):
            result = dict(_DEFAULT_APPEARANCE)
            result.update({k: v for k, v in raw.items() if k in result})
            result["font_size"]     = int(result["font_size"])
            result["corner_radius"] = int(result["corner_radius"])
            result["shadow"]      = str(result["shadow"]).lower()      not in ("false", "0", "no")
            result["show_anchor"] = str(result["show_anchor"]).lower() not in ("false", "0", "no")
            if result.get("placement") not in [c[1] for c in _PLACEMENT_CELLS]:
                result["placement"] = "top"
            if result.get("orientation") not in ("horizontal", "vertical"):
                result["orientation"] = "horizontal"
            if result.get("line_position") not in ("midpoint", "start", "end"):
                result["line_position"] = "midpoint"
            return result
    except Exception:
        pass
    return dict(_DEFAULT_APPEARANCE)


def _save_appearance(app):
    try:
        QSettings().setValue(_APPEARANCE_SETTINGS_KEY, app)
    except Exception:
        pass


def _make_color_button(color_hex: str, parent=None):
    btn = QToolButton(parent)
    btn.setFixedSize(32, 22)
    btn._color = QColor(color_hex)

    def _update_icon():
        pm = QPixmap(28, 18)
        pm.fill(btn._color)
        btn.setIcon(QIcon(pm))
        btn.setIconSize(pm.size())

    _update_icon()

    def _pick():
        chosen = QColorDialog.getColor(btn._color, parent, "Pick Color")
        if chosen.isValid():
            btn._color = chosen
            _update_icon()

    btn.clicked.connect(_pick)
    btn._update_icon = _update_icon
    return btn


class ReorderableListWidget(QListWidget):
    def __init__(self, on_reorder=None, parent=None):
        super().__init__(parent)
        try:
            self.setDragDropMode(QAbstractItemView.InternalMove)
            self.setDefaultDropAction(Qt.MoveAction)
        except Exception:
            pass
        self._on_reorder = on_reorder

    def dropEvent(self, event):
        super().dropEvent(event)
        if callable(self._on_reorder):
            try:
                self._on_reorder()
            except Exception:
                pass


class PreviewWidget(QWidget):
    def __init__(self, layer, feature, fields=None, appearance=None, font_size=9, null_display="NULL", parent=None):
        super().__init__(parent)
        self._layer = layer
        self._feature = feature
        self._fields = list(fields) if fields else []
        self._appearance = dict(appearance) if appearance else {}
        self._font_size = font_size
        self._null_display = null_display
        self.setMinimumSize(320, 120)

    def set_fields(self, fields):
        self._fields = list(fields) if fields else []
        self.update()

    def set_feature(self, feature):
        self._feature = feature
        self.update()

    def set_appearance(self, appearance):
        self._appearance = dict(appearance) if appearance else {}
        self.update()

    def set_font_size(self, sz):
        try:
            self._font_size = int(sz)
        except Exception:
            pass
        self.update()

    def set_null_display(self, nd):
        self._null_display = nd
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        rect = self.rect()
        if not self._feature or not self._fields:
            painter.drawText(rect, Qt.AlignCenter, "Preview\n(no fields selected)")
            return
        try:
            map_point = QgsPointXY(0, 0)
            item = AttributeTableAnnotationItem(
                map_point=map_point,
                feature=self._feature,
                layer=self._layer,
                fields=self._fields,
                font_size=self._font_size,
                null_display=self._null_display,
                appearance=self._appearance,
            )
            painter.save()
            painter.translate(rect.width() / 2.0, rect.height() / 2.0)
            item._draw_table(painter)
            painter.restore()
        except Exception as e:
            painter.drawText(rect, Qt.AlignCenter, f"Preview error: {e}")


# ---------------------------------------------------------------------------
# Field Selection + Appearance Dialog
# ---------------------------------------------------------------------------

class FieldSelectionDialog(QDialog):
    def __init__(self, layer, feature, saved_fields=None, saved_appearance=None, null_display="NULL", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Attribute Table on Map")
        self.setModal(True)
        self.setMinimumWidth(760)

        self._layer   = layer
        self._feature = feature
        self._checkboxes   = {}
        self._saved_fields = saved_fields or []
        self._app = dict(saved_appearance) if saved_appearance else _load_saved_appearance()
        self._null_display = null_display

        self._setup_ui()
        self._restore_selection()
        try:
            self._update_preview()
        except Exception:
            pass

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.NoFrame)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        try:
            screen = QApplication.primaryScreen()
            screen_h = screen.availableGeometry().height() if screen else 800
        except Exception:
            screen_h = 800
        main_scroll.setMaximumHeight(min(820, max(480, screen_h - 180)))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(0, 0, 0, 0)

        info = QLabel(
            f"Layer: <b>{self._layer.name()}</b>&nbsp;&nbsp;"
            f"Feature ID: <b>{self._feature.id()}</b>"
        )
        info.setWordWrap(True)
        content_layout.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        content_layout.addWidget(sep)

        fields_group = QGroupBox("Fields to display")
        fg_layout = QVBoxLayout(fields_group)
        fg_layout.setContentsMargins(6, 6, 6, 6)
        fg_layout.setSpacing(4)

        self._fields_list = ReorderableListWidget(on_reorder=self._update_preview, parent=self)
        self._fields_list.setSelectionMode(QListWidget.SingleSelection)
        self._fields_list.setMinimumHeight(150)
        self._fields_list.setMaximumHeight(230)
        for field in self._layer.fields():
            item = QListWidgetItem(field.name())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked)
            raw = self._feature[field.name()]
            if raw is None or (hasattr(raw, "isNull") and raw.isNull()):
                tip_val = "NULL"
            else:
                tv = str(raw)
                tip_val = tv[:60] + "..." if len(tv) > 60 else tv
            item.setToolTip(f"Type: {field.typeName()}  |  Value: {tip_val}")
            self._fields_list.addItem(item)

        try:
            self._fields_list.itemChanged.connect(self._update_preview)
        except Exception:
            pass

        fg_layout.addWidget(self._fields_list)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.setMaximumWidth(100)
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("Select None")
        btn_none.setMaximumWidth(100)
        btn_none.clicked.connect(self._select_none)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        fg_layout.addLayout(btn_row)

        self._remember_cb = QCheckBox("Remember field selection for this layer")
        self._remember_cb.setChecked(True)
        fg_layout.addWidget(self._remember_cb)

        content_layout.addWidget(fields_group)

        preview_group = QGroupBox("Live Preview")
        pg_layout = QVBoxLayout(preview_group)
        initial_font = self._app.get("font_size", 9)
        initial_fields = self._saved_fields if self._saved_fields else [f.name() for f in self._layer.fields()]
        self._preview = PreviewWidget(
            layer=self._layer,
            feature=self._feature,
            fields=initial_fields,
            appearance=self._app,
            font_size=initial_font,
            null_display=self._null_display,
            parent=self,
        )
        pg_layout.addWidget(self._preview)
        content_layout.addWidget(preview_group)

        app_toggle = QToolButton()
        app_toggle.setText("▼  Appearance")
        app_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        app_toggle.setCheckable(True)
        app_toggle.setChecked(True)
        app_toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        app_toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(app_toggle)
        self._app_container = QWidget()
        self._app_container.setVisible(True)
        app_layout = QVBoxLayout(self._app_container)
        app_layout.setContentsMargins(4, 0, 4, 0)
        app_layout.setSpacing(6)

        def _toggle_appearance(checked):
            self._app_container.setVisible(checked)
            app_toggle.setText(("▼" if checked else "▶") + "  Appearance")
            self.adjustSize()

        app_toggle.toggled.connect(_toggle_appearance)

        def _row(label_text, widget):
            row_w = QWidget()
            hl = QHBoxLayout(row_w)
            hl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(140)
            hl.addWidget(lbl)
            hl.addWidget(widget)
            hl.addStretch()
            app_layout.addWidget(row_w)

        self._preset_combo = QComboBox()
        self._preset_combo.addItem("Custom", None)
        for p in _APPEARANCE_PRESETS:
            try:
                self._preset_combo.addItem(p.get("name", "Preset"), p.get("values"))
            except Exception:
                pass
        self._preset_combo.setMaximumWidth(220)
        _row("Preset:", self._preset_combo)

        def _preset_changed(idx):
            if getattr(self, "_applying_preset", False):
                return
            vals = self._preset_combo.itemData(idx)
            if not vals:
                return
            self._apply_preset(vals)

        self._preset_combo.currentIndexChanged.connect(_preset_changed)

        self._font_combo = QComboBox()
        families = sorted(set(QFontDatabase().families()))
        self._font_combo.addItem("(system default)", "")
        for fam in families:
            self._font_combo.addItem(fam, fam)
        saved_fam = self._app.get("font_family", "")
        idx = self._font_combo.findData(saved_fam)
        self._font_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._font_combo.setMaximumWidth(200)
        _row("Font family:", self._font_combo)

        self._font_spin = QSpinBox()
        self._font_spin.setRange(6, 28)
        self._font_spin.setValue(self._app.get("font_size", 9))
        self._font_spin.setSuffix(" pt")
        self._font_spin.setMaximumWidth(80)
        _row("Font size:", self._font_spin)

        _sep = QFrame(); _sep.setFrameShape(QFrame.HLine); _sep.setFrameShadow(QFrame.Sunken)
        app_layout.addWidget(_sep)

        self._btn_header_bg  = _make_color_button(self._app["header_bg"],  self)
        self._btn_header_fg  = _make_color_button(self._app["header_fg"],  self)
        self._btn_value_bg   = _make_color_button(self._app["value_bg"],   self)
        self._btn_value_bg_alt = _make_color_button(self._app["value_bg_alt"], self)
        self._btn_value_fg   = _make_color_button(self._app["value_fg"],   self)
        self._btn_grid       = _make_color_button(self._app["grid_color"], self)
        self._btn_border     = _make_color_button(self._app["border_color"], self)
        self._btn_anchor     = _make_color_button(self._app["anchor_color"], self)

        _row("Header background:", self._btn_header_bg)
        _row("Header text:", self._btn_header_fg)
        _row("Value background:", self._btn_value_bg)
        _row("Value background (alt):", self._btn_value_bg_alt)
        _row("Value text:", self._btn_value_fg)
        _row("Grid / divider:", self._btn_grid)
        _row("Border:", self._btn_border)
        _row("Leader / anchor:", self._btn_anchor)

        _sep2 = QFrame(); _sep2.setFrameShape(QFrame.HLine); _sep2.setFrameShadow(QFrame.Sunken)
        app_layout.addWidget(_sep2)

        self._corner_spin = QSpinBox()
        self._corner_spin.setRange(0, 20)
        self._corner_spin.setValue(self._app.get("corner_radius", 5))
        self._corner_spin.setSuffix(" px")
        self._corner_spin.setMaximumWidth(80)
        _row("Corner radius:", self._corner_spin)

        from qgis.PyQt.QtWidgets import QGridLayout, QButtonGroup
        compass_outer = QWidget()
        compass_hl = QHBoxLayout(compass_outer)
        compass_hl.setContentsMargins(0, 0, 0, 0)
        lbl_place = QLabel("Table placement:")
        lbl_place.setFixedWidth(140)
        compass_hl.addWidget(lbl_place)
        compass_w = QWidget()
        compass_grid = QGridLayout(compass_w)
        compass_grid.setSpacing(2)
        compass_grid.setContentsMargins(0, 0, 0, 0)
        self._placement_buttons = {}
        self._placement_group = QButtonGroup(self)
        self._placement_group.setExclusive(True)
        for arrow, pid, row, col in _PLACEMENT_CELLS:
            btn = QToolButton()
            btn.setText(arrow)
            btn.setCheckable(True)
            btn.setFixedSize(26, 26)
            btn.setToolTip(pid.replace("-", " ").title())
            self._placement_group.addButton(btn)
            self._placement_buttons[pid] = btn
            compass_grid.addWidget(btn, row, col)
        saved_placement = self._app.get("placement", "top")
        if saved_placement in self._placement_buttons:
            self._placement_buttons[saved_placement].setChecked(True)
        else:
            self._placement_buttons["top"].setChecked(True)
        compass_hl.addWidget(compass_w)
        compass_hl.addStretch()
        app_layout.addWidget(compass_outer)

        # Line anchor position (midpoint / start / end)
        self._line_pos_combo = QComboBox()
        for label, val in _LINE_POSITION_OPTIONS:
            self._line_pos_combo.addItem(label, val)
        saved_line_pos = self._app.get("line_position", "midpoint")
        li_lp = self._line_pos_combo.findData(saved_line_pos)
        self._line_pos_combo.setCurrentIndex(li_lp if li_lp >= 0 else 0)
        _row("Line anchor:", self._line_pos_combo)

        self._shadow_cb = QCheckBox("Draw drop shadow")
        self._shadow_cb.setChecked(bool(self._app.get("shadow", True)))
        app_layout.addWidget(self._shadow_cb)

        self._anchor_cb = QCheckBox("Show leader line and anchor dot")
        self._anchor_cb.setChecked(bool(self._app.get("show_anchor", True)))
        app_layout.addWidget(self._anchor_cb)

        def _sync_leader_combo(checked):
            self._leader_combo.setEnabled(checked)
        self._anchor_cb.toggled.connect(_sync_leader_combo)

        self._leader_combo = QComboBox()
        for style in _LEADER_STYLES:
            self._leader_combo.addItem(style.capitalize(), style)
        saved_leader = self._app.get("leader_style", "dot")
        li = self._leader_combo.findData(saved_leader)
        self._leader_combo.setCurrentIndex(li if li >= 0 else 0)
        self._leader_combo.setMaximumWidth(120)
        _row("Leader line style:", self._leader_combo)

        self._orientation_combo = QComboBox()
        self._orientation_combo.addItem("Horizontal", "horizontal")
        self._orientation_combo.addItem("Vertical", "vertical")
        saved_orient = self._app.get("orientation", "horizontal")
        oi = self._orientation_combo.findData(saved_orient)
        self._orientation_combo.setCurrentIndex(oi if oi >= 0 else 0)
        self._orientation_combo.setMaximumWidth(160)
        _row("Orientation:", self._orientation_combo)

        def _reset_defaults():
            d = dict(_DEFAULT_APPEARANCE)
            self._font_spin.setValue(d["font_size"])
            idx0 = self._font_combo.findData(d["font_family"])
            self._font_combo.setCurrentIndex(idx0 if idx0 >= 0 else 0)
            self._btn_header_bg._color   = QColor(d["header_bg"]);   self._btn_header_bg._update_icon()
            self._btn_header_fg._color   = QColor(d["header_fg"]);   self._btn_header_fg._update_icon()
            self._btn_value_bg._color    = QColor(d["value_bg"]);    self._btn_value_bg._update_icon()
            self._btn_value_bg_alt._color= QColor(d["value_bg_alt"]);self._btn_value_bg_alt._update_icon()
            self._btn_value_fg._color    = QColor(d["value_fg"]);    self._btn_value_fg._update_icon()
            self._btn_grid._color        = QColor(d["grid_color"]);  self._btn_grid._update_icon()
            self._btn_border._color      = QColor(d["border_color"]);self._btn_border._update_icon()
            self._btn_anchor._color      = QColor(d["anchor_color"]);self._btn_anchor._update_icon()
            self._corner_spin.setValue(d["corner_radius"])
            self._shadow_cb.setChecked(d["shadow"])
            self._anchor_cb.setChecked(d["show_anchor"])
            self._leader_combo.setEnabled(d["show_anchor"])
            li2 = self._leader_combo.findData(d["leader_style"])
            self._leader_combo.setCurrentIndex(li2 if li2 >= 0 else 0)
            dp = d.get("placement", "top")
            if dp in self._placement_buttons:
                self._placement_buttons[dp].setChecked(True)
            # reset line anchor
            lp = d.get("line_position", "midpoint")
            li_lp2 = self._line_pos_combo.findData(lp)
            if li_lp2 >= 0:
                self._line_pos_combo.setCurrentIndex(li_lp2)
            li3 = self._orientation_combo.findData(d.get("orientation", "horizontal"))
            self._orientation_combo.setCurrentIndex(li3 if li3 >= 0 else 0)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setMaximumWidth(150)
        reset_btn.clicked.connect(_reset_defaults)
        app_layout.addWidget(reset_btn)

        self._remember_app_cb = QCheckBox("Remember appearance settings globally")
        self._remember_app_cb.setChecked(True)
        app_layout.addWidget(self._remember_app_cb)

        content_layout.addWidget(self._app_container)

        for cb in self._checkboxes.values():
            try:
                cb.toggled.connect(self._update_preview)
            except Exception:
                pass

        try:
            self._font_combo.currentIndexChanged.connect(self._update_preview)
        except Exception:
            pass
        try:
            self._font_spin.valueChanged.connect(self._update_preview)
        except Exception:
            pass
        try:
            self._line_pos_combo.currentIndexChanged.connect(self._update_preview)
        except Exception:
            pass
        try:
            self._orientation_combo.currentIndexChanged.connect(self._update_preview)
        except Exception:
            pass
        for btn in (self._btn_header_bg, self._btn_header_fg, self._btn_value_bg, self._btn_value_bg_alt,
                    self._btn_value_fg, self._btn_grid, self._btn_border, self._btn_anchor):
            try:
                btn.clicked.connect(self._update_preview)
            except Exception:
                pass
        try:
            self._corner_spin.valueChanged.connect(self._update_preview)
        except Exception:
            pass
        for btn in self._placement_buttons.values():
            try:
                btn.toggled.connect(self._update_preview)
            except Exception:
                pass
        try:
            self._shadow_cb.toggled.connect(self._update_preview)
            self._anchor_cb.toggled.connect(self._update_preview)
            self._leader_combo.currentIndexChanged.connect(self._update_preview)
        except Exception:
            pass
        try:
            reset_btn.clicked.connect(self._update_preview)
        except Exception:
            pass

        main_scroll.setWidget(content)
        root.addWidget(main_scroll)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep3)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_ok = QPushButton("Place on Map")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_ok)
        bottom.addWidget(btn_cancel)
        root.addLayout(bottom)

    def _apply_preset(self, vals: dict):
        if not isinstance(vals, dict):
            return
        self._applying_preset = True
        try:
            fam = vals.get("font_family", "")
            if fam:
                idx = self._font_combo.findData(fam)
                if idx >= 0:
                    self._font_combo.setCurrentIndex(idx)
                else:
                    self._font_combo.setCurrentIndex(0)
            else:
                self._font_combo.setCurrentIndex(0)

            try:
                self._font_spin.setValue(int(vals.get("font_size", self._font_spin.value())))
            except Exception:
                pass

            try:
                self._btn_header_bg._color = QColor(vals.get("header_bg", self._btn_header_bg._color.name()))
                self._btn_header_bg._update_icon()
                self._btn_header_fg._color = QColor(vals.get("header_fg", self._btn_header_fg._color.name()))
                self._btn_header_fg._update_icon()
                self._btn_value_bg._color = QColor(vals.get("value_bg", self._btn_value_bg._color.name()))
                self._btn_value_bg._update_icon()
                self._btn_value_bg_alt._color = QColor(vals.get("value_bg_alt", self._btn_value_bg_alt._color.name()))
                self._btn_value_bg_alt._update_icon()
                self._btn_value_fg._color = QColor(vals.get("value_fg", self._btn_value_fg._color.name()))
                self._btn_value_fg._update_icon()
                self._btn_grid._color = QColor(vals.get("grid_color", self._btn_grid._color.name()))
                self._btn_grid._update_icon()
                self._btn_border._color = QColor(vals.get("border_color", self._btn_border._color.name()))
                self._btn_border._update_icon()
                self._btn_anchor._color = QColor(vals.get("anchor_color", self._btn_anchor._color.name()))
                self._btn_anchor._update_icon()
            except Exception:
                pass

            try:
                self._corner_spin.setValue(int(vals.get("corner_radius", self._corner_spin.value())))
            except Exception:
                pass

            try:
                self._shadow_cb.setChecked(bool(vals.get("shadow", self._shadow_cb.isChecked())))
            except Exception:
                pass

            try:
                self._anchor_cb.setChecked(bool(vals.get("show_anchor", self._anchor_cb.isChecked())))
            except Exception:
                pass

            try:
                li = self._leader_combo.findData(vals.get("leader_style", self._leader_combo.currentData()))
                if li >= 0:
                    self._leader_combo.setCurrentIndex(li)
            except Exception:
                pass

            try:
                p = vals.get("placement", self._placement_buttons and next(iter(self._placement_buttons), "top"))
                if p in self._placement_buttons:
                    self._placement_buttons[p].setChecked(True)
            except Exception:
                pass

            try:
                lpv = vals.get("line_position", None)
                if lpv:
                    li_lp3 = self._line_pos_combo.findData(lpv)
                    if li_lp3 >= 0:
                        self._line_pos_combo.setCurrentIndex(li_lp3)
            except Exception:
                pass

            try:
                oi = self._orientation_combo.findData(vals.get("orientation", self._orientation_combo.currentData()))
                if oi >= 0:
                    self._orientation_combo.setCurrentIndex(oi)
            except Exception:
                pass

        finally:
            self._applying_preset = False
        try:
            self._update_preview()
        except Exception:
            pass

    def _restore_selection(self):
        if getattr(self, "_fields_list", None):
            if self._saved_fields:
                chosen = set(self._saved_fields)
                for i in range(self._fields_list.count()):
                    it = self._fields_list.item(i)
                    it.setCheckState(Qt.Checked if it.text() in chosen else Qt.Unchecked)
            else:
                for i in range(self._fields_list.count()):
                    self._fields_list.item(i).setCheckState(Qt.Checked)
        else:
            if self._saved_fields:
                for name, cb in self._checkboxes.items():
                    cb.setChecked(name in self._saved_fields)
            else:
                for cb in self._checkboxes.values():
                    cb.setChecked(True)

    def _select_all(self):
        if getattr(self, "_fields_list", None):
            for i in range(self._fields_list.count()):
                self._fields_list.item(i).setCheckState(Qt.Checked)
        else:
            for cb in self._checkboxes.values():
                cb.setChecked(True)

    def _select_none(self):
        if getattr(self, "_fields_list", None):
            for i in range(self._fields_list.count()):
                self._fields_list.item(i).setCheckState(Qt.Unchecked)
        else:
            for cb in self._checkboxes.values():
                cb.setChecked(False)

    def selected_fields(self):
        if getattr(self, "_fields_list", None):
            res = []
            for i in range(self._fields_list.count()):
                it = self._fields_list.item(i)
                if it.checkState() == Qt.Checked:
                    res.append(it.text())
            return res
        return [n for n, cb in self._checkboxes.items() if cb.isChecked()]

    def should_remember(self):
        return self._remember_cb.isChecked()

    def should_remember_appearance(self):
        return self._remember_app_cb.isChecked()

    def get_appearance(self) -> dict:
        fam = self._font_combo.currentData()
        return {
            "font_family":    fam if fam else "",
            "font_size":      self._font_spin.value(),
            "header_bg":      self._btn_header_bg._color.name(),
            "header_fg":      self._btn_header_fg._color.name(),
            "value_bg":       self._btn_value_bg._color.name(),
            "value_bg_alt":   self._btn_value_bg_alt._color.name(),
            "value_fg":       self._btn_value_fg._color.name(),
            "grid_color":     self._btn_grid._color.name(),
            "border_color":   self._btn_border._color.name(),
            "anchor_color":   self._btn_anchor._color.name(),
            "shadow":         self._shadow_cb.isChecked(),
            "corner_radius":  self._corner_spin.value(),
            "show_anchor":    self._anchor_cb.isChecked(),
            "leader_style":   self._leader_combo.currentData(),
            "placement":      next(
                (pid for pid, btn in self._placement_buttons.items() if btn.isChecked()),
                "top"
            ),
            "line_position":  self._line_pos_combo.currentData(),
            "orientation":     self._orientation_combo.currentData(),
        }

    def _update_preview(self):
        if not getattr(self, "_preview", None):
            return
        try:
            fields = self.selected_fields()
            feature = getattr(self, "_feature", None)
            self._preview.set_fields(fields)
            self._preview.set_feature(feature)
            app = self.get_appearance()
            self._preview.set_appearance(app)
            self._preview.set_font_size(app.get("font_size", self._app.get("font_size", 9)))
            self._preview.set_null_display(getattr(self, "_null_display", "NULL"))
            self._preview.update()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Annotation Item — renders in QgsAnnotationLayer (canvas + print layout)
# ---------------------------------------------------------------------------

class AttributeTableAnnotationItem(QgsAnnotationItem):
    ITEM_TYPE = "show_line_attribute_table_annotation_v1"

    def __init__(self, map_point, feature, layer, fields,
                 font_size, null_display, appearance=None):
        super().__init__()
        self._map_point_x = map_point.x()
        self._map_point_y = map_point.y()
        self._feature     = feature
        self._layer       = layer
        self._fields      = fields
        self._null_display = null_display

        try:
            self._fid = int(feature.id()) if feature is not None else None
        except Exception:
            self._fid = None

        self._app = dict(_DEFAULT_APPEARANCE)
        if appearance:
            self._app.update(appearance)
        if not appearance or "font_size" not in appearance:
            self._app["font_size"] = font_size

    def type(self):
        return self.ITEM_TYPE

    def clone(self):
        return AttributeTableAnnotationItem(
            QgsPointXY(self._map_point_x, self._map_point_y),
            self._feature, self._layer, self._fields,
            self._app.get("font_size", 9), self._null_display,
            dict(self._app)
        )

    def boundingBox(self, *args):
        buf = 1e-4
        return QgsRectangle(
            self._map_point_x - buf, self._map_point_y - buf,
            self._map_point_x + buf, self._map_point_y + buf,
        )

    def writeXml(self, element, document, context):
        import json
        element.setAttribute("map_point_x",  str(self._map_point_x))
        element.setAttribute("map_point_y",  str(self._map_point_y))
        element.setAttribute("fields",       json.dumps(self._fields))
        element.setAttribute("null_display", self._null_display)
        element.setAttribute("appearance",   json.dumps(self._app))
        return True

    def readXml(self, element, context):
        return True

    @staticmethod
    def _fmt_value(value, null_display):
        if value is None or (hasattr(value, "isNull") and value.isNull()):
            return null_display
        return str(value)

    @staticmethod
    def _make_font_from_app(app, bold=False):
        f = QFont()
        fam = app.get("font_family", "")
        if fam:
            f.setFamily(fam)
        size = int(app.get("font_size", 9))
        f.setPointSize(size)
        if bold:
            f.setBold(True)
        return f

    @staticmethod
    def _table_offset(placement, w, h, leader_len):
        ll = leader_len
        p  = placement
        if   p == "top":          return -w / 2.0,   -(h + ll)
        elif p == "bottom":       return -w / 2.0,    ll
        elif p == "left":         return -(w + ll),  -h / 2.0
        elif p == "right":        return  ll,         -h / 2.0
        elif p == "top-left":     return -(w + ll),  -(h + ll)
        elif p == "top-right":    return  ll,         -(h + ll)
        elif p == "bottom-left":  return -(w + ll),   ll
        elif p == "bottom-right": return  ll,          ll
        elif p == "center":       return -w / 2.0,   -h / 2.0
        else:                     return -w / 2.0,   -(h + ll)

    @staticmethod
    def _leader_start(placement, tx, ty, w, h):
        p = placement
        if   p == "top":          return QPointF(tx + w / 2,  ty + h)
        elif p == "bottom":       return QPointF(tx + w / 2,  ty)
        elif p == "left":         return QPointF(tx + w,      ty + h / 2)
        elif p == "right":        return QPointF(tx,          ty + h / 2)
        elif p == "top-left":     return QPointF(tx + w,      ty + h)
        elif p == "top-right":    return QPointF(tx,          ty + h)
        elif p == "bottom-left":  return QPointF(tx + w,      ty)
        elif p == "bottom-right": return QPointF(tx,          ty)
        elif p == "center":       return QPointF(tx + w / 2,  ty + h / 2)
        else:                     return QPointF(tx + w / 2,  ty + h)

    def render(self, context, feedback=None):
        try:
            pt = QgsPointXY(self._map_point_x, self._map_point_y)
            ct = context.coordinateTransform()
            try:
                if ct.isValid():
                    pt = ct.transform(pt)
            except Exception:
                pass

            screen = context.mapToPixel().transform(pt)

            painter = context.painter()
            painter.save()
            painter.translate(screen.x(), screen.y())
            self._draw_table(painter)
            painter.restore()
        except Exception as e:
            try:
                from qgis.core import QgsMessageLog, Qgis
                QgsMessageLog.logMessage(
                    f"[AttributeTableAnnotation] render() error: {e}",
                    "RightClickUtils", Qgis.Warning
                )
            except Exception:
                pass

    def _draw_table(self, painter):
        app          = self._app
        header_bg    = QColor(app.get("header_bg",    "#217346"))
        header_fg    = QColor(app.get("header_fg",    "#FFFFFF"))
        value_bg     = QColor(app.get("value_bg",     "#FFFFFF"))
        value_bg_alt = QColor(app.get("value_bg_alt", "#EAF4EE"))
        value_fg     = QColor(app.get("value_fg",     "#111111"))
        grid_color   = QColor(app.get("grid_color",   "#B0B0B0"))
        border_color = QColor(app.get("border_color", "#155A30"))
        anchor_color = QColor(app.get("anchor_color", "#217346"))
        corner_r     = float(app.get("corner_radius", 5))
        draw_shadow  = bool(app.get("shadow", True))
        show_anchor  = bool(app.get("show_anchor", True))
        leader_style = app.get("leader_style", "dot")
        placement    = app.get("placement", "top")

        live_feature = None
        if getattr(self, "_fid", None) is not None and getattr(self, "_layer", None) is not None:
            try:
                from qgis.core import QgsFeatureRequest
                for f in self._layer.getFeatures(QgsFeatureRequest().setFilterFid(self._fid)):
                    live_feature = f
                    break
            except Exception:
                live_feature = None

        def _raw_attr(field_name):
            if live_feature is not None:
                try:
                    return live_feature[field_name]
                except Exception:
                    pass
            try:
                return self._feature[field_name]
            except Exception:
                return None

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        header_font = self._make_font_from_app(app, bold=True)
        value_font  = self._make_font_from_app(app, bold=False)

        painter.setFont(header_font)
        fm_h = painter.fontMetrics()
        painter.setFont(value_font)
        fm_v = painter.fontMetrics()

        pad_x = max(4, fm_h.averageCharWidth())
        pad_y = max(2, fm_h.descent() + 1)
        row_h = max(fm_h.height(), fm_v.height()) + 2 * pad_y
        min_col_w = fm_v.averageCharWidth() * 7
        max_col_w = fm_v.averageCharWidth() * 28
        orientation = app.get("orientation", "horizontal")

        if orientation == "horizontal":
            col_widths = []
            for field_name in self._fields:
                raw      = _raw_attr(field_name)
                val_text = self._fmt_value(raw, self._null_display)
                w_h = fm_h.horizontalAdvance(field_name) + 2 * pad_x
                w_v = fm_v.horizontalAdvance(val_text)   + 2 * pad_x
                cw  = max(w_h, w_v, min_col_w)
                cw  = min(cw, max_col_w)
                col_widths.append(cw)

            table_w = sum(col_widths)
            table_h = 2 * row_h
        else:
            label_widths = []
            value_widths = []
            for field_name in self._fields:
                raw      = _raw_attr(field_name)
                val_text = self._fmt_value(raw, self._null_display)
                w_label = fm_h.horizontalAdvance(field_name) + 2 * pad_x
                w_val   = fm_v.horizontalAdvance(val_text)   + 2 * pad_x
                label_widths.append(w_label)
                value_widths.append(w_val)

            left_col_w = max(max(label_widths) if label_widths else min_col_w, min_col_w)
            right_col_w = max(max(value_widths) if value_widths else min_col_w, min_col_w)
            left_col_w = min(left_col_w, max_col_w)
            right_col_w = min(right_col_w, max_col_w)

            table_w = left_col_w + right_col_w
            table_h = row_h * max(1, len(self._fields))

        leader_len   = row_h * 0.9
        anchor_dot_r = row_h * 0.22
        shadow_off   = max(1.0, row_h * 0.15)

        tx, ty = self._table_offset(placement, table_w, table_h, leader_len)

        if draw_shadow:
            so = shadow_off
            sp = QPainterPath()
            sp.addRoundedRect(QRectF(tx + so, ty + so, table_w, table_h), corner_r, corner_r)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
            painter.drawPath(sp)

        table_path = QPainterPath()
        table_path.addRoundedRect(QRectF(tx, ty, table_w, table_h), corner_r, corner_r)
        painter.setClipPath(table_path)

        painter.setPen(Qt.NoPen)
        if orientation == "horizontal":
            painter.setBrush(QBrush(header_bg))
            painter.drawRect(QRectF(tx, ty, table_w, row_h))

            x = tx
            for ci, cw in enumerate(col_widths):
                bg = value_bg_alt if ci % 2 == 0 else value_bg
                painter.setBrush(QBrush(bg))
                painter.drawRect(QRectF(x, ty + row_h, cw, row_h))
                x += cw

            painter.setPen(QPen(grid_color, 0.8))
            x = tx
            for cw in col_widths[:-1]:
                x += cw
                painter.drawLine(QPointF(x, ty), QPointF(x, ty + table_h))
            painter.drawLine(QPointF(tx, ty + row_h), QPointF(tx + table_w, ty + row_h))

            painter.setClipping(False)

            painter.setFont(header_font)
            painter.setPen(QPen(header_fg))
            x = tx
            for ci, field_name in enumerate(self._fields):
                cw        = col_widths[ci]
                cell_rect = QRectF(x, ty, cw, row_h)
                elided    = fm_h.elidedText(field_name, Qt.ElideRight, int(cw) - 4)
                painter.drawText(cell_rect, Qt.AlignCenter, elided)
                x += cw

            painter.setFont(value_font)
            painter.setPen(QPen(value_fg))
            x = tx
            for ci, field_name in enumerate(self._fields):
                cw        = col_widths[ci]
                raw       = _raw_attr(field_name)
                val_text  = self._fmt_value(raw, self._null_display)
                cell_rect = QRectF(x, ty + row_h, cw, row_h)
                elided    = fm_v.elidedText(val_text, Qt.ElideRight, int(cw) - 4)
                painter.drawText(cell_rect, Qt.AlignCenter, elided)
                x += cw
        else:
            left_w = left_col_w
            right_w = right_col_w

            painter.setBrush(QBrush(header_bg))
            painter.drawRect(QRectF(tx, ty, left_w, table_h))

            y = ty
            for ri in range(len(self._fields)):
                bg = value_bg_alt if ri % 2 == 0 else value_bg
                painter.setBrush(QBrush(bg))
                painter.drawRect(QRectF(tx + left_w, y, right_w, row_h))
                y += row_h

            painter.setPen(QPen(grid_color, 0.8))
            painter.drawLine(QPointF(tx + left_w, ty), QPointF(tx + left_w, ty + table_h))
            y = ty
            for ri in range(1, len(self._fields)):
                y += row_h
                painter.drawLine(QPointF(tx, y), QPointF(tx + table_w, y))

            painter.setClipping(False)

            painter.setFont(header_font)
            painter.setPen(QPen(header_fg))
            y = ty
            for ri, field_name in enumerate(self._fields):
                cell_rect = QRectF(tx, y, left_w, row_h)
                elided = fm_h.elidedText(field_name, Qt.ElideRight, int(left_w) - 4)
                painter.drawText(cell_rect, Qt.AlignCenter, elided)
                y += row_h

            painter.setFont(value_font)
            painter.setPen(QPen(value_fg))
            y = ty
            for ri, field_name in enumerate(self._fields):
                raw = _raw_attr(field_name)
                val_text = self._fmt_value(raw, self._null_display)
                cell_rect = QRectF(tx + left_w, y, right_w, row_h)
                elided = fm_v.elidedText(val_text, Qt.ElideRight, int(right_w) - 4)
                painter.drawText(cell_rect, Qt.AlignCenter, elided)
                y += row_h

        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(table_path)

        if show_anchor:
            if leader_style != "none":
                _qt_style = {
                    "dot":   Qt.DotLine,
                    "dash":  Qt.DashLine,
                    "solid": Qt.SolidLine,
                }.get(leader_style, Qt.DotLine)
                painter.setPen(QPen(anchor_color, max(1.0, row_h * 0.07), _qt_style))
                painter.drawLine(
                    self._leader_start(placement, tx, ty, table_w, table_h),
                    QPointF(0.0, 0.0)
                )
            painter.setPen(QPen(border_color, max(1.0, row_h * 0.1)))
            painter.setBrush(QBrush(anchor_color))
            painter.drawEllipse(QPointF(0.0, 0.0), anchor_dot_r, anchor_dot_r)


# ---------------------------------------------------------------------------
# Action Class
# ---------------------------------------------------------------------------

class ShowLineAttributeTableAction(BaseAction):
    """
    Places an Excel-like attribute annotation directly on the map canvas,
    anchored to a representative point on the clicked line feature.
    """

    _SELECTION_SETTINGS_PREFIX = (
        "RightClickUtilities/show_line_attribute_table/saved_fields"
    )

    def __init__(self):
        super().__init__()

        self.action_id  = "show_line_attribute_table"
        self.name       = "Show Attribute Table on Map (Line)"
        self.category   = "Information"
        self.description = (
            "Place an Excel-like attribute table annotation directly on the map, "
            "anchored to the clicked line (representative point). Field names in the header row; values "
            "in the row below. Trigger again on the same feature to remove it."
        )
        self.enabled = True

        self.set_action_scope("feature")
        self.set_supported_scopes(["feature"])
        self.set_supported_click_types(["line", "multiline"])
        self.set_supported_geometry_types(["line", "multiline"])

        self._active_items = {}
        self._annotation_items_by_id = {}
        self._annotation_layer_ids = {}
        self._last_payload = None
        try:
            self.register_undo_handler()
        except Exception:
            pass

    def get_settings_schema(self):
        return {
            "table_font_size": {
                "type": "int",
                "default": 9,
                "label": "Table Font Size",
                "description": "Font size (pt) for text inside the map annotation",
                "min": 6,
                "max": 20,
                "step": 1,
            },
            "null_display": {
                "type": "choice",
                "default": "NULL",
                "label": "Null Value Display",
                "description": "Text to show for NULL / empty attribute values",
                "options": ["NULL", "N/A", "(empty)", ""],
            },
            "remember_field_selection": {
                "type": "bool",
                "default": True,
                "label": "Remember Field Selection",
                "description": "Save and restore the field selection per layer",
            },
        }

    def supports_undo(self):
        return True

    def get_undo_category(self):
        return "trivial"

    def get_undo_payload(self, context, execute_result=None):
        return self._last_payload or {}

    def apply_undo(self, payload):
        try:
            item_id    = payload.get("annotation_item_id")
            layer_id   = payload.get("layer_id")
            feature_id = payload.get("feature_id")

            if not item_id:
                return True, "Annotation was already removed"

            self._annotation_items_by_id.pop(item_id, None)

            if layer_id and feature_id is not None:
                key = (layer_id, int(feature_id))
                self._active_items.pop(key, None)
                self._remove_annotation_layer(key)
            else:
                ann_layer_id = payload.get("ann_layer_id")
                if ann_layer_id:
                    try:
                        from qgis.core import QgsProject
                        QgsProject.instance().removeMapLayer(ann_layer_id)
                    except Exception:
                        pass

            return True, "Attribute table annotation removed"
        except Exception as e:
            return False, f"Undo failed: {e}"

    def apply_redo(self, payload):
        try:
            from qgis.core import QgsProject, QgsFeatureRequest

            layer_id   = payload.get("layer_id")
            feature_id = payload.get("feature_id")
            fields     = payload.get("fields_shown", [])
            pt_x       = payload.get("map_point_x")
            pt_y       = payload.get("map_point_y")
            font_size  = int(payload.get("font_size", 9))
            null_disp  = str(payload.get("null_display", "NULL"))
            appearance = payload.get("appearance") or {}

            if not layer_id or feature_id is None or not fields:
                return False, "Redo payload is incomplete"

            layer = QgsProject.instance().mapLayer(layer_id)
            if not layer:
                return False, "Layer no longer exists – cannot redo annotation"

            fid = int(feature_id)
            feature = None
            for f in layer.getFeatures(QgsFeatureRequest().setFilterFid(fid)):
                feature = f
                break
            if feature is None:
                return False, "Feature no longer exists – cannot redo annotation"

            map_point = QgsPointXY(float(pt_x), float(pt_y))
            key       = (layer_id, fid)

            old_id = self._active_items.pop(key, None)
            self._annotation_items_by_id.pop(old_id, None)
            self._remove_annotation_layer(key)

            item = AttributeTableAnnotationItem(
                map_point=map_point,
                feature=feature,
                layer=layer,
                fields=fields,
                font_size=font_size,
                null_display=null_disp,
                appearance=appearance,
            )
            ann_layer  = self._get_or_create_annotation_layer(key, layer.name(), fid)
            new_id     = ann_layer.addItem(item)
            self._annotation_items_by_id[new_id] = item
            self._active_items[key] = new_id

            payload["annotation_item_id"] = new_id
            payload["ann_layer_id"] = self._annotation_layer_ids.get(key)

            ann_layer.triggerRepaint()
            return True, "Attribute table annotation restored"
        except Exception as e:
            return False, f"Redo failed: {e}"

    def execute(self, context):
        detected_features = context.get("detected_features", [])
        if not detected_features:
            self.show_error("Show Attribute Table", "No line feature found here.")
            return

        detected = detected_features[0]
        feature  = detected.feature
        layer    = detected.layer

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.show_error(
                "Show Attribute Table",
                "This action only works with line (or multiline) layers."
            )
            return

        if layer.fields().count() == 0:
            self.show_info("Show Attribute Table", "This layer has no attribute fields.")
            return

        key = (layer.id(), feature.id())

        if key in self._active_items:
            self._remove_item(key)
            self.record_informational(
                description=(
                    f"Removed attribute table annotation for feature ID "
                    f"{feature.id()} on layer '{layer.name()}'"
                )
            )
            return

        try:
            font_size = int(self.get_setting("table_font_size", 9))
        except (ValueError, TypeError):
            font_size = 9

        null_display = str(self.get_setting("null_display", "NULL"))

        try:
            remember = bool(self.get_setting("remember_field_selection", True))
        except (ValueError, TypeError):
            remember = True

        saved_fields = self._load_saved_fields(layer.id()) if remember else []

        parent_widget = iface.mainWindow() if iface else None
        sel_dlg = FieldSelectionDialog(
            layer=layer,
            feature=feature,
            saved_fields=saved_fields,
            saved_appearance=_load_saved_appearance(),
            null_display=null_display,
            parent=parent_widget
        )
        if sel_dlg.exec_() != QDialog.Accepted:
            return

        selected = sel_dlg.selected_fields()
        if not selected:
            self.show_warning("Show Attribute Table", "No fields were selected.")
            return

        if remember and sel_dlg.should_remember():
            self._save_selected_fields(layer.id(), selected)

        appearance = sel_dlg.get_appearance()
        if sel_dlg.should_remember_appearance():
            _save_appearance(appearance)

        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            self.show_error("Show Attribute Table", "Feature has no geometry.")
            return

        # Determine anchor point along the line according to appearance
        line_pos = appearance.get("line_position", "midpoint")
        try:
            line_length = geom.length()
            if line_length and line_length > 0:
                if line_pos == "start":
                    dist = 0.0
                elif line_pos == "end":
                    dist = line_length
                else:
                    dist = line_length / 2.0
                interp_pt = geom.interpolate(dist)
                try:
                    pt = interp_pt.asPoint()
                except Exception:
                    pt = geom.boundingBox().center()
            else:
                pt = geom.boundingBox().center()
        except Exception:
            try:
                pt = geom.asPoint()
            except Exception:
                pt = geom.boundingBox().center()

        try:
            from qgis.core import QgsCoordinateTransform, QgsProject as _Proj
            canvas_crs = iface.mapCanvas().mapSettings().destinationCrs()
            if layer.crs().isValid() and canvas_crs.isValid() and layer.crs() != canvas_crs:
                _ct = QgsCoordinateTransform(layer.crs(), canvas_crs, _Proj.instance())
                pt = _ct.transform(pt)
        except Exception:
            pass
        map_point = QgsPointXY(pt.x(), pt.y())

        item = AttributeTableAnnotationItem(
            map_point=map_point,
            feature=feature,
            layer=layer,
            fields=selected,
            font_size=appearance.get("font_size", font_size),
            null_display=null_display,
            appearance=appearance,
        )
        ann_layer  = self._get_or_create_annotation_layer(key, layer.name(), feature.id())
        new_id     = ann_layer.addItem(item)
        self._annotation_items_by_id[new_id] = item
        self._active_items[key] = new_id
        ann_layer.triggerRepaint()

        self._last_payload = {
            "layer_id":            layer.id(),
            "layer_name":          layer.name(),
            "feature_id":          feature.id(),
            "fields_shown":        selected,
            "map_point_x":         map_point.x(),
            "map_point_y":         map_point.y(),
            "font_size":           font_size,
            "null_display":        null_display,
            "annotation_item_id":  new_id,
            "ann_layer_id":        self._annotation_layer_ids.get(key),
            "appearance":          appearance,
        }

        self.record_to_history(
            description=(
                f"Placed attribute table annotation for feature ID {feature.id()} "
                f"on layer '{layer.name()}' ({len(selected)} fields)"
            ),
            undo_type="create_feature",
            can_undo=True,
            undo_payload=self._last_payload,
            layers=[self.create_layer_descriptor(layer)],
            meta={
                "layer_id":     layer.id(),
                "layer_name":   layer.name(),
                "feature_id":   feature.id(),
                "fields_shown": selected,
            }
        )

    def _get_or_create_annotation_layer(self, key, source_layer_name, feature_id):
        from qgis.core import QgsProject, QgsAnnotationLayer
        proj = QgsProject.instance()
        existing_id = self._annotation_layer_ids.get(key)
        if existing_id:
            ann_layer = proj.mapLayer(existing_id)
            if ann_layer is not None:
                return ann_layer
        name = f"Attribute Table - {source_layer_name} - ID {feature_id}"
        ann_layer = QgsAnnotationLayer(
            name,
            QgsAnnotationLayer.LayerOptions(proj.transformContext()),
        )
        proj.addMapLayer(ann_layer)
        self._annotation_layer_ids[key] = ann_layer.id()
        return ann_layer

    def _remove_annotation_layer(self, key):
        from qgis.core import QgsProject
        layer_qgis_id = self._annotation_layer_ids.pop(key, None)
        if layer_qgis_id:
            try:
                QgsProject.instance().removeMapLayer(layer_qgis_id)
            except Exception:
                pass

    def _remove_item(self, key):
        item_id = self._active_items.pop(key, None)
        self._annotation_items_by_id.pop(item_id, None)
        self._remove_annotation_layer(key)

    def _settings_key(self, layer_id):
        return f"{self._SELECTION_SETTINGS_PREFIX}/{layer_id}"

    def _load_saved_fields(self, layer_id):
        try:
            raw = QSettings().value(self._settings_key(layer_id), None)
            if raw is None:
                return []
            if isinstance(raw, list):
                return raw
            if isinstance(raw, str):
                return [raw] if raw else []
            return list(raw)
        except Exception:
            return []

    def _save_selected_fields(self, layer_id, fields):
        try:
            QSettings().setValue(self._settings_key(layer_id), fields)
        except Exception:
            pass


# Global instance - required for automatic action discovery
show_line_attribute_table = ShowLineAttributeTableAction()
