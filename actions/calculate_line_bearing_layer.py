"""
Calculate Line Bearing/Azimuth for Layer Action for Right-click Utilities and Shortcuts Hub

Calculates and displays the bearing/azimuth for all line features in a layer.
For each line, calculates bearing from first to last vertex.
Shows bearing in degrees (0° = North, 90° = East, 180° = South, 270° = West).
Optionally stores calculated bearings in the attribute table.
"""

from .base_action import BaseAction
from qgis.core import QgsWkbTypes, QgsPointXY, QgsGeometry, QgsField
from qgis.PyQt.QtCore import QVariant, QMetaType
import math


class CalculateLineBearingLayerAction(BaseAction):
    """
    Action to calculate and display line bearing/azimuth for all features in a layer.
    
    This action calculates the bearing (azimuth) of all line features in a layer
    from their first vertex to their last vertex. Bearing is displayed in degrees
    with 0° = North, 90° = East, 180° = South, 270° = West.
    Optionally stores calculated bearings in the attribute table.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_line_bearing_layer"
        self.name = "Calculate Line Bearing/Azimuth for Layer"
        self.category = "Analysis"
        self.description = "Calculate and display the bearing/azimuth for all line features in the layer. For each line, calculates bearing from first to last vertex. Shows bearing in degrees (0° = North, 90° = East, 180° = South, 270° = West). Optionally stores calculated bearings in the attribute table. Works on selected features if any are selected, otherwise processes all features in the layer."
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
                'description': 'Number of decimal places to show in bearing calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_summary_statistics': {
                'type': 'bool',
                'default': True,
                'label': 'Show Summary Statistics',
                'description': 'Display summary statistics (count, min, max, average) in the result dialog',
            },
            'show_individual_results': {
                'type': 'bool',
                'default': False,
                'label': 'Show Individual Results',
                'description': 'Display bearing for each feature in the result dialog (may be long for large layers)',
            },
            'show_cardinal_direction': {
                'type': 'bool',
                'default': True,
                'label': 'Show Cardinal Direction',
                'description': 'Display cardinal direction (N, NE, E, SE, S, SW, W, NW) in addition to degrees',
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
                'description': 'Automatically add calculated bearings as a new column in the layer attribute table',
            },
            'result_field_name': {
                'type': 'str',
                'default': 'bearing',
                'label': 'Result Field Name',
                'description': 'Name of the field to store calculated bearings (max 10 chars for shapefiles)',
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
    
    def calculate_bearing(self, start_point, end_point):
        """
        Calculate bearing from start point to end point.
        
        Args:
            start_point (QgsPointXY): Starting point
            end_point (QgsPointXY): Ending point
            
        Returns:
            float: Bearing in degrees (0° = North, 90° = East, 180° = South, 270° = West)
        """
        # Calculate differences
        delta_x = end_point.x() - start_point.x()
        delta_y = end_point.y() - start_point.y()
        
        # Calculate bearing using atan2
        # atan2(delta_x, delta_y) gives angle from North (0° = North, 90° = East)
        bearing_rad = math.atan2(delta_x, delta_y)
        
        # Convert to degrees
        bearing_deg = math.degrees(bearing_rad)
        
        # Normalize to 0-360 range
        if bearing_deg < 0:
            bearing_deg += 360.0
        
        return bearing_deg
    
    def get_cardinal_direction(self, bearing):
        """
        Get cardinal direction from bearing.
        
        Args:
            bearing (float): Bearing in degrees
            
        Returns:
            str: Cardinal direction (N, NE, E, SE, S, SW, W, NW)
        """
        # Normalize bearing to 0-360
        bearing = bearing % 360.0
        
        # Determine cardinal direction
        if bearing >= 337.5 or bearing < 22.5:
            return "N"
        elif bearing >= 22.5 and bearing < 67.5:
            return "NE"
        elif bearing >= 67.5 and bearing < 112.5:
            return "E"
        elif bearing >= 112.5 and bearing < 157.5:
            return "SE"
        elif bearing >= 157.5 and bearing < 202.5:
            return "S"
        elif bearing >= 202.5 and bearing < 247.5:
            return "SW"
        elif bearing >= 247.5 and bearing < 292.5:
            return "W"
        else:  # 292.5 to 337.5
            return "NW"
    
    def calculate_feature_bearing(self, feature):
        """
        Calculate bearing for a single line feature.
        
        Args:
            feature (QgsFeature): Line feature
            
        Returns:
            float or None: Bearing in degrees, or None if calculation failed
        """
        try:
            geometry = feature.geometry()
            if not geometry:
                return None
            
            # Validate that this is a line feature
            if geometry.type() != QgsWkbTypes.LineGeometry:
                return None
            
            # Get vertices of the line and convert to QgsPointXY
            vertices = geometry.vertices()
            vertex_list = []
            for vertex in vertices:
                # Convert QgsPoint to QgsPointXY
                vertex_list.append(QgsPointXY(vertex.x(), vertex.y()))
            
            if len(vertex_list) < 2:
                return None
            
            # Calculate bearing from first to last vertex
            start_point = vertex_list[0]
            end_point = vertex_list[-1]
            
            bearing = self.calculate_bearing(start_point, end_point)
            return bearing
            
        except Exception:
            return None
    
    def execute(self, context):
        """
        Execute the calculate line bearing for layer action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_summary = bool(self.get_setting('show_summary_statistics', True))
            show_individual = bool(self.get_setting('show_individual_results', False))
            show_cardinal = bool(self.get_setting('show_cardinal_direction', True))
            show_crs_info = bool(self.get_setting('show_crs_info', False))
            process_selected_only = bool(self.get_setting('process_selected_only', False))
            show_success_message = bool(self.get_setting('show_success_message', True))
            store_in_table = bool(self.get_setting('store_in_attribute_table', False))
            field_name = str(self.get_setting('result_field_name', 'bearing'))
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
            
            # Calculate bearings for all features
            results = []  # List of dicts: [{'feature_id': int, 'value': bearing}, ...]
            valid_bearings = []  # For statistics
            
            processed_count = 0
            failed_count = 0
            
            for feature in features_to_process:
                # Skip invalid features
                if not feature.isValid():
                    failed_count += 1
                    continue
                
                # Calculate bearing
                bearing = self.calculate_feature_bearing(feature)
                
                if bearing is not None:
                    results.append({
                        'feature_id': feature.id(),
                        'value': bearing
                    })
                    valid_bearings.append(bearing)
                    processed_count += 1
                else:
                    failed_count += 1
            
            if processed_count == 0:
                self.show_warning("Warning", "No valid line features found to process")
                return
            
            # Calculate summary statistics
            if valid_bearings:
                min_bearing = min(valid_bearings)
                max_bearing = max(valid_bearings)
                avg_bearing = sum(valid_bearings) / len(valid_bearings)
            else:
                min_bearing = max_bearing = avg_bearing = 0.0
            
            # Build result message
            result_lines = []
            result_lines.append(f"Layer: {layer.name()}")
            result_lines.append(f"Features Processed: {processed_count}")
            if failed_count > 0:
                result_lines.append(f"Features Failed: {failed_count}")
            result_lines.append(f"Processing Mode: {processing_mode}")
            result_lines.append("")
            
            if show_summary and valid_bearings:
                result_lines.append("Summary Statistics:")
                result_lines.append(f"  Minimum Bearing: {min_bearing:.{decimal_places}f}°")
                if show_cardinal:
                    result_lines.append(f"    Direction: {self.get_cardinal_direction(min_bearing)}")
                result_lines.append(f"  Maximum Bearing: {max_bearing:.{decimal_places}f}°")
                if show_cardinal:
                    result_lines.append(f"    Direction: {self.get_cardinal_direction(max_bearing)}")
                result_lines.append(f"  Average Bearing: {avg_bearing:.{decimal_places}f}°")
                if show_cardinal:
                    result_lines.append(f"    Direction: {self.get_cardinal_direction(avg_bearing)}")
                result_lines.append("")
            
            if show_individual:
                result_lines.append("Individual Results:")
                for result_data in results[:100]:  # Limit to first 100 for display
                    feature_id = result_data['feature_id']
                    bearing = result_data['value']
                    bearing_formatted = f"{bearing:.{decimal_places}f}°"
                    line = f"  Feature ID {feature_id}: {bearing_formatted}"
                    if show_cardinal:
                        line += f" ({self.get_cardinal_direction(bearing)})"
                    result_lines.append(line)
                
                if len(results) > 100:
                    result_lines.append(f"  ... and {len(results) - 100} more features")
                result_lines.append("")
            
            if show_crs_info:
                crs = layer.crs()
                result_lines.append(f"CRS: {crs.description()}")
            
            result_text = "\n".join(result_lines)
            
            # Show result
            self.show_info("Bearing/Azimuth Calculation for Layer", result_text)
            
            # Record informational history when not storing results to table
            try:
                if not store_in_table:
                    from ..history_manager import get_history_manager
                    hm = get_history_manager()
                    meta_info = {
                        'processed_count': int(processed_count),
                        'failed_count': int(failed_count),
                        'processing_mode': processing_mode
                    }
                    description = f"Calculated bearings for layer {layer.name()} ({processed_count} processed, {failed_count} failed)"
                    hm.record_informational(self.action_id, self.name, description, meta=meta_info)
            except Exception:
                pass
            
            # OPTIONAL: Store in attribute table if setting enabled
            if store_in_table and results:
                try:
                    # Handle edit mode
                    edit_result = self.handle_edit_mode(layer, "storing calculated bearings")
                    if edit_result[0] is None:  # Error occurred
                        self.show_warning("Warning", "Could not enter edit mode. Values will not be stored in attribute table.")
                    else:
                        was_in_edit_mode, edit_mode_entered = edit_result
                        
                        try:
                            # Step 1: Create field with appropriate type
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
                                # Step 5: Update features with calculated values
                                updated_count = 0
                                failed_update_count = 0
                                
                                # Prepare feature backups for history (old/new attribute values)
                                features_backup = []

                                for result_data in results:
                                    feature_id = result_data['feature_id']
                                    value = result_data['value']
                                    
                                    # Get feature by ID (more reliable than iterating)
                                    feature = layer.getFeature(feature_id)
                                    if not feature.isValid():
                                        failed_update_count += 1
                                        continue
                                    
                                    # Handle None values and type conversion
                                    # Capture old and new attribute values for history
                                    old_value = feature.attribute(field_idx)
                                    if value is None:
                                        new_value = None
                                        feature.setAttribute(field_idx, None)
                                    else:
                                        # Round float values to avoid precision issues
                                        if abs(value) < 0.000001 and value != 0.0:
                                            new_value = round(value, 12)
                                        else:
                                            new_value = round(value, 10)
                                        feature.setAttribute(field_idx, new_value)

                                    features_backup.append({
                                        'fid': int(feature_id),
                                        'old_attributes': {field_name: old_value},
                                        'new_attributes': {field_name: new_value}
                                    })
                                    
                                    # Update the feature
                                    if layer.updateFeature(feature):
                                        updated_count += 1
                                    else:
                                        failed_update_count += 1
                                
                                if updated_count == 0 and failed_update_count > 0:
                                    self.show_warning("Warning", f"Could not update any features. {failed_update_count} features failed to update.")
                                
                                # Step 6: Commit changes
                                if self.commit_changes(layer, "storing calculated bearings"):
                                    # CRITICAL: Trigger layer refresh to update attribute table display
                                    layer.triggerRepaint()
                                    
                                    if field_idx >= 0 and updated_count > 0:
                                        self.show_info("Success", f"Stored bearings in field '{field_name}' ({updated_count} features updated)")

                                        # Record undoable history entry.
                                        # If we created the field(s) as part of this action, record a composite
                                        # sub-operation so undo will remove the added field(s) as well.
                                        try:
                                            from ..history_manager import get_history_manager
                                            hm = get_history_manager()
                                            layer_desc = hm.create_layer_descriptor(layer)
                                            description = f"Stored calculated bearings in field '{field_name}' on layer {layer.name()} ({updated_count} features updated)"

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
                                                        'features': features_backup
                                                    }
                                                ]

                                                hm.record(
                                                    action_id=self.action_id,
                                                    action_name=self.name,
                                                    description=description,
                                                    undo_type='composite',
                                                    can_undo=True,
                                                    undo_payload={'sub_operations': sub_operations},
                                                    layers=[layer_desc],
                                                    features=features_backup,
                                                    atomic=True,
                                                    meta={'field_name': field_name, 'processing_mode': processing_mode, 'updated_count': updated_count}
                                                )
                                            else:
                                                # No schema change; simple attribute update
                                                hm.record(
                                                    action_id=self.action_id,
                                                    action_name=self.name,
                                                    description=description,
                                                    undo_type='update_attributes',
                                                    can_undo=True,
                                                    undo_payload=None,
                                                    redo_payload=None,
                                                    layers=[layer_desc],
                                                    features=features_backup,
                                                    atomic=True,
                                                    meta={'field_name': field_name, 'processing_mode': processing_mode, 'updated_count': updated_count}
                                                )
                                        except Exception:
                                            pass
                        
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
                self.show_info("Success", f"Bearing calculated for {processed_count} feature(s)")
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate bearings: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_line_bearing_layer = CalculateLineBearingLayerAction()

