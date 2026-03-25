"""
Number Points in Layer Action for Right-click Utilities and Shortcuts Hub

Creates a new integer field in a point layer and assigns sequential numbers
to all features based on a user-chosen ordering method (northernmost first,
nearest to origin, by feature ID, etc.).
"""

from .base_action import BaseAction
from qgis.core import QgsWkbTypes, QgsField, QgsProject
from qgis.PyQt.QtCore import QMetaType, QVariant, Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame
)
import math


# ──────────────────────────────────────────────────────────────────────────────
# Reference-point helpers
# ──────────────────────────────────────────────────────────────────────────────

# For single-point features every option is equivalent (the point IS the
# reference).  For multipoint features these options pick a meaningful
# representative coordinate from the multi-geometry.

REFERENCE_POINTS = {
    'centroid':     'Centroid / point itself (default)',
    'bbox_center':  'Bounding box center',
    'northernmost': 'Northernmost point (max Y)',
    'southernmost': 'Southernmost point (min Y)',
    'easternmost':  'Easternmost point (max X)',
    'westernmost':  'Westernmost point (min X)',
}


def _get_ref_point(feature, ref_type):
    """Return (x, y) for a feature according to ref_type."""
    geom = feature.geometry()
    if geom is None or geom.isEmpty():
        return (0.0, 0.0)
    if ref_type == 'centroid':
        c = geom.centroid()
        if not c.isEmpty():
            pt = c.asPoint()
            return (pt.x(), pt.y())
    elif ref_type == 'bbox_center':
        bb = geom.boundingBox()
        return (bb.center().x(), bb.center().y())
    elif ref_type == 'northernmost':
        bb = geom.boundingBox()
        return (bb.center().x(), bb.yMaximum())
    elif ref_type == 'southernmost':
        bb = geom.boundingBox()
        return (bb.center().x(), bb.yMinimum())
    elif ref_type == 'easternmost':
        bb = geom.boundingBox()
        return (bb.xMaximum(), bb.center().y())
    elif ref_type == 'westernmost':
        bb = geom.boundingBox()
        return (bb.xMinimum(), bb.center().y())
    # fallback: centroid
    c = geom.centroid()
    if not c.isEmpty():
        pt = c.asPoint()
        return (pt.x(), pt.y())
    return (0.0, 0.0)


# ──────────────────────────────────────────────────────────────────────────────
# Attribute-field sort helpers
# ──────────────────────────────────────────────────────────────────────────────

class _Desc:
    """Wraps a value so it sorts in descending order, with NULLs last."""
    __slots__ = ('val',)

    def __init__(self, v):
        self.val = v

    def __lt__(self, o):
        if self.val is None and o.val is None:
            return False
        if self.val is None:
            return False    # nulls sort last
        if o.val is None:
            return True
        try:
            return self.val > o.val
        except TypeError:
            return str(self.val) > str(o.val)

    def __eq__(self, o):
        return self.val == o.val

    def __le__(self, o):
        return self.__lt__(o) or self.__eq__(o)

    def __gt__(self, o):
        return not self.__le__(o)

    def __ge__(self, o):
        return not self.__lt__(o)


def _attr_sort_key(feature, field_name, ascending):
    """Return a sort key for ordering features by the value of an existing field.

    NULL values are always sorted last regardless of direction.
    Numeric strings are compared numerically; anything else as lower-case text.
    """
    try:
        val = feature.attribute(field_name)
    except Exception:
        val = None
    if isinstance(val, QVariant):
        val = None
    if val is None:
        return (1,)
    try:
        numeric = float(val)
        return (0, numeric) if ascending else (0, _Desc(numeric))
    except (TypeError, ValueError):
        s = str(val).lower()
        return (0, s) if ascending else (0, _Desc(s))


def _attr_output_field_name(src_field_name, direction):
    """Generate a ≤10-char output field name for attribute-based ordering.

    Pattern: n_<up-to-6-safe-chars>_a  /  n_<…>_d
    """
    suffix = '_a' if direction == 'asc' else '_d'
    prefix = 'n_'
    max_src = 10 - len(prefix) - len(suffix)   # = 6
    safe = ''.join(c for c in src_field_name.lower() if c.isalnum() or c == '_')
    return f"{prefix}{safe[:max_src]}{suffix}"


# ──────────────────────────────────────────────────────────────────────────────
# Sort-method catalogue
# Each entry:
#   label        – human-readable name shown in the dialog
#   field_name   – auto-generated field name (≤10 chars for shapefile safety)
#   uses_ref_pt  – True if reference-point setting affects sorting
#   sort_fn(f, ref_type) → sort key
# ──────────────────────────────────────────────────────────────────────────────

SORT_METHODS = {
    'north_to_south': {
        'label':       'North to South',
        'field_name':  'num_n_s',
        'uses_ref_pt': True,
        'sort_fn':     lambda f, ref: -_get_ref_point(f, ref)[1],
    },
    'south_to_north': {
        'label':       'South to North',
        'field_name':  'num_s_n',
        'uses_ref_pt': True,
        'sort_fn':     lambda f, ref: _get_ref_point(f, ref)[1],
    },
    'west_to_east': {
        'label':       'West to East',
        'field_name':  'num_w_e',
        'uses_ref_pt': True,
        'sort_fn':     lambda f, ref: _get_ref_point(f, ref)[0],
    },
    'east_to_west': {
        'label':       'East to West',
        'field_name':  'num_e_w',
        'uses_ref_pt': True,
        'sort_fn':     lambda f, ref: -_get_ref_point(f, ref)[0],
    },
    'distance_from_origin': {
        'label':       'Nearest to Farthest from Origin (0, 0)',
        'field_name':  'num_dist',
        'uses_ref_pt': True,
        'sort_fn':     lambda f, ref: math.hypot(*_get_ref_point(f, ref)),
    },
    'fid_asc': {
        'label':       'By Feature ID (ascending)',
        'field_name':  'num_fid',
        'uses_ref_pt': False,
        'sort_fn':     lambda f, ref: f.id(),
    },
}


# Group for the dialog
SORT_METHOD_GROUPS = [
    (
        "Position",
        ['north_to_south', 'south_to_north', 'west_to_east', 'east_to_west'],
    ),
    (
        "Other",
        ['distance_from_origin', 'fid_asc'],
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# Ordering-method picker dialog
# ──────────────────────────────────────────────────────────────────────────────

class NumberPointsDialog(QDialog):
    """
    Dialog for choosing one or more numbering fields to create.
    Each method gets a checkbox; the field name that will be written is shown
    next to the label so the user knows exactly what will be created.
    """

    def __init__(self, layer_name, ref_point_label='Centroid / point itself (default)',
                 layer_fields=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Number Points")
        self.setModal(True)
        self.setMinimumWidth(430)

        self._checkboxes = {}
        # {(field_name, 'asc'/'desc'): QCheckBox}
        self._attr_checkboxes = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        header = QLabel(f"<b>Layer:</b> {layer_name}")
        layout.addWidget(header)

        ref_lbl = QLabel(f"<b>Reference point</b> (position-based methods): {ref_point_label}")
        ref_lbl.setWordWrap(True)
        ref_lbl.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(ref_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        method_label = QLabel("Select numbering fields to create (one field per method):")
        method_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(method_label)

        # ── Scrollable checkbox list ───────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(6)

        for group_title, method_keys in SORT_METHOD_GROUPS:
            group_box = QGroupBox(group_title)
            group_vbox = QVBoxLayout(group_box)
            group_vbox.setSpacing(2)
            group_vbox.setContentsMargins(8, 4, 8, 6)
            for key in method_keys:
                m = SORT_METHODS[key]
                ref_note = " *" if m['uses_ref_pt'] else ""
                cb = QCheckBox(f"{m['label']}{ref_note}   →  field: {m['field_name']}")
                cb._method_key = key
                group_vbox.addWidget(cb)
                self._checkboxes[key] = cb
            scroll_layout.addWidget(group_box)

        # ── By Attribute Field group (dynamic, based on layer fields) ──────────
        if layer_fields:
            attr_group = QGroupBox("By Attribute Field")
            attr_vbox = QVBoxLayout(attr_group)
            attr_vbox.setSpacing(2)
            attr_vbox.setContentsMargins(8, 4, 8, 8)
            attr_note = QLabel("Order by any existing field value — one output field per selection")
            attr_note.setStyleSheet("color: #666; font-size: 10px;")
            attr_note.setWordWrap(True)
            attr_vbox.addWidget(attr_note)
            for fname, ftype in layer_fields:
                out_asc  = _attr_output_field_name(fname, 'asc')
                out_desc = _attr_output_field_name(fname, 'desc')
                row = QWidget()
                row_h = QHBoxLayout(row)
                row_h.setContentsMargins(0, 2, 0, 2)
                lbl = QLabel(f"<b>{fname}</b> <span style='color:#888'>({ftype})</span>")
                lbl.setMinimumWidth(150)
                cb_asc  = QCheckBox(f"\u2191 asc  \u2192  {out_asc}")
                cb_desc = QCheckBox(f"\u2193 desc  \u2192  {out_desc}")
                row_h.addWidget(lbl)
                row_h.addWidget(cb_asc)
                row_h.addWidget(cb_desc)
                row_h.addStretch()
                attr_vbox.addWidget(row)
                self._attr_checkboxes[(fname, 'asc')]  = cb_asc
                self._attr_checkboxes[(fname, 'desc')] = cb_desc
                cb_asc.stateChanged.connect(self._update_ok)
                cb_desc.stateChanged.connect(self._update_ok)
            scroll_layout.addWidget(attr_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        scroll.setMinimumHeight(240)
        layout.addWidget(scroll)

        note = QLabel("* affected by Reference Point setting")
        note.setStyleSheet("color: #777; font-size: 10px;")
        layout.addWidget(note)

        # ── Select-all / clear row ─────────────────────────────────────────────
        sel_row = QHBoxLayout()
        all_btn = QPushButton("Select All")
        none_btn = QPushButton("Clear All")
        all_btn.setFixedWidth(90)
        none_btn.setFixedWidth(90)
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("Number Points")
        self._ok_btn.setDefault(True)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        for cb in self._checkboxes.values():
            cb.stateChanged.connect(self._update_ok)

    def _set_all(self, state):
        for cb in self._checkboxes.values():
            cb.setChecked(state)
        for cb in self._attr_checkboxes.values():
            cb.setChecked(state)

    def _update_ok(self):
        has_any = (
            any(cb.isChecked() for cb in self._checkboxes.values())
            or any(cb.isChecked() for cb in self._attr_checkboxes.values())
        )
        self._ok_btn.setEnabled(has_any)

    @property
    def selected_methods(self):
        result = []
        for key in SORT_METHODS:
            if key in self._checkboxes and self._checkboxes[key].isChecked():
                result.append({'type': 'static', 'key': key})
        for (fname, direction), cb in self._attr_checkboxes.items():
            if cb.isChecked():
                result.append({
                    'type':       'attribute',
                    'src_field':  fname,
                    'direction':  direction,
                    'field_name': _attr_output_field_name(fname, direction),
                    'label':      f"By '{fname}' ({'ascending' if direction == 'asc' else 'descending'})",
                })
        return result


# ──────────────────────────────────────────────────────────────────────────────
# Action class
# ──────────────────────────────────────────────────────────────────────────────

class NumberPointsLayerAction(BaseAction):
    """
    Action to number all point features in a layer.

    Adds (or overwrites) an integer field and writes sequential numbers
    (starting from 1) ordered according to the user's chosen method.
    """

    def __init__(self):
        super().__init__()

        self.action_id = "number_points_layer"
        self.name = "Number Points"
        self.category = "Analysis"
        self.description = (
            "Adds a sequential number field to a point layer. "
            "The numbering order is configurable: by position (north/south/east/west), "
            "or by proximity to the map origin. "
            "If the chosen field already exists its values are overwritten."
        )
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

        self._undo_state = None

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings_schema(self):
        return {
            'reference_point': {
                'type': 'choice',
                'default': 'centroid',
                'label': 'Reference Point',
                'description': (
                    'Which coordinate is used to represent a point feature for position-based ordering '
                    '(North/South/East/West and Distance from Origin). '
                    'For single-point features all options are equivalent — the point IS the reference. '
                    'For multipoint features this selects which part of the multi-geometry to use.'
                ),
                'options': list(REFERENCE_POINTS.keys()),
            },
            'start_number': {
                'type': 'int',
                'default': 1,
                'label': 'Starting Number',
                'description': 'The first number to assign (e.g. 1 gives 1, 2, 3 …; 0 gives 0, 1, 2 …).',
                'min': 0,
                'max': 9999,
                'step': 1,
            },
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': (
                    'When checked, only selected features are numbered starting from the starting number. '
                    'Other features are left unchanged.'
                ),
            },
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    # ── Undo support ──────────────────────────────────────────────────────────

    def supports_undo(self):
        return True

    def get_undo_category(self):
        return 'payload'

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, context):
        """Number all point features using one or more sort methods chosen in the dialog."""

        # ── Read settings ──────────────────────────────────────────────────────
        try:
            ref_type         = str(self.get_setting('reference_point', 'centroid'))
            start_number     = int(self.get_setting('start_number', 1))
            process_selected = str(self.get_setting('process_selected_only', False)).lower() == 'true'
        except (ValueError, TypeError) as e:
            self.show_error("Settings Error", f"Invalid setting values: {e}")
            return

        if ref_type not in REFERENCE_POINTS:
            ref_type = 'centroid'

        # ── Extract layer ──────────────────────────────────────────────────────
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No features found at this location.")
            return

        layer = detected_features[0].layer

        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "This action only works with point layers.")
            return

        # ── Show method-picker dialog ──────────────────────────────────────────
        layer_fields = [(f.name(), f.typeName()) for f in layer.fields()]
        dlg = NumberPointsDialog(
            layer_name=layer.name(),
            ref_point_label=REFERENCE_POINTS.get(ref_type, ref_type),
            layer_fields=layer_fields,
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        selected_methods = dlg.selected_methods
        if not selected_methods:
            return

        # ── Resolve selected methods to unified specs ──────────────────────────
        method_specs = []
        for m in selected_methods:
            if m['type'] == 'static':
                info = SORT_METHODS[m['key']]
                method_specs.append({
                    'id':         m['key'],
                    'label':      info['label'],
                    'field_name': info['field_name'],
                    'sort_fn':    info['sort_fn'],
                })
            else:
                asc = (m['direction'] == 'asc')
                method_specs.append({
                    'id':         f"attr_{m['src_field']}_{m['direction']}",
                    'label':      m['label'],
                    'field_name': m['field_name'],
                    'sort_fn':    lambda f, ref, sf=m['src_field'], a=asc: _attr_sort_key(f, sf, a),
                })

        # ── Collect features to process ────────────────────────────────────────
        if process_selected and layer.selectedFeatureCount() > 0:
            features = list(layer.selectedFeatures())
            scope_label = f"{len(features)} selected feature(s)"
        else:
            features = list(layer.getFeatures())
            scope_label = f"all {len(features)} feature(s)"

        if not features:
            self.show_warning("Nothing to Number", "No features to process in this layer.")
            return

        # ── Pre-sort features for every chosen method (outside edit mode) ──────
        sorted_per_method = {}
        for spec in method_specs:
            fn = spec['sort_fn']
            try:
                sorted_per_method[spec['id']] = sorted(features, key=lambda f, _fn=fn: _fn(f, ref_type))
            except Exception as sort_err:
                self.show_error("Sort Error",
                    f"Could not sort features by '{spec['label']}': {sort_err}")
                return

        # ── Confirm ────────────────────────────────────────────────────────────
        lines = []
        for spec in method_specs:
            fn_name = spec['field_name']
            verb = "overwrite" if layer.fields().indexOf(fn_name) >= 0 else "create"
            lines.append(f"  • {fn_name}  ({spec['label']})  [{verb}]")

        msg = (
            f"Will write the following field(s) on layer '{layer.name()}'\n"
            f"for {scope_label}:\n\n"
            + "\n".join(lines)
            + f"\n\nNumbers start at {start_number}.\n"
            f"Reference point: {REFERENCE_POINTS.get(ref_type, ref_type)}"
        )
        if not self.confirm_action("Number Points", msg):
            return

        # ── Enter edit mode once for all fields ────────────────────────────────
        edit_result = self.handle_edit_mode(layer, "numbering points")
        if edit_result[0] is None:
            return
        was_in_edit_mode, edit_mode_entered = edit_result

        try:
            undo_entries = []

            for spec in method_specs:
                field_name = spec['field_name']
                sorted_feats = sorted_per_method[spec['id']]

                # ── Create field if it doesn't exist ───────────────────────────
                field_exists = layer.fields().indexOf(field_name) >= 0
                field_was_created = False
                if not field_exists:
                    new_field = QgsField(field_name, QMetaType.Int)
                    if not layer.dataProvider().addAttributes([new_field]):
                        self.show_error("Error", f"Could not add field '{field_name}'.")
                        layer.rollBack()
                        return
                    layer.updateFields()
                    field_was_created = True
                else:
                    layer.updateFields()

                field_idx = layer.fields().indexOf(field_name)
                if field_idx < 0:
                    self.show_error("Error", f"Field '{field_name}' not found after creation.")
                    layer.rollBack()
                    return

                # ── Collect old values ─────────────────────────────────────────
                old_values = {}
                if field_was_created:
                    for feat in sorted_feats:
                        old_values[feat.id()] = None
                else:
                    for feat in layer.getFeatures():
                        old_values[feat.id()] = feat.attribute(field_idx)

                # ── Write numbers ──────────────────────────────────────────────
                feature_changes = []
                for i, feat in enumerate(sorted_feats):
                    number = start_number + i
                    if layer.changeAttributeValue(feat.id(), field_idx, number):
                        feature_changes.append({
                            'fid': int(feat.id()),
                            'old_attributes': {field_name: old_values.get(feat.id())},
                            'new_attributes': {field_name: number},
                        })

                undo_entries.append({
                    'method':            spec['id'],
                    'method_label':      spec['label'],
                    'field_name':        field_name,
                    'field_was_created': field_was_created,
                    'feature_changes':   feature_changes,
                })

            # ── Single commit for all fields ───────────────────────────────────
            if not layer.commitChanges():
                errors = layer.commitErrors()
                self.show_error("Commit Failed",
                    f"Could not save changes: {'; '.join(errors)}")
                layer.rollBack()
                return

            layer.triggerRepaint()

            # ── Store undo state ───────────────────────────────────────────────
            self._undo_state = {
                'layer_info': self.create_layer_descriptor(layer),
                'entries':    undo_entries,
            }

            # ── Record to history ──────────────────────────────────────────────
            any_created = any(e['field_was_created'] for e in undo_entries)
            all_changes = [c for e in undo_entries for c in e['feature_changes']]
            self.record_to_history(
                description=(
                    f"Numbered {len(features)} point(s) in '{layer.name()}' — "
                    + ", ".join(
                        f"{e['field_name']} ({e.get('method_label', e['method'])})"
                        for e in undo_entries
                    )
                ),
                undo_type='add_field' if any_created else 'update_attributes',
                layers=[self._undo_state['layer_info']],
                features=all_changes,
                meta={
                    'methods':      [s['id'] for s in method_specs],
                    'ref_type':     ref_type,
                    'start_number': start_number,
                },
            )

            # ── Success message ────────────────────────────────────────────────
            summary = "\n".join(
                f"  • {e['field_name']}  ({e.get('method_label', e['method'])})"
                for e in undo_entries
            )
            self.show_info(
                "Points Numbered",
                f"Numbered {len(features)} point(s) on layer '{layer.name()}'.\n\n"
                f"Fields written:\n{summary}"
            )

        except Exception as exc:
            try:
                if layer.isEditable():
                    layer.rollBack()
            except Exception:
                pass
            self.show_error("Unexpected Error", f"An error occurred while numbering points: {exc}")

    # ── Undo ──────────────────────────────────────────────────────────────────

    def apply_undo(self, payload):
        """
        Undo all fields written in one action invocation.

        - Fields that were newly created → deleted entirely.
        - Fields that already existed → their values restored.
        Processed in reverse order to handle schema indices correctly.
        """
        if not payload:
            return False, "No undo payload available."

        layer_info = payload.get('layer_info', {})
        entries    = payload.get('entries', [])

        layer_id = layer_info.get('layer_id', '')
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return False, f"Layer '{layer_info.get('layer_name', layer_id)}' no longer exists in the project."

        if layer.readOnly():
            return False, f"Layer '{layer.name()}' is read-only."

        if not layer.startEditing():
            return False, f"Could not enter edit mode for layer '{layer.name()}'."

        try:
            for entry in reversed(entries):
                field_name        = entry['field_name']
                field_was_created = entry['field_was_created']
                feature_changes   = entry['feature_changes']

                if field_was_created:
                    field_idx = layer.fields().indexOf(field_name)
                    if field_idx < 0:
                        continue  # Already gone
                    if not layer.dataProvider().deleteAttributes([field_idx]):
                        layer.rollBack()
                        return False, f"Could not delete field '{field_name}'."
                    layer.updateFields()
                else:
                    field_idx = layer.fields().indexOf(field_name)
                    if field_idx < 0:
                        layer.rollBack()
                        return False, f"Field '{field_name}' no longer exists in the layer."
                    for change in feature_changes:
                        layer.changeAttributeValue(
                            change['fid'], field_idx,
                            change['old_attributes'].get(field_name)
                        )

            if not layer.commitChanges():
                errors = layer.commitErrors()
                layer.rollBack()
                return False, f"Could not commit undo changes: {'; '.join(errors)}"

            layer.triggerRepaint()
            n_deleted  = sum(1 for e in entries if e['field_was_created'])
            n_restored = len(entries) - n_deleted
            parts = []
            if n_deleted:  parts.append(f"deleted {n_deleted} field(s)")
            if n_restored: parts.append(f"restored {n_restored} field(s)")
            return True, f"Undo successful: {', '.join(parts)} on layer '{layer.name()}'."

        except Exception as exc:
            try:
                layer.rollBack()
            except Exception:
                pass
            return False, f"Undo failed: {exc}"

    def get_undo_payload(self, context, execute_result=None):
        if self._undo_state is None:
            return {}
        payload = dict(self._undo_state)
        self._undo_state = None
        return payload


# ── Global instance for automatic discovery ───────────────────────────────────
number_points_layer = NumberPointsLayerAction()
