"""
Add Area and Perimeter Fields to Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Adds calculated area and perimeter fields to polygon layers. Opens a dialog to select which fields to add,
then creates them with proper formulas and populates all features with calculated values.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
                                 QPushButton, QLabel, QScrollArea, QWidget)
from qgis.PyQt.QtCore import Qt, QMetaType
from qgis.core import (QgsField, QgsExpression, QgsExpressionContext,
                      QgsExpressionContextUtils, QgsWkbTypes)
from qgis.PyQt.QtCore import QVariant
import math


class FieldSelectionDialog(QDialog):
    """Dialog for selecting area and perimeter fields to add."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Area and Perimeter Fields")
        self.setModal(True)
        self.resize(400, 300)
        
        # Available fields - only area and perimeter
        self.available_fields = {
            "area": {
                "formula": "$area",
                "description": "Area of the polygon in layer CRS units",
                "type": QVariant.Double
            },
            "perimeter": {
                "formula": "$perimeter", 
                "description": "Perimeter of the polygon in layer CRS units",
                "type": QVariant.Double
            }
        }
        
        self.selected_fields = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Select area and perimeter fields to add:")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
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


class AddAreaPerimeterFieldsAction(BaseAction):
    """Action to add area and perimeter calculated fields to polygon layers."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "add_area_perimeter_fields_polygon"
        self.name = "Add Area & Perimeter Fields"
        self.category = "Analysis"
        self.description = "Add calculated area and perimeter fields to polygon layer. Opens dialog to select which fields to add, then creates them with proper formulas and populates all features with calculated values. Automatically handles edit mode."
        self.enabled = True
        
        # Action scoping - works on entire layers (affects all features in layer)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            'confirm_before_adding': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Adding Fields',
                'description': 'Show confirmation dialog before adding fields to the layer',
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """Get a setting value for this action."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def execute(self, context):
        """Execute the add area and perimeter fields action."""
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
        
        # Verify it's a polygon layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers")
            return
        
        # Show field selection dialog
        dialog = FieldSelectionDialog()
        if dialog.exec_() != QDialog.Accepted:
            return
        
        selected_fields = dialog.selected_fields
        if not selected_fields:
            self.show_warning("No Fields Selected", "No fields were selected to add.")
            return
        
        # Confirm action if setting is enabled
        if confirm_before_adding:
            field_list = "\n".join([f"• {name}: {info['description']}" for name, info in selected_fields.items()])
            if not self.confirm_action(
                "Add Area & Perimeter Fields",
                f"Are you sure you want to add {len(selected_fields)} calculated fields to layer '{layer.name()}'?\n\nSelected fields:\n{field_list}\n\nThis will modify the layer structure."
            ):
                return
        
        # Handle edit mode
        edit_result = self.handle_edit_mode(layer, "adding calculated fields")
        if edit_result[0] is None:  # Error occurred
            return
        
        was_in_edit_mode, edit_mode_entered = edit_result
        
        try:
            # Add fields to layer and prepare formulas
            fields_to_add = []
            field_formulas = {}
            fields_already_exist = []
            
            for field_name, field_info in selected_fields.items():
                # Check if field already exists
                existing_field_index = layer.fields().indexOf(field_name)
                if existing_field_index >= 0:
                    # Field exists - we'll recalculate values for it
                    fields_already_exist.append(field_name)
                    field_formulas[field_name] = field_info['formula']
                else:
                    # Field doesn't exist - create it
                    field_type = field_info['type']
                    
                    # Convert QVariant to QMetaType
                    if field_type == QVariant.Double:
                        meta_type = QMetaType.Double
                    elif field_type == QVariant.Int:
                        meta_type = QMetaType.Int
                    elif field_type == QVariant.LongLong:
                        meta_type = QMetaType.LongLong
                    elif field_type == QVariant.String:
                        meta_type = QMetaType.QString
                    else:
                        meta_type = QMetaType.Double  # Default fallback
                    
                    new_field = QgsField(field_name, meta_type)
                    fields_to_add.append(new_field)
                    field_formulas[field_name] = field_info['formula']
            
            # Add new fields to layer if any
            if fields_to_add:
                layer.dataProvider().addAttributes(fields_to_add)
                layer.updateFields()
            
            # Inform user if some fields already exist (but we'll still recalculate)
            if fields_already_exist:
                existing_fields_list = ", ".join(fields_already_exist)
                self.show_info("Recalculating Existing Fields", 
                    f"The following fields already exist and will be recalculated: {existing_fields_list}")
            
            # Calculate field values directly (more reliable than worker thread)
            try:
                total_features = layer.featureCount()
                if total_features == 0:
                    if fields_to_add:
                        self.show_info("Success", f"Successfully added {len(fields_to_add)} calculated fields to empty layer")
                    else:
                        self.show_info("Success", "Fields already exist in empty layer")
                    return
                
                # Create expressions for each field
                expressions = {}
                for field_name in field_formulas:
                    formula = field_formulas[field_name]
                    expressions[field_name] = QgsExpression(formula)
                    if expressions[field_name].hasParserError():
                        self.show_error("Error", f"Expression error for {field_name}: {expressions[field_name].parserErrorString()}")
                        return
                
                # Process each feature - recalculate values for ALL features
                success_count = 0
                for i, feature in enumerate(layer.getFeatures()):
                    # Create expressions for each field have been prepared above
                    feature_changes = []
                    for i, feature in enumerate(layer.getFeatures()):
                        # Capture old attribute values for all fields we'll modify
                        old_attrs = {}
                        new_attrs = {}
                        for field_name in field_formulas:
                            idx = layer.fields().indexOf(field_name)
                            if idx >= 0:
                                old_value = feature.attribute(idx)
                            else:
                                old_value = None
                            old_attrs[field_name] = old_value

                        # Create expression context for this feature
                        expr_context = QgsExpressionContext()
                        expr_context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
                        expr_context.setFeature(feature)

                        # Calculate values for each selected field (both new and existing)
                        for field_name in field_formulas:
                            expression = expressions[field_name]
                            expression.prepare(expr_context)
                            value = expression.evaluate(expr_context)

                            # Normalize value types
                            if value is None:
                                final_value = None
                            elif isinstance(value, (int, float)):
                                if math.isnan(value) or math.isinf(value):
                                    final_value = None
                                else:
                                    final_value = value
                            else:
                                final_value = str(value)

                            # Set on feature (by name is acceptable here)
                            feature.setAttribute(field_name, final_value)
                            new_attrs[field_name] = final_value

                        # Update the feature
                        if layer.updateFeature(feature):
                            success_count += 1
                            feature_changes.append({
                                'fid': int(feature.id()),
                                'old_attributes': old_attrs,
                                'new_attributes': new_attrs
                            })
                
                # Build success message
                new_fields_count = len(fields_to_add)
                recalculated_fields_count = len(fields_already_exist)
                
                if new_fields_count > 0 and recalculated_fields_count > 0:
                    success_message = f"Successfully added {new_fields_count} new field(s) and recalculated {recalculated_fields_count} existing field(s) for {success_count}/{total_features} features"
                elif new_fields_count > 0:
                    success_message = f"Successfully added {new_fields_count} calculated field(s) for {success_count}/{total_features} features"
                elif recalculated_fields_count > 0:
                    success_message = f"Successfully recalculated {recalculated_fields_count} field(s) for {success_count}/{total_features} features"
                else:
                    success_message = f"Processed {success_count}/{total_features} features"
                
                self.show_info("Success", success_message)
                
            except Exception as calc_error:
                self.show_error("Error", f"Failed to calculate field values: {str(calc_error)}")
                # Rollback only new field additions (don't delete existing fields)
                if fields_to_add:
                    try:
                        field_indices = [layer.fields().indexOf(f.name()) for f in fields_to_add]
                        # Filter out -1 indices (fields that weren't found)
                        field_indices = [idx for idx in field_indices if idx >= 0]
                        if field_indices:
                            layer.dataProvider().deleteAttributes(field_indices)
                            layer.updateFields()
                    except Exception as rollback_error:
                        self.show_warning("Rollback Warning", f"Could not rollback field additions: {str(rollback_error)}")
                return
            
                # Commit changes
            if not self.commit_changes(layer, "adding calculated fields"):
                return

            # Record history: composite entry with schema change (added fields)
            try:
                from ..undo_handlers import get_handler_registry
            except Exception:
                pass

            # Build created fields descriptors for undo/redo
            created_fields = []
            for f in fields_to_add:
                try:
                    created_fields.append({
                        'name': f.name(),
                        'qmeta_type': int(getattr(f, 'type', lambda: QMetaType.Double)()) if hasattr(f, 'type') else None,
                        'length': getattr(f, 'length', None)() if hasattr(f, 'length') and callable(getattr(f, 'length')) else None,
                        'precision': getattr(f, 'precision', None)() if hasattr(f, 'precision') and callable(getattr(f, 'precision')) else None
                    })
                except Exception:
                    created_fields.append({'name': f.name(), 'qmeta_type': None})

            # Compose sub-operations: original order (schema add, then attribute updates)
            sub_ops = []
            if created_fields:
                sub_ops.append({
                    'undo_type': 'update_schema',
                    'undo_payload': {
                        'added_fields': created_fields
                    },
                    'layers': [self.create_layer_descriptor(layer)],
                    'features': []
                })

            if feature_changes:
                sub_ops.append({
                    'undo_type': 'update_attributes',
                    'undo_payload': None,
                    'layers': [self.create_layer_descriptor(layer)],
                    'features': feature_changes
                })

            if sub_ops:
                # Record composite undo (can be undone by the composite handler)
                self.record_to_history(
                    description=f"Added {len(fields_to_add)} field(s) and updated attributes on layer '{layer.name()}'",
                    undo_type='composite',
                    can_undo=True,
                    undo_payload={'sub_operations': sub_ops},
                    layers=[self.create_layer_descriptor(layer)],
                    features=[]
                )
            
        except Exception as e:
            self.show_error("Error", f"Failed to add calculated fields: {str(e)}")
            self.rollback_changes(layer)
            
        finally:
            # Exit edit mode if we entered it
            self.exit_edit_mode(layer, edit_mode_entered)


# REQUIRED: Create global instance for automatic discovery
add_area_perimeter_fields_action = AddAreaPerimeterFieldsAction()
