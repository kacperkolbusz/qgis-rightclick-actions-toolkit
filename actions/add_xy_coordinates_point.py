"""
Add X/Y Coordinates Fields to Point Layer Action for Right-click Utilities and Shortcuts Hub

Adds calculated X and Y coordinate fields to point layers. Opens a dialog to select which coordinate fields to add,
then creates them with proper formulas and populates all features with calculated values.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
                                 QPushButton, QLabel)
from qgis.PyQt.QtCore import Qt, QMetaType
from qgis.core import (QgsField, QgsExpression, QgsExpressionContext,
                      QgsExpressionContextUtils, QgsWkbTypes)
from qgis.PyQt.QtCore import QVariant
import math


class CoordinateFieldsDialog(QDialog):
    """Dialog for selecting which coordinate fields to add."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Coordinate Fields to Point Layer")
        self.setModal(True)
        self.resize(400, 350)
        
        # Available coordinate fields
        self.available_fields = {
            "x_coord": {
                "formula": "$x",
                "description": "X coordinate of the point in layer CRS units",
                "type": QVariant.Double
            },
            "y_coord": {
                "formula": "$y", 
                "description": "Y coordinate of the point in layer CRS units",
                "type": QVariant.Double
            },
            "longitude": {
                "formula": "$x",
                "description": "Longitude of the point (X coordinate in layer CRS)",
                "type": QVariant.Double
            },
            "latitude": {
                "formula": "$y",
                "description": "Latitude of the point (Y coordinate in layer CRS)",
                "type": QVariant.Double
            }
        }
        
        self.selected_fields = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Select coordinate fields to add:")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Info label
        info_label = QLabel("Note: Longitude/Latitude fields use the same values as X/Y coordinates in the layer's CRS")
        info_label.setStyleSheet("color: #666; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Create checkboxes for each field
        for field_name, field_info in self.available_fields.items():
            checkbox = QCheckBox(field_name)
            checkbox.setToolTip(f"{field_info['description']}\nFormula: {field_info['formula']}")
            checkbox.stateChanged.connect(lambda state, name=field_name: self.on_field_selected(name, state))
            layout.addWidget(checkbox)
        
        # Select all/none buttons
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_none_btn = QPushButton("Select None")
        select_all_btn.clicked.connect(self.select_all)
        select_none_btn.clicked.connect(self.select_none)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        self.create_btn = QPushButton("Create Fields")
        self.create_btn.setEnabled(False)
        self.create_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def on_field_selected(self, field_name, state):
        """Handle field selection."""
        if state == Qt.Checked:
            self.selected_fields[field_name] = self.available_fields[field_name]
        else:
            self.selected_fields.pop(field_name, None)
        
        # Enable/disable create button
        self.create_btn.setEnabled(len(self.selected_fields) > 0)
    
    def select_all(self):
        """Select all fields."""
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                item.widget().setChecked(True)
    
    def select_none(self):
        """Deselect all fields."""
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                item.widget().setChecked(False)


class AddXYCoordinatesPointAction(BaseAction):
    """Action to add X/Y coordinate calculated fields to point layers."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "add_xy_coordinates_point"
        self.name = "Add Coordinate Fields"
        self.category = "Analysis"
        self.description = "Add calculated coordinate fields to point layer. Opens dialog to select which coordinate fields to add (X/Y coordinates or longitude/latitude), then creates them with proper formulas and populates all features with calculated values. Automatically handles edit mode."
        self.enabled = True
        
        # Action scoping - works on entire layers (affects all features in layer)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with points
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            'confirm_before_adding': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Adding Fields',
                'description': 'Show confirmation dialog before adding coordinate fields to the layer',
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """Get a setting value for this action."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    def supports_undo(self) -> bool:
        """This action supports undo/redo by restoring feature backups and removing added fields."""
        return True

    def get_undo_category(self) -> str:
        """Return the undo category. We include payload backups for reliable redo support."""
        return 'payload'

    def get_undo_payload(self, context, execute_result=None):
        """Return the undo payload prepared during execute(). Called after successful commit."""
        try:
            if not hasattr(self, '_undo_payload'):
                return None
            return self._undo_payload
        except Exception:
            return None
    
    def execute(self, context):
        """Execute the add X/Y coordinate fields action."""
        # Get settings with proper type conversion
        try:
            confirm_before_adding = bool(self.get_setting('confirm_before_adding', True))
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
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Verify it's a point layer
        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.show_error("Error", "This action only works with point layers")
            return
        
        # Show coordinate fields dialog
        dialog = CoordinateFieldsDialog()
        if dialog.exec_() != QDialog.Accepted:
            return
        
        selected_fields = dialog.selected_fields
        if not selected_fields:
            self.show_warning("No Fields Selected", "No coordinate fields were selected to add.")
            return
        
        # Check for existing fields and create new ones
        fields_to_add = []
        field_formulas = {}
        
        for field_name, field_info in selected_fields.items():
            # Check if field already exists
            existing_field_index = layer.fields().indexOf(field_name)
            if existing_field_index >= 0:
                self.show_warning("Field Exists", f"Field '{field_name}' already exists in the layer. Skipping.")
                continue
            
            # Create new field
            field_type = field_info['type']
            
            # Convert QVariant to QMetaType
            if field_type == QVariant.Double:
                meta_type = QMetaType.Double
            else:
                meta_type = QMetaType.Double  # Default fallback
            
            new_field = QgsField(field_name, meta_type)
            fields_to_add.append(new_field)
            field_formulas[field_name] = field_info['formula']
        
        if not fields_to_add:
            self.show_warning("No New Fields", "No new coordinate fields to add (all selected fields already exist).")
            return
        
        # Confirm action if setting is enabled
        if confirm_before_adding:
            field_list = "\n".join([f"• {name}: {info['description']}" for name, info in selected_fields.items()])
            if not self.confirm_action(
                "Add Coordinate Fields",
                f"Are you sure you want to add {len(fields_to_add)} coordinate fields to layer '{layer.name()}'?\n\nSelected fields:\n{field_list}\n\nThis will modify the layer structure."
            ):
                return
        
        # Handle edit mode
        edit_result = self.handle_edit_mode(layer, "adding coordinate fields")
        if edit_result[0] is None:  # Error occurred
            return
        
        was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Create backups BEFORE changing anything so undo can restore original state
            features_before = []
            try:
                for f in layer.getFeatures():
                    features_before.append(self.create_feature_backup(f, layer))
            except Exception:
                features_before = []

            # Add fields to layer
            layer.dataProvider().addAttributes(fields_to_add)
            layer.updateFields()
            
            # Calculate field values directly
            try:
                total_features = layer.featureCount()
                if total_features == 0:
                    self.show_info("Success", f"Successfully added {len(fields_to_add)} coordinate fields to empty layer")
                    return
                
                # Create expressions for each field
                expressions = {}
                for field_name in field_formulas:
                    formula = field_formulas[field_name]
                    expressions[field_name] = QgsExpression(formula)
                    if expressions[field_name].hasParserError():
                        self.show_error("Error", f"Expression error for {field_name}: {expressions[field_name].parserErrorString()}")
                        return
                
                # Process each feature
                success_count = 0
                for i, feature in enumerate(layer.getFeatures()):
                    # Create expression context for this feature
                    context = QgsExpressionContext()
                    context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
                    context.setFeature(feature)
                    
                    # Calculate values for each selected field
                    for field_name in field_formulas:
                        expression = expressions[field_name]
                        expression.prepare(context)
                        value = expression.evaluate(context)
                        
                        # Handle different value types and set attribute
                        if value is None:
                            feature.setAttribute(field_name, None)
                        elif isinstance(value, (int, float)):
                            if math.isnan(value) or math.isinf(value):
                                feature.setAttribute(field_name, None)
                            else:
                                feature.setAttribute(field_name, value)
                        else:
                            feature.setAttribute(field_name, str(value))
                    
                    # Update the feature
                    if layer.updateFeature(feature):
                        success_count += 1
                
                self.show_info("Success", f"Successfully added {len(fields_to_add)} coordinate fields for {success_count}/{total_features} features")

                # After updating features, create backups for redo support
                features_after = []
                try:
                    for f in layer.getFeatures():
                        features_after.append(self.create_feature_backup(f, layer))
                except Exception:
                    features_after = []
                
            except Exception as calc_error:
                self.show_error("Error", f"Failed to calculate coordinate values: {str(calc_error)}")
                # Rollback field additions
                try:
                    field_indices = [layer.fields().indexOf(f.name()) for f in fields_to_add]
                    layer.dataProvider().deleteAttributes(field_indices)
                    layer.updateFields()
                except Exception as rollback_error:
                    self.show_warning("Rollback Warning", f"Could not rollback field additions: {str(rollback_error)}")
                return
            
            # Commit changes
            if not self.commit_changes(layer, "adding coordinate fields"):
                return
            # Prepare undo payload and record to history using composite pattern
            try:
                layer_desc = self.create_layer_descriptor(layer)

                # Build description of added fields for schema update handler
                added_fields_desc = []
                for nf in fields_to_add:
                    try:
                        qmeta = int(QMetaType.Double) if isinstance(nf.typeName(), str) else int(QMetaType.Double)
                    except Exception:
                        qmeta = int(QMetaType.Double)
                    added_fields_desc.append({
                        'name': nf.name(),
                        'qmeta_type': qmeta,
                        'length': None,
                        'precision': None
                    })

                # Build features history mapping old/new attribute values for the added fields
                # Create lookup maps by fid
                before_map = {fb.get('fid'): fb.get('attributes', {}) for fb in features_before}
                after_map = {fa.get('fid'): fa.get('attributes', {}) for fa in features_after}

                features_history = []
                # Iterate over feature ids present in before_map (stable ordering)
                for fid, attrs_before in before_map.items():
                    old_attrs = {}
                    new_attrs = {}
                    for fld in added_fields_desc:
                        fname = fld['name']
                        old_attrs[fname] = attrs_before.get(fname)
                        new_attrs[fname] = after_map.get(fid, {}).get(fname)

                    features_history.append({
                        'fid': fid,
                        'old_attributes': old_attrs,
                        'new_attributes': new_attrs
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
                        'features': features_history
                    }
                ]

                self.record_to_history(
                    description=f"Added {len(fields_to_add)} coordinate fields to layer '{layer.name()}'",
                    undo_type='composite',
                    can_undo=True,
                    undo_payload={'sub_operations': sub_operations},
                    layers=[layer_desc],
                    features=features_history
                )
            except Exception:
                # Non-fatal: history recording failure should not break the action
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to add coordinate fields: {str(e)}")
            self.rollback_changes(layer)
            
        finally:
            # Exit edit mode if we entered it
            self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
add_xy_coordinates_point_action = AddXYCoordinatesPointAction()
