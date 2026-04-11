"""
Show Point Layer Attribute Table Action for Right-click Utilities and Shortcuts Hub

Renders an Excel-like two-row attribute table directly on the map canvas
for EVERY point in the clicked layer.  Each annotation is anchored to its
point's geographic coordinates and moves with the map on pan/zoom — just
like the single-feature version, but applied to all features at once.

Triggering the action on a layer that already has annotations removes all
of them (toggle behaviour).  Undo removes all placed annotations at once;
redo recreates them.
"""

from .base_action import BaseAction

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QScrollArea, QWidget, QFrame, QApplication,
    QGroupBox, QSpinBox, QComboBox, QToolButton, QSizePolicy,
    QColorDialog, QMessageBox,
)
from qgis.PyQt.QtCore import Qt, QSettings, QRectF, QPointF
from qgis.PyQt.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath,
    QFontDatabase, QPixmap, QIcon,
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
    "placement":      "top",       # top | bottom | left | right | top-left | top-right | bottom-left | bottom-right
}

# NOTE: a future enhancement could expose a fixed-screen sizing mode here.

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

# Shared with the single-feature action so appearance settings are global
_APPEARANCE_SETTINGS_KEY = "RightClickUtilities/show_point_attribute_table/appearance"


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
    """Create a small square button that shows a solid colour swatch."""
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


# ---------------------------------------------------------------------------
# Field Selection + Appearance Dialog
# ---------------------------------------------------------------------------

class FieldSelectionDialog(QDialog):
    """Lets the user pick which fields to display and customise table appearance."""

    def __init__(self, layer, feature, features=None, saved_fields=None, saved_appearance=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Attribute Table on Map")
        self.setModal(True)
        # Make the dialog wider by default so controls can be laid out horizontally
        self.setMinimumWidth(640)

        self._layer        = layer
        self._feature      = feature
        # List of QgsFeature objects offered for selection (may be truncated)
        self._features     = features or []
        self._checkboxes   = {}
        self._saved_fields = saved_fields or []
        self._app = dict(saved_appearance) if saved_appearance else _load_saved_appearance()

        self._setup_ui()
        self._restore_selection()
        # Feature selection defaults
        self._restore_feature_selection()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # Put main content into a scroll area so the dialog can be wider
        # instead of very tall; keep action buttons fixed below.
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.NoFrame)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        try:
            screen = QApplication.primaryScreen()
            screen_h = screen.availableGeometry().height() if screen else 800
        except Exception:
            screen_h = 800
        main_scroll.setMaximumHeight(min(700, max(400, screen_h - 200)))

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

        # ---- Points / Features ----
        points_group = QGroupBox("Points to annotate")
        pg_layout = QVBoxLayout(points_group)
        pg_layout.setContentsMargins(6, 6, 6, 6)
        pg_layout.setSpacing(4)

        p_scroll = QScrollArea()
        p_scroll.setWidgetResizable(True)
        p_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        p_scroll.setFrameShape(QFrame.NoFrame)
        p_scroll.setMinimumHeight(150)
        p_scroll.setMaximumHeight(230)

        p_inner = QWidget()
        p_inner_layout = QVBoxLayout(p_inner)
        p_inner_layout.setSpacing(3)
        p_inner_layout.setContentsMargins(4, 4, 4, 4)

        # Feature checkboxes (show FID and short attribute preview)
        self._feature_checkboxes = {}
        for feat in self._features:
            fid = feat.id()
            preview = []
            cnt = 0
            for f in self._layer.fields():
                if cnt >= 2:
                    break
                val = feat[f.name()]
                if val is None or (hasattr(val, "isNull") and val.isNull()):
                    vstr = ""
                else:
                    vstr = str(val)
                if vstr:
                    preview.append(f"{f.name()}={vstr[:30]}")
                cnt += 1
            label = f"FID {fid}"
            if preview:
                label += "  —  " + ", ".join(preview)
            cb = QCheckBox(label)
            cb.setToolTip(f"Feature ID: {fid}")
            self._feature_checkboxes[fid] = cb
            p_inner_layout.addWidget(cb)

        p_inner_layout.addStretch()
        p_scroll.setWidget(p_inner)
        pg_layout.addWidget(p_scroll)

        feat_btn_row = QHBoxLayout()
        feat_select_all = QPushButton("Select All")
        feat_select_all.setMaximumWidth(100)
        feat_select_all.clicked.connect(self._select_all_features)
        feat_select_none = QPushButton("Select None")
        feat_select_none.setMaximumWidth(100)
        feat_select_none.clicked.connect(self._select_none_features)
        feat_btn_row.addWidget(feat_select_all)
        feat_btn_row.addWidget(feat_select_none)
        feat_btn_row.addStretch()
        pg_layout.addLayout(feat_btn_row)

        content_layout.addWidget(points_group)

        # ---- Fields ----
        fields_group = QGroupBox("Fields to display")
        fg_layout = QVBoxLayout(fields_group)
        fg_layout.setContentsMargins(6, 6, 6, 6)
        fg_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(150)
        scroll.setMaximumHeight(230)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(3)
        inner_layout.setContentsMargins(4, 4, 4, 4)

        for field in self._layer.fields():
            cb  = QCheckBox(field.name())
            raw = self._feature[field.name()]
            if raw is None or (hasattr(raw, "isNull") and raw.isNull()):
                tip_val = "NULL"
            else:
                tv      = str(raw)
                tip_val = tv[:60] + "..." if len(tv) > 60 else tv
            cb.setToolTip(f"Type: {field.typeName()}  |  Value: {tip_val}")
            self._checkboxes[field.name()] = cb
            inner_layout.addWidget(cb)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        fg_layout.addWidget(scroll)

        btn_row  = QHBoxLayout()
        btn_all  = QPushButton("Select All")
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

        # ---- Appearance (collapsible toggle) ----
        app_toggle = QToolButton()
        app_toggle.setText("▼  Appearance")
        app_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        app_toggle.setCheckable(True)
        # Show appearance controls expanded by default
        app_toggle.setChecked(True)
        app_toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        app_toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(app_toggle)

        self._app_container = QWidget()
        # Expanded by default
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
            hl    = QHBoxLayout(row_w)
            hl.setContentsMargins(0, 0, 0, 0)
            lbl   = QLabel(label_text)
            lbl.setFixedWidth(140)
            hl.addWidget(lbl)
            hl.addWidget(widget)
            hl.addStretch()
            app_layout.addWidget(row_w)

        # Font family
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

        # Font size
        self._font_spin = QSpinBox()
        self._font_spin.setRange(6, 28)
        self._font_spin.setValue(self._app.get("font_size", 9))
        self._font_spin.setSuffix(" pt")
        self._font_spin.setMaximumWidth(80)
        _row("Font size:", self._font_spin)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.HLine)
        _sep.setFrameShadow(QFrame.Sunken)
        app_layout.addWidget(_sep)

        # Colours
        self._btn_header_bg    = _make_color_button(self._app["header_bg"],    self)
        self._btn_header_fg    = _make_color_button(self._app["header_fg"],    self)
        self._btn_value_bg     = _make_color_button(self._app["value_bg"],     self)
        self._btn_value_bg_alt = _make_color_button(self._app["value_bg_alt"], self)
        self._btn_value_fg     = _make_color_button(self._app["value_fg"],     self)
        self._btn_grid         = _make_color_button(self._app["grid_color"],   self)
        self._btn_border       = _make_color_button(self._app["border_color"], self)
        self._btn_anchor       = _make_color_button(self._app["anchor_color"], self)

        _row("Header background:",    self._btn_header_bg)
        _row("Header text:",          self._btn_header_fg)
        _row("Value background:",     self._btn_value_bg)
        _row("Value background (alt):", self._btn_value_bg_alt)
        _row("Value text:",           self._btn_value_fg)
        _row("Grid / divider:",       self._btn_grid)
        _row("Border:",               self._btn_border)
        _row("Leader / anchor:",      self._btn_anchor)

        _sep2 = QFrame()
        _sep2.setFrameShape(QFrame.HLine)
        _sep2.setFrameShadow(QFrame.Sunken)
        app_layout.addWidget(_sep2)

        # Corner radius
        self._corner_spin = QSpinBox()
        self._corner_spin.setRange(0, 20)
        self._corner_spin.setValue(self._app.get("corner_radius", 5))
        self._corner_spin.setSuffix(" px")
        self._corner_spin.setMaximumWidth(80)
        _row("Corner radius:", self._corner_spin)

        # Placement compass
        from qgis.PyQt.QtWidgets import QGridLayout, QButtonGroup
        compass_outer = QWidget()
        compass_hl    = QHBoxLayout(compass_outer)
        compass_hl.setContentsMargins(0, 0, 0, 0)
        lbl_place = QLabel("Table placement:")
        lbl_place.setFixedWidth(140)
        compass_hl.addWidget(lbl_place)
        compass_w    = QWidget()
        compass_grid = QGridLayout(compass_w)
        compass_grid.setSpacing(2)
        compass_grid.setContentsMargins(0, 0, 0, 0)
        self._placement_buttons = {}
        self._placement_group   = QButtonGroup(self)
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

        # Shadow
        self._shadow_cb = QCheckBox("Draw drop shadow")
        self._shadow_cb.setChecked(bool(self._app.get("shadow", True)))
        app_layout.addWidget(self._shadow_cb)

        self._anchor_cb = QCheckBox("Show leader line and anchor dot")
        self._anchor_cb.setChecked(bool(self._app.get("show_anchor", True)))
        app_layout.addWidget(self._anchor_cb)

        def _sync_leader_combo(checked):
            self._leader_combo.setEnabled(checked)
        self._anchor_cb.toggled.connect(_sync_leader_combo)

        # Leader line style
        self._leader_combo = QComboBox()
        for style in _LEADER_STYLES:
            self._leader_combo.addItem(style.capitalize(), style)
        saved_leader = self._app.get("leader_style", "dot")
        li = self._leader_combo.findData(saved_leader)
        self._leader_combo.setCurrentIndex(li if li >= 0 else 0)
        self._leader_combo.setMaximumWidth(120)
        _row("Leader line style:", self._leader_combo)

        # Reset to defaults
        def _reset_defaults():
            d = dict(_DEFAULT_APPEARANCE)
            self._font_spin.setValue(d["font_size"])
            idx0 = self._font_combo.findData(d["font_family"])
            self._font_combo.setCurrentIndex(idx0 if idx0 >= 0 else 0)
            self._btn_header_bg._color    = QColor(d["header_bg"]);    self._btn_header_bg._update_icon()
            self._btn_header_fg._color    = QColor(d["header_fg"]);    self._btn_header_fg._update_icon()
            self._btn_value_bg._color     = QColor(d["value_bg"]);     self._btn_value_bg._update_icon()
            self._btn_value_bg_alt._color = QColor(d["value_bg_alt"]); self._btn_value_bg_alt._update_icon()
            self._btn_value_fg._color     = QColor(d["value_fg"]);     self._btn_value_fg._update_icon()
            self._btn_grid._color         = QColor(d["grid_color"]);   self._btn_grid._update_icon()
            self._btn_border._color       = QColor(d["border_color"]); self._btn_border._update_icon()
            self._btn_anchor._color       = QColor(d["anchor_color"]); self._btn_anchor._update_icon()
            self._corner_spin.setValue(d["corner_radius"])
            self._shadow_cb.setChecked(d["shadow"])
            self._anchor_cb.setChecked(d["show_anchor"])
            self._leader_combo.setEnabled(d["show_anchor"])
            li2 = self._leader_combo.findData(d["leader_style"])
            self._leader_combo.setCurrentIndex(li2 if li2 >= 0 else 0)
            dp = d.get("placement", "top")
            if dp in self._placement_buttons:
                self._placement_buttons[dp].setChecked(True)
            # sizing defaults were removed — only map-scaling is supported

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setMaximumWidth(150)
        reset_btn.clicked.connect(_reset_defaults)
        app_layout.addWidget(reset_btn)

        self._remember_app_cb = QCheckBox("Remember appearance settings globally")
        self._remember_app_cb.setChecked(True)
        app_layout.addWidget(self._remember_app_cb)

        content_layout.addWidget(self._app_container)

        # Finish scroll area and add it to the dialog; buttons remain fixed below
        main_scroll.setWidget(content)
        root.addWidget(main_scroll)

        # ---- Buttons ----
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

    # ------------------------------------------------------------------
    def _restore_selection(self):
        if self._saved_fields:
            for name, cb in self._checkboxes.items():
                cb.setChecked(name in self._saved_fields)
        else:
            for cb in self._checkboxes.values():
                cb.setChecked(True)

    def _restore_feature_selection(self):
        # Default to selecting all features presented in the dialog
        if getattr(self, "_feature_checkboxes", None):
            for cb in self._feature_checkboxes.values():
                cb.setChecked(True)

    def _select_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(True)

    def _select_none(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    def _select_all_features(self):
        for cb in self._feature_checkboxes.values():
            cb.setChecked(True)

    def _select_none_features(self):
        for cb in self._feature_checkboxes.values():
            cb.setChecked(False)

    def selected_fields(self):
        return [n for n, cb in self._checkboxes.items() if cb.isChecked()]

    def selected_feature_fids(self):
        return [fid for fid, cb in self._feature_checkboxes.items() if cb.isChecked()]

    def should_remember(self):
        return self._remember_cb.isChecked()

    def should_remember_appearance(self):
        return self._remember_app_cb.isChecked()

    def get_appearance(self) -> dict:
        fam = self._font_combo.currentData()
        return {
            "font_family":   fam if fam else "",
            "font_size":     self._font_spin.value(),
            "header_bg":     self._btn_header_bg._color.name(),
            "header_fg":     self._btn_header_fg._color.name(),
            "value_bg":      self._btn_value_bg._color.name(),
            "value_bg_alt":  self._btn_value_bg_alt._color.name(),
            "value_fg":      self._btn_value_fg._color.name(),
            "grid_color":    self._btn_grid._color.name(),
            "border_color":  self._btn_border._color.name(),
            "anchor_color":  self._btn_anchor._color.name(),
            "shadow":        self._shadow_cb.isChecked(),
            "corner_radius": self._corner_spin.value(),
            "show_anchor":   self._anchor_cb.isChecked(),
            "leader_style":  self._leader_combo.currentData(),
            "placement":     next(
                (pid for pid, btn in self._placement_buttons.items() if btn.isChecked()),
                "top"
            ),
            # Only map-scaled sizing is supported currently. Fixed-screen
            # sizing was removed due to inconsistent behaviour and may be
            # re-introduced in a future revision.
        }


# ---------------------------------------------------------------------------
# Annotation Item — renders in QgsAnnotationLayer (canvas + print layout)
# ---------------------------------------------------------------------------

class AttributeTableAnnotationItem(QgsAnnotationItem):
    """
    Excel-style two-row attribute table anchored to a geographic point.

    Subclasses QgsAnnotationItem so it lives inside a QgsAnnotationLayer and
    appears both in the live canvas and in Print Layout exports.
    """

    ITEM_TYPE = "show_point_layer_attribute_table_annotation_v1"

    def __init__(self, map_point, feature, layer, fields,
                 font_size, null_display, appearance=None):
        super().__init__()
        self._map_point_x  = map_point.x()
        self._map_point_y  = map_point.y()
        self._feature      = feature
        self._layer        = layer
        self._fields       = fields
        self._null_display = null_display

        self._app = dict(_DEFAULT_APPEARANCE)
        if appearance:
            self._app.update(appearance)
        if not appearance or "font_size" not in appearance:
            self._app["font_size"] = font_size

    # ------------------------------------------------------------------
    # QgsAnnotationItem required interface
    # ------------------------------------------------------------------

    def type(self):
        return self.ITEM_TYPE

    def clone(self):
        return AttributeTableAnnotationItem(
            QgsPointXY(self._map_point_x, self._map_point_y),
            self._feature, self._layer, self._fields,
            self._app.get("font_size", 9), self._null_display,
            dict(self._app),
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

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_value(value, null_display):
        if value is None or (hasattr(value, "isNull") and value.isNull()):
            return null_display
        return str(value)

    @staticmethod
    def _make_font_from_app(app, bold=False):
        """Create a QFont from appearance settings (map-scaled only).

        Fixed-screen sizing was removed due to inconsistent rendering
        behaviour; this may be revisited in a future update.
        """
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
        if   p == "top":          return -w / 2.0,  -(h + ll)
        elif p == "bottom":       return -w / 2.0,   ll
        elif p == "left":         return -(w + ll), -h / 2.0
        elif p == "right":        return  ll,        -h / 2.0
        elif p == "top-left":     return -(w + ll), -(h + ll)
        elif p == "top-right":    return  ll,        -(h + ll)
        elif p == "bottom-left":  return -(w + ll),  ll
        elif p == "bottom-right": return  ll,         ll
        elif p == "center":       return -w / 2.0,  -h / 2.0
        else:                     return -w / 2.0,  -(h + ll)

    @staticmethod
    def _leader_start(placement, tx, ty, w, h):
        p = placement
        if   p == "top":          return QPointF(tx + w / 2, ty + h)
        elif p == "bottom":       return QPointF(tx + w / 2, ty)
        elif p == "left":         return QPointF(tx + w,     ty + h / 2)
        elif p == "right":        return QPointF(tx,         ty + h / 2)
        elif p == "top-left":     return QPointF(tx + w,     ty + h)
        elif p == "top-right":    return QPointF(tx,         ty + h)
        elif p == "bottom-left":  return QPointF(tx + w,     ty)
        elif p == "bottom-right": return QPointF(tx,         ty)
        elif p == "center":       return QPointF(tx + w / 2, ty + h / 2)
        else:                     return QPointF(tx + w / 2, ty + h)

    # ------------------------------------------------------------------
    # Core render
    # ------------------------------------------------------------------

    def render(self, context, feedback=None):
        try:
            pt = QgsPointXY(self._map_point_x, self._map_point_y)
            ct = context.coordinateTransform()
            try:
                if ct.isValid():
                    pt = ct.transform(pt)
            except Exception:
                pass

            screen  = context.mapToPixel().transform(pt)
            painter = context.painter()
            painter.save()

            # Always translate to the anchor; fonts use configured point-size
            # and therefore scale with the map.
            painter.translate(screen.x(), screen.y())

            self._draw_table(painter)
            painter.restore()
        except Exception as e:
            try:
                from qgis.core import QgsMessageLog, Qgis
                QgsMessageLog.logMessage(
                    f"[LayerAttributeTableAnnotation] render() error: {e}",
                    "RightClickUtils", Qgis.Warning,
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
        draw_shadow  = bool(app.get("shadow",         True))
        show_anchor  = bool(app.get("show_anchor",    True))
        leader_style = app.get("leader_style", "dot")
        placement    = app.get("placement",    "top")

        painter.setRenderHint(QPainter.Antialiasing,     True)
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
        col_widths = []
        for field_name in self._fields:
            raw      = self._feature[field_name]
            val_text = self._fmt_value(raw, self._null_display)
            w_h = fm_h.horizontalAdvance(field_name) + 2 * pad_x
            w_v = fm_v.horizontalAdvance(val_text)   + 2 * pad_x
            cw  = max(w_h, w_v, min_col_w)
            cw  = min(cw, max_col_w)
            col_widths.append(cw)

        table_w      = sum(col_widths)
        table_h      = 2 * row_h
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
            raw       = self._feature[field_name]
            val_text  = self._fmt_value(raw, self._null_display)
            cell_rect = QRectF(x, ty + row_h, cw, row_h)
            elided    = fm_v.elidedText(val_text, Qt.ElideRight, int(cw) - 4)
            painter.drawText(cell_rect, Qt.AlignCenter, elided)
            x += cw

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
                    QPointF(0.0, 0.0),
                )
            painter.setPen(QPen(border_color, max(1.0, row_h * 0.1)))
            painter.setBrush(QBrush(anchor_color))
            painter.drawEllipse(QPointF(0.0, 0.0), anchor_dot_r, anchor_dot_r)


class ShowPointLayerAttributeTableAction(BaseAction):
    """
    Places attribute-table annotations on the map for every point feature
    in the clicked layer.  Re-triggering on the same layer removes all
    annotations (toggle).

    A single QgsAnnotationLayer is created per source layer so the QGIS
    layer panel stays clean even on large datasets.
    """

    _SELECTION_SETTINGS_PREFIX = (
        "RightClickUtilities/show_point_layer_attribute_table/saved_fields"
    )

    def __init__(self):
        super().__init__()

        self.action_id   = "show_point_layer_attribute_table"
        self.name        = "Show Attribute Table on Map (All Points)"
        self.category    = "Information"
        self.description = (
            "Place an Excel-like attribute table annotation for every point in "
            "the layer, anchored to each point's geographic coordinates. "
            "Field names appear in the header row; values appear below. "
            "Trigger again on the same layer to remove all annotations."
        )
        self.enabled = True

        self.set_action_scope("layer")
        self.set_supported_scopes(["layer"])
        self.set_supported_click_types(["point", "multipoint"])
        self.set_supported_geometry_types(["point", "multipoint"])

        # layer_id  →  {'ann_layer_id': str, 'item_ids': list[str]}
        self._active_layers: dict = {}

        # annotation item id  →  Python AttributeTableAnnotationItem
        # Must keep Python-side refs alive so SIP's virtual dispatch works
        # after C++ takes ownership of items via QgsAnnotationLayer.addItem().
        self._annotation_items_by_id: dict = {}

        # Payload for the most-recent execute() — used by get_undo_payload()
        self._last_payload = None

        # Register as own undo handler so the history manager calls
        # apply_undo / apply_redo on this instance directly.
        self.register_undo_handler()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings_schema(self):
        return {
            "table_font_size": {
                "type": "int",
                "default": 9,
                "label": "Table Font Size",
                "description": "Font size (pt) for text inside the map annotations",
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
            "max_features": {
                "type": "int",
                "default": 200,
                "label": "Max Features to Annotate",
                "description": (
                    "Maximum number of point features to annotate per layer. "
                    "If the layer exceeds this limit a warning is shown before proceeding."
                ),
                "min": 1,
                "max": 5000,
                "step": 50,
            },
        }

    # ------------------------------------------------------------------
    # Undo / redo support
    # ------------------------------------------------------------------

    def supports_undo(self):
        return True

    def get_undo_category(self):
        return "trivial"

    def get_undo_payload(self, context, execute_result=None):
        return self._last_payload or {}

    def apply_undo(self, payload):
        """Undo: remove every annotation placed for the layer."""
        try:
            layer_id     = payload.get("layer_id")
            ann_layer_id = payload.get("ann_layer_id")

            if layer_id:
                self._remove_all_for_layer(layer_id)
            elif ann_layer_id:
                # Fallback when layer_id missing from old payloads
                try:
                    from qgis.core import QgsProject
                    QgsProject.instance().removeMapLayer(ann_layer_id)
                except Exception:
                    pass

            return True, "All attribute table annotations removed"
        except Exception as e:
            return False, f"Undo failed: {e}"

    def apply_redo(self, payload):
        """Redo: recreate all annotations from stored payload data."""
        try:
            from qgis.core import QgsProject, QgsFeatureRequest, QgsCoordinateTransform

            layer_id      = payload.get("layer_id")
            fields        = payload.get("fields_shown", [])
            font_size     = int(payload.get("font_size", 9))
            null_disp     = str(payload.get("null_display", "NULL"))
            appearance    = payload.get("appearance") or {}
            features_data = payload.get("features_data", [])

            if not layer_id or not fields:
                return False, "Redo payload is incomplete"

            layer = QgsProject.instance().mapLayer(layer_id)
            if not layer:
                return False, "Layer no longer exists – cannot redo annotations"

            # Clean up any stale state
            self._remove_all_for_layer(layer_id)

            canvas_crs = iface.mapCanvas().mapSettings().destinationCrs()
            layer_crs  = layer.crs()
            transform  = None
            if layer_crs.isValid() and canvas_crs.isValid() and layer_crs != canvas_crs:
                transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())

            ann_layer = self._get_or_create_annotation_layer(layer_id, layer.name())
            item_ids  = []

            for fd in features_data:
                fid   = int(fd["fid"])
                pt_x  = float(fd["map_point_x"])
                pt_y  = float(fd["map_point_y"])

                feature = None
                for f in layer.getFeatures(QgsFeatureRequest().setFilterFid(fid)):
                    feature = f
                    break
                if feature is None:
                    continue

                map_point = QgsPointXY(pt_x, pt_y)
                item = AttributeTableAnnotationItem(
                    map_point=map_point,
                    feature=feature,
                    layer=layer,
                    fields=fields,
                    font_size=appearance.get("font_size", font_size),
                    null_display=null_disp,
                    appearance=appearance,
                )
                new_id = ann_layer.addItem(item)
                self._annotation_items_by_id[new_id] = item
                item_ids.append(new_id)

            if not item_ids:
                return False, "No features could be restored – all may have been deleted"

            self._active_layers[layer_id] = {
                "ann_layer_id": ann_layer.id(),
                "item_ids":     item_ids,
            }

            # Keep payload up-to-date so the next undo cycle finds the new layer id
            payload["ann_layer_id"] = ann_layer.id()

            ann_layer.triggerRepaint()
            return True, f"Restored {len(item_ids)} attribute table annotation(s)"
        except Exception as e:
            return False, f"Redo failed: {e}"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, context):
        detected_features = context.get("detected_features", [])
        if not detected_features:
            self.show_error(
                "Show Layer Attribute Table",
                "No point layer found here."
            )
            return

        layer = detected_features[0].layer

        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error(
                "Show Layer Attribute Table",
                "This action only works with point (or multipoint) layers."
            )
            return

        if layer.fields().count() == 0:
            self.show_info(
                "Show Layer Attribute Table",
                "This layer has no attribute fields."
            )
            return

        layer_id = layer.id()

        # --- Toggle: if annotations already active for this layer, remove all ---
        if layer_id in self._active_layers:
            count = len(self._active_layers[layer_id].get("item_ids", []))
            self._remove_all_for_layer(layer_id)
            self.record_informational(
                description=(
                    f"Removed {count} attribute table annotation(s) "
                    f"for layer '{layer.name()}'"
                )
            )
            return

        # --- Read settings ---
        try:
            font_size = int(self.get_setting("table_font_size", 9))
        except (ValueError, TypeError):
            font_size = 9

        null_display = str(self.get_setting("null_display", "NULL"))

        try:
            remember = bool(self.get_setting("remember_field_selection", True))
        except (ValueError, TypeError):
            remember = True

        try:
            max_features = int(self.get_setting("max_features", 200))
        except (ValueError, TypeError):
            max_features = 200

        # --- Warn when layer has more features than the configured limit ---
        feature_count = layer.featureCount()
        if feature_count > max_features:
            parent_w = iface.mainWindow() if iface else None
            resp = QMessageBox.question(
                parent_w,
                "Show Layer Attribute Table",
                (
                    f"This layer has {feature_count} feature(s), but the current "
                    f"limit is {max_features}.\n\n"
                    f"Only the first {max_features} features will be annotated.\n\n"
                    "Do you want to continue?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return

        # --- Representative feature for the field-selection dialog ---
        first_feature = None
        for f in layer.getFeatures():
            first_feature = f
            break

        if first_feature is None:
            self.show_info(
                "Show Layer Attribute Table",
                "This layer has no features."
            )
            return

        # --- Field selection + appearance dialog + feature selection ---
        saved_fields  = self._load_saved_fields(layer_id) if remember else []
        parent_widget = iface.mainWindow() if iface else None

        # Present up to `max_features` features for checkbox selection in the dialog
        features_for_dialog = []
        for f in layer.getFeatures():
            features_for_dialog.append(f)
            if len(features_for_dialog) >= max_features:
                break

        sel_dlg = FieldSelectionDialog(
            layer=layer,
            feature=first_feature,
            features=features_for_dialog,
            saved_fields=saved_fields,
            saved_appearance=_load_saved_appearance(),
            parent=parent_widget,
        )
        if sel_dlg.exec_() != QDialog.Accepted:
            return

        selected = sel_dlg.selected_fields()
        if not selected:
            self.show_warning(
                "Show Layer Attribute Table",
                "No fields were selected."
            )
            return

        selected_fids = sel_dlg.selected_feature_fids()
        if not selected_fids:
            self.show_warning(
                "Show Layer Attribute Table",
                "No features were selected."
            )
            return

        if remember and sel_dlg.should_remember():
            self._save_selected_fields(layer_id, selected)

        appearance = sel_dlg.get_appearance()
        if sel_dlg.should_remember_appearance():
            _save_appearance(appearance)

        # --- Prepare CRS transform (layer CRS → canvas CRS) ---
        canvas_crs = iface.mapCanvas().mapSettings().destinationCrs()
        layer_crs  = layer.crs()
        transform  = None
        if layer_crs.isValid() and canvas_crs.isValid() and layer_crs != canvas_crs:
            from qgis.core import QgsCoordinateTransform, QgsProject
            transform = QgsCoordinateTransform(
                layer_crs, canvas_crs, QgsProject.instance()
            )

        # --- Create the single annotation layer for this source layer ---
        ann_layer     = self._get_or_create_annotation_layer(layer_id, layer.name())
        item_ids      = []
        features_data = []
        processed     = 0

        selected_fids_set = set(selected_fids)

        for feature in layer.getFeatures():
            if processed >= max_features:
                break

            # Skip features not chosen by the user
            if feature.id() not in selected_fids_set:
                continue

            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue

            pt = geom.asPoint()
            if transform:
                try:
                    pt = transform.transform(pt)
                except Exception:
                    continue

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
            new_id = ann_layer.addItem(item)
            self._annotation_items_by_id[new_id] = item
            item_ids.append(new_id)
            features_data.append({
                "fid":         feature.id(),
                "map_point_x": map_point.x(),
                "map_point_y": map_point.y(),
            })
            processed += 1

        # --- Bail out if no valid geometries were found ---
        if not item_ids:
            self.show_warning(
                "Show Layer Attribute Table",
                "No features with valid geometry were found."
            )
            from qgis.core import QgsProject
            QgsProject.instance().removeMapLayer(ann_layer.id())
            self._active_layers.pop(layer_id, None)
            return

        self._active_layers[layer_id] = {
            "ann_layer_id": ann_layer.id(),
            "item_ids":     item_ids,
        }

        ann_layer.triggerRepaint()

        # --- Record to history with full undo payload ---
        self._last_payload = {
            "layer_id":      layer_id,
            "layer_name":    layer.name(),
            "ann_layer_id":  ann_layer.id(),
            "fields_shown":  selected,
            "font_size":     font_size,
            "null_display":  null_display,
            "appearance":    appearance,
            "features_data": features_data,
        }

        self.record_to_history(
            description=(
                f"Placed attribute table annotations for {len(item_ids)} point(s) "
                f"on layer '{layer.name()}' ({len(selected)} fields)"
            ),
            undo_type="create_layer",
            can_undo=True,
            undo_payload=self._last_payload,
            layers=[self.create_layer_descriptor(layer)],
            meta={
                "layer_id":      layer_id,
                "layer_name":    layer.name(),
                "feature_count": len(item_ids),
                "fields_shown":  selected,
            },
        )

    # ------------------------------------------------------------------
    # Annotation layer management
    # ------------------------------------------------------------------

    def _get_or_create_annotation_layer(self, layer_id: str, layer_name: str):
        """
        Return the existing QgsAnnotationLayer for this source layer, or
        create a new one named "Attribute Table (All Points) - {layer_name}".
        One annotation layer is shared by all features of the same source layer.
        """
        from qgis.core import QgsProject, QgsAnnotationLayer
        proj = QgsProject.instance()

        layer_info      = self._active_layers.get(layer_id, {})
        existing_ann_id = layer_info.get("ann_layer_id")
        if existing_ann_id:
            ann_layer = proj.mapLayer(existing_ann_id)
            if ann_layer is not None:
                return ann_layer

        name      = f"Attribute Table (All Points) - {layer_name}"
        ann_layer = QgsAnnotationLayer(
            name,
            QgsAnnotationLayer.LayerOptions(proj.transformContext()),
        )
        proj.addMapLayer(ann_layer)

        if layer_id not in self._active_layers:
            self._active_layers[layer_id] = {}
        self._active_layers[layer_id]["ann_layer_id"] = ann_layer.id()
        return ann_layer

    def _remove_all_for_layer(self, layer_id: str):
        """Remove the annotation layer and all Python item references for a source layer."""
        from qgis.core import QgsProject
        layer_info = self._active_layers.pop(layer_id, None)
        if not layer_info:
            return

        for item_id in layer_info.get("item_ids", []):
            self._annotation_items_by_id.pop(item_id, None)

        ann_layer_id = layer_info.get("ann_layer_id")
        if ann_layer_id:
            try:
                QgsProject.instance().removeMapLayer(ann_layer_id)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Saved field selection helpers
    # ------------------------------------------------------------------

    def _settings_key(self, layer_id: str) -> str:
        return f"{self._SELECTION_SETTINGS_PREFIX}/{layer_id}"

    def _load_saved_fields(self, layer_id: str) -> list:
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

    def _save_selected_fields(self, layer_id: str, fields: list):
        try:
            QSettings().setValue(self._settings_key(layer_id), fields)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Global instance – required for automatic action discovery
# ---------------------------------------------------------------------------
show_point_layer_attribute_table = ShowPointLayerAttributeTableAction()
