"""
Calculate Line Length for Layer Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the length for all line features in a layer.
Shows length in appropriate units based on layer CRS.
Optionally stores calculated lengths in the attribute table.
"""

from .base_action import BaseAction
from qgis.core import QgsWkbTypes, QgsField
from qgis.PyQt.QtCore import QVariant, QMetaType


class CalculateLineLengthLayerAction(BaseAction):
    """
    Action to calculate and display line length for all features in a layer.
    
    This action calculates the length of all line features in a layer.
    Length is displayed in appropriate units based on layer CRS.
    Optionally stores calculated lengths in the attribute table.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_line_length_layer"
        self.name = "Calculate Line Length for Layer"
        self.category = "Analysis"
        self.description = "Calculate and display the length for all line features in the layer. Shows length in appropriate units based on layer CRS. Optionally stores calculated lengths in the attribute table. Works on selected features if any are selected, otherwise processes all features in the layer."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # DISPLAY SETTINGS - Easy to customize output format
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in length calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_summary_statistics': {
                'type': 'bool',
                'default': True,
                'label': 'Show Summary Statistics',
                'description': 'Display summary statistics (count, min, max, average, total) in the result dialog',
            },
            'show_individual_results': {
                'type': 'bool',
                'default': False,
                'label': 'Show Individual Results',
                'description': 'Display length for each feature in the result dialog (may be long for large layers)',
            },
            'show_units': {
                'type': 'bool',
                'default': True,
                'label': 'Show Units',
                'description': 'Display units (meters, feet, degrees, etc.) in the result dialog',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result dialog',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'process_selected_only': {
                'type': 'bool',
                'default': False,
                'label': 'Process Selected Features Only',
                'description': 'If checked, only processes selected features. If unchecked, processes all features in the layer.',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a brief success message after calculation',
            },
            
            # ATTRIBUTE TABLE SETTINGS - Store results in attribute table
            'store_in_attribute_table': {
                'type': 'bool',
                'default': False,
                'label': 'Store in Attribute Table',
                'description': 'Automatically add calculated lengths as a new column in the layer attribute table',
            },
            'result_field_name': {
                'type': 'str',
                'default': 'length',
                'label': 'Result Field Name',
                'description': 'Name of the field to store calculated lengths (max 10 chars for shapefiles)',
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """
        Get a setting value for this action.
        
        Args:
            setting_name (str): Name of the setting to retrieve
            default_value: Default value if setting not found
            
        Returns:
            Setting value or default_value
        """
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def calculate_feature_length(self, feature):
        """
        Calculate length for a single line feature.
        
        Args:
            feature (QgsFeature): Line feature
            
        Returns:
            float or None: Length in map units, or None if calculation failed
        """
        try:
            geometry = feature.geometry()
            if not geometry:
                return None
            
            # Validate that this is a line feature
            if geometry.type() != QgsWkbTypes.LineGeometry:
                return None
            
            # Calculate length
            length = geometry.length()
            return length
            
        except Exception:
            return None
    
    def execute(self, context):
        """
        Execute the calculate line length for layer action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_summary = bool(self.get_setting('show_summary_statistics', True))
            show_individual = bool(self.get_setting('show_individual_results', False))
            show_units = bool(self.get_setting('show_units', True))
            show_crs_info = bool(self.get_setting('show_crs_info', False))
            process_selected_only = bool(self.get_setting('process_selected_only', False))
            show_success_message = bool(self.get_setting('show_success_message', True))
            store_in_table = bool(self.get_setting('store_in_attribute_table', False))
            field_name = str(self.get_setting('result_field_name', 'length'))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract layer from context
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No line features found at this location")
            return
        
        # Get the layer from the first detected feature
        layer = detected_features[0].layer
        
        # Validate layer type
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.show_error("Error", "This action only works with line layers")
            return
        
        try:
            # Determine which features to process
            if process_selected_only and layer.selectedFeatureCount() > 0:
                features_to_process = layer.selectedFeatures()
                processing_mode = "selected"
            else:
                features_to_process = layer.getFeatures()
                processing_mode = "all"
            
            # Calculate lengths for all features
            results = []  # List of dicts: [{'feature_id': int, 'value': length}, ...]
            valid_lengths = []  # For statistics
            
            processed_count = 0
            failed_count = 0
            
            for feature in features_to_process:
                # Skip invalid features
                if not feature.isValid():
                    failed_count += 1
                    continue
                
                # Calculate length
                length = self.calculate_feature_length(feature)
                
                if length is not None:
                    results.append({
                        'feature_id': feature.id(),
                        'value': length
                    })
                    valid_lengths.append(length)
                    processed_count += 1
                else:
                    failed_count += 1
            
            if processed_count == 0:
                self.show_warning("Warning", "No valid line features found to process")
                return
            
            # Calculate summary statistics
            if valid_lengths:
                min_length = min(valid_lengths)
                max_length = max(valid_lengths)
                avg_length = sum(valid_lengths) / len(valid_lengths)
                total_length = sum(valid_lengths)
            else:
                min_length = max_length = avg_length = total_length = 0.0
            
            # Get unit information
            unit_name = "units"
            if show_units:
                crs = layer.crs()
                if crs.isGeographic():
                    unit_name = "degrees"
                else:
                    # For projected CRS, get the map units
                    try:
                        unit_name = crs.mapUnits().name().lower()
                    except:
                        unit_name = "map units"
            
            # Build result message
            result_lines = []
            result_lines.append(f"Layer: {layer.name()}")
            result_lines.append(f"Features Processed: {processed_count}")
            if failed_count > 0:
                result_lines.append(f"Features Failed: {failed_count}")
            result_lines.append(f"Processing Mode: {processing_mode}")
            result_lines.append("")
            
            if show_summary and valid_lengths:
                result_lines.append("Summary Statistics:")
                result_lines.append(f"  Minimum Length: {min_length:.{decimal_places}f} {unit_name}")
                result_lines.append(f"  Maximum Length: {max_length:.{decimal_places}f} {unit_name}")
                result_lines.append(f"  Average Length: {avg_length:.{decimal_places}f} {unit_name}")
                result_lines.append(f"  Total Length: {total_length:.{decimal_places}f} {unit_name}")
                result_lines.append("")
            
            if show_individual:
                result_lines.append("Individual Results:")
                for result_data in results[:100]:  # Limit to first 100 for display
                    feature_id = result_data['feature_id']
                    length = result_data['value']
                    length_formatted = f"{length:.{decimal_places}f}"
                    line = f"  Feature ID {feature_id}: {length_formatted}"
                    if show_units:
                        line += f" {unit_name}"
                    result_lines.append(line)
                
                if len(results) > 100:
                    result_lines.append(f"  ... and {len(results) - 100} more features")
                result_lines.append("")
            
            if show_crs_info:
                crs = layer.crs()
                result_lines.append(f"CRS: {crs.description()}")
            
            result_text = "\n".join(result_lines)
            
            # Show result
            self.show_info("Length Calculation for Layer", result_text)
            
            # OPTIONAL: Store in attribute table if setting enabled
            if store_in_table and results:
                try:
                    # Handle edit mode
                    edit_result = self.handle_edit_mode(layer, "storing calculated lengths")
                    if edit_result[0] is None:  # Error occurred
                        self.show_warning("Warning", "Could not enter edit mode. Values will not be stored in attribute table.")
                    else:
                        was_in_edit_mode, edit_mode_entered = edit_result
                        
                        try:
                            # Step 1: Create field with appropriate type (Double for length)
                            # Use QMetaType instead of QVariant to avoid deprecation warning
                            new_field = QgsField(field_name, QMetaType.Double)
                            new_field.setPrecision(10)  # Avoid scientific notation
                            new_field.setLength(20)     # Display length
                            
                            # Step 2: Check if field exists, create if needed
                            fields_to_add = []
                            fields = layer.fields()
                            
                            if fields.indexOf(field_name) == -1:
                                # Field doesn't exist, add it to list
                                fields_to_add.append(new_field)
                            
                            # Step 3: Add fields if any were created
                            if fields_to_add:
                                # CRITICAL: Use dataProvider().addAttributes() (plural), not addAttribute()
                                result = layer.dataProvider().addAttributes(fields_to_add)
                                if not result:
                                    self.show_warning("Warning", f"Failed to add field: {field_name}")
                                # CRITICAL: Always update fields after adding (even if it failed)
                                layer.updateFields()
                            
                            # Step 4: Get field index (handle name truncation for shapefiles)
                            # CRITICAL: Refresh fields before getting index
                            layer.updateFields()
                            fields = layer.fields()
                            field_idx = fields.indexOf(field_name)
                            
                            # Fallback: Try case-insensitive and prefix matching (for truncated names)
                            if field_idx == -1:
                                # Try case-insensitive search
                                for i, field in enumerate(fields):
                                    if field.name().lower() == field_name.lower():
                                        field_idx = i
                                        field_name = field.name()  # Use actual name
                                        break
                                # If still not found, try prefix match (shapefiles truncate to 10 chars)
                                if field_idx == -1:
                                    for i, field in enumerate(fields):
                                        if field.name().lower().startswith(field_name.lower()[:8]):
                                            field_idx = i
                                            field_name = field.name()  # Use actual truncated name
                                            break
                            
                            if field_idx == -1:
                                all_field_names = [f.name() for f in fields]
                                self.show_warning("Warning", f"Could not find field '{field_name}' after adding it. Available fields: {', '.join(all_field_names[:10])}")
                            else:
                                # Step 5: Prepare backups and update features with calculated values
                                updated_count = 0
                                failed_update_count = 0

                                # Prepare a list of feature-level backups for undo/redo
                                features_backups = []

                                for result_data in results:
                                    feature_id = result_data['feature_id']
                                    value = result_data['value']

                                    # Get feature by ID (more reliable than iterating)
                                    feature = layer.getFeature(feature_id)
                                    if not feature.isValid():
                                        failed_update_count += 1
                                        continue

                                    # Read original attribute value for backup
                                    try:
                                        orig_value = feature.attribute(field_idx)
                                        # Convert QVariant-like objects to JSON-serializable types
                                        if hasattr(orig_value, 'isNull') and orig_value.isNull():
                                            orig_value_serial = None
                                        else:
                                            orig_value_serial = orig_value
                                    except Exception:
                                        orig_value_serial = None

                                    # Prepare new value (rounded) for storing
                                    new_value = None
                                    if value is None:
                                        new_value = None
                                    else:
                                        try:
                                            if abs(value) < 0.000001 and value != 0.0:
                                                nv = round(value, 12)
                                            else:
                                                nv = round(value, 10)
                                            new_value = nv
                                        except Exception:
                                            new_value = value

                                    # Record backup entry for this feature
                                    features_backups.append({
                                        'fid': int(feature_id),
                                        'old_attributes': {fields[field_idx].name(): orig_value_serial},
                                        'new_attributes': {fields[field_idx].name(): new_value}
                                    })

                                    # Apply the new value to the feature
                                    try:
                                        feature.setAttribute(field_idx, new_value)
                                    except Exception:
                                        # Fallback: try setting by field name
                                        try:
                                            fname = fields[field_idx].name()
                                            feature.setAttribute(fname, new_value)
                                        except Exception:
                                            failed_update_count += 1
                                            continue

                                    # Update the feature
                                    if layer.updateFeature(feature):
                                        updated_count += 1
                                    else:
                                        failed_update_count += 1

                                if updated_count == 0 and failed_update_count > 0:
                                    self.show_warning("Warning", f"Could not update any features. {failed_update_count} features failed to update.")

                                # Step 6: Commit changes
                                if self.commit_changes(layer, "storing calculated lengths"):
                                    # CRITICAL: Trigger layer refresh to update attribute table display
                                    layer.triggerRepaint()

                                    if field_idx >= 0 and updated_count > 0:
                                        # Record undoable history entry for attribute updates
                                        try:
                                            from ..history_manager import get_history_manager
                                            hm = get_history_manager()

                                            # Use history manager helper to create layer descriptor
                                            layer_desc = hm.create_layer_descriptor(layer)
                                            description_store = f"Stored lengths in field '{field_name}' ({updated_count} features updated)"

                                            if fields_to_add:
                                                # Build added_fields_desc similar to other actions
                                                added_fields_desc = []

                                                for nf in fields_to_add:
                                                    try:
                                                        qmeta = int(QMetaType.Double)
                                                    except Exception:
                                                        qmeta = 0
                                                    added_fields_desc.append({
                                                        'name': nf.name(),
                                                        'qmeta_type': qmeta,
                                                        'length': getattr(nf, 'length', None),
                                                        'precision': getattr(nf, 'precision', None)
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
                                                        'features': features_backups
                                                    }
                                                ]

                                                hm.record(
                                                    action_id=self.action_id,
                                                    action_name=self.name,
                                                    description=description_store,
                                                    undo_type='composite',
                                                    can_undo=True,
                                                    undo_payload={'sub_operations': sub_operations},
                                                    layers=[layer_desc],
                                                    features=features_backups,
                                                    atomic=True,
                                                    meta={'field_name': field_name, 'processing_mode': processing_mode, 'updated_count': updated_count}
                                                )
                                            else:
                                                # No schema change; simple attribute update
                                                hm.record(
                                                    action_id=self.action_id,
                                                    action_name=self.name,
                                                    description=description_store,
                                                    undo_type='update_attributes',
                                                    can_undo=True,
                                                    undo_payload=None,
                                                    redo_payload=None,
                                                    layers=[layer_desc],
                                                    features=features_backups,
                                                    atomic=True,
                                                    meta={'field_name': field_name, 'processing_mode': processing_mode, 'updated_count': updated_count}
                                                )
                                        except Exception:
                                            self.show_warning("Warning", "Failed to record undo information for stored lengths")

                                        self.show_info("Success", f"Stored lengths in field '{field_name}' ({updated_count} features updated)")
                        
                        except Exception as store_error:
                            self.show_warning("Warning", f"Failed to store data in attribute table: {str(store_error)}")
                            self.rollback_changes(layer)
                        finally:
                            # Exit edit mode if we entered it
                            self.exit_edit_mode(layer, edit_mode_entered)
                
                except Exception as e:
                    self.show_warning("Warning", f"Failed to store data in attribute table: {str(e)}")
            
            # Show success message if requested
            if show_success_message:
                total_formatted = f"{total_length:.{decimal_places}f}"
                self.show_info("Success", f"Length calculated for {processed_count} feature(s). Total length: {total_formatted} {unit_name}")
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate lengths: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_line_length_layer = CalculateLineLengthLayerAction()

