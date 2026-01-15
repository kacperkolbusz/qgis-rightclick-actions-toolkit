"""
Split Point Layer by Attribute Action for Right-click Utilities and Shortcuts Hub

Splits a point layer into multiple layers based on a selected attribute field.
Each unique value in the selected attribute creates a new layer with all features
having that value. All other attribute fields are preserved in the split layers.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsFields, QgsField, QgsProject,
    QgsWkbTypes, QgsVectorFileWriter, QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QInputDialog, QMessageBox, QDialog, QVBoxLayout, 
    QLabel, QCheckBox, QPushButton, QHBoxLayout, QApplication
)
import os
import time
import stat


class SplitPointLayerByAttributeAction(BaseAction):
    """Action to split a point layer into multiple layers based on an attribute field."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "split_point_layer_by_attribute"
        self.name = "Split Layer by Attribute"
        self.category = "Editing"
        self.description = "Split a point layer into multiple layers based on a selected attribute field. Each unique value creates a new layer containing all features with that value. All other attribute fields are preserved in the split layers."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with point layers
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'default': '{original_layer_name}_{attribute_value}',
                'label': 'Layer Name Template',
                'description': 'Template for new layer names. Available variables: {original_layer_name}, {attribute_value}, {attribute_field}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add Layers to Project',
                'description': 'Automatically add the split layers to the QGIS project',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when splitting is completed successfully',
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
    
    def execute(self, context):
        """Execute the split point layer by attribute action."""
        try:
            # Get settings with proper type conversion
            try:
                schema = self.get_settings_schema()
                layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
                layer_name_template = str(self.get_setting('layer_name_template', schema['layer_name_template']['default']))
                add_to_project = bool(self.get_setting('add_to_project', schema['add_to_project']['default']))
                show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
            except (ValueError, TypeError) as e:
                self.show_error("Error", f"Invalid setting values: {str(e)}")
                return
            
            # Extract context elements
            detected_features = context.get('detected_features', [])
            
            if not detected_features:
                self.show_error("Error", "No features found at this location")
                return
            
            # Get the layer from the first detected feature
            detected_feature = detected_features[0]
            layer = detected_feature.layer
            
            if not layer or not layer.isValid():
                self.show_error("Error", "Invalid layer")
                return
            
            # Check if layer has point features
            if layer.geometryType() != QgsWkbTypes.PointGeometry:
                self.show_error("Error", "This action only works with point layers")
                return
            
            # Get all fields from the layer
            fields = layer.fields()
            if fields.count() == 0:
                self.show_error("Error", "Layer has no attribute fields")
                return
            
            # Get field names (excluding geometry and FID fields)
            field_names = []
            for field in fields:
                field_name = field.name()
                # Skip system fields
                if field_name.lower() not in ['fid', 'id', 'geometry']:
                    field_names.append(field_name)
            
            if not field_names:
                self.show_error("Error", "No suitable attribute fields found in the layer")
                return
            
            # Prompt user to select attribute field
            selected_field, ok = QInputDialog.getItem(
                None,
                "Select Attribute Field",
                "Choose the attribute field to split by:",
                field_names,
                0,  # Default to first field
                False  # Not editable
            )
            
            if not ok or not selected_field:
                return  # User cancelled
            
            # Find the selected field
            split_field = None
            split_field_index = -1
            for i, field in enumerate(fields):
                if field.name() == selected_field:
                    split_field = field
                    split_field_index = i
                    break
            
            if split_field is None:
                self.show_error("Error", f"Could not find field '{selected_field}'")
                return
            
            # Get all features and collect unique values
            features = list(layer.getFeatures())
            if not features:
                self.show_error("Error", "Layer has no features")
                return
            
            # Collect unique values and group features by value
            unique_values = {}
            for feature in features:
                attributes = feature.attributes()
                if split_field_index < len(attributes):
                    value = attributes[split_field_index]
                    # Convert None to string for grouping
                    if value is None:
                        value_str = "NULL"
                    else:
                        value_str = str(value)
                    
                    if value_str not in unique_values:
                        unique_values[value_str] = []
                    unique_values[value_str].append(feature)
            
            # Check if we have unique values
            if not unique_values:
                self.show_error("Error", "No values found in the selected attribute field")
                return
            
            num_layers = len(unique_values)
            
            # Show preview of unique values and ask for confirmation with delete option
            preview_text = f"Layer will be split into {num_layers} layers based on '{selected_field}':\n\n"
            for value_str, feature_list in sorted(unique_values.items()):
                preview_text += f"  • {value_str}: {len(feature_list)} feature(s)\n"
            
            preview_text += f"\nTotal features: {len(features)}"
            
            # Create custom dialog with checkbox for deleting original layer
            dialog = QDialog(None)
            dialog.setWindowTitle("Confirm Split")
            dialog.setMinimumWidth(400)
            
            layout = QVBoxLayout()
            dialog.setLayout(layout)
            
            # Preview text label
            preview_label = QLabel(preview_text)
            preview_label.setWordWrap(True)
            layout.addWidget(preview_label)
            
            # Checkbox for deleting original layer
            delete_checkbox = QCheckBox(f"Delete original layer '{layer.name()}' and all associated files after split")
            delete_checkbox.setChecked(False)
            layout.addWidget(delete_checkbox)
            
            # Buttons
            button_layout = QHBoxLayout()
            yes_button = QPushButton("Yes")
            no_button = QPushButton("No")
            yes_button.clicked.connect(dialog.accept)
            no_button.clicked.connect(dialog.reject)
            button_layout.addWidget(yes_button)
            button_layout.addWidget(no_button)
            layout.addLayout(button_layout)
            
            # Show dialog
            if dialog.exec_() != QDialog.Accepted:
                return  # User cancelled
            
            # Get user's choice about deleting original layer
            delete_original = delete_checkbox.isChecked()
            
            # Check layer storage type setting
            create_permanent = (layer_storage_type == 'permanent')
            
            # Get original layer source and format for deletion purposes (if needed)
            actual_source = None
            original_file_format = None
            if delete_original:
                layer_source = layer.source()
                if layer_source and not layer_source.startswith('memory:'):
                    if layer_source.startswith('ogr:'):
                        parts = layer_source.split('|')
                        if parts:
                            file_part = parts[0].replace('ogr:', '')
                            if file_part and os.path.exists(file_part):
                                actual_source = file_part
                    else:
                        actual_source = layer_source.split('|')[0] if '|' in layer_source else layer_source
                    
                    # Determine original file format for deletion
                    if actual_source:
                        source_lower = actual_source.lower()
                        if source_lower.endswith('.gpkg') or 'gpkg' in source_lower:
                            original_file_format = "GPKG"
                        elif source_lower.endswith('.geojson') or source_lower.endswith('.json'):
                            original_file_format = "GeoJSON"
                        elif source_lower.endswith('.shp'):
                            original_file_format = "ESRI Shapefile"
                        elif source_lower.endswith('.kml'):
                            original_file_format = "KML"
                        elif source_lower.endswith('.kmz'):
                            original_file_format = "KMZ"
                        else:
                            original_file_format = "ESRI Shapefile"  # Default
            
            # Only check for file-based source if creating permanent layers
            file_format = None
            file_extension = None
            layer_dir = None
            
            if create_permanent:
                # Prompt user for save directory
                from qgis.PyQt.QtWidgets import QFileDialog
                layer_dir = QFileDialog.getExistingDirectory(
                    None, "Select Directory to Save Split Layers", ""
                )
                if not layer_dir:
                    return  # User cancelled
                
                # Determine file format (default to GeoPackage for split layers)
                file_format = "GPKG"
                file_extension = ".gpkg"
            
            
            # Create new layers for each unique value
            original_layer_name = layer.name()
            created_layers = []
            project = QgsProject.instance()
            geometry_type = layer.wkbType()
            crs = layer.crs()
            
            for value_str, feature_list in sorted(unique_values.items()):
                try:
                    # Create layer name with sanitized values
                    sanitized_value = value_str.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                    sanitized_field = selected_field.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                    sanitized_layer_name = original_layer_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                    
                    layer_name = layer_name_template.format(
                        original_layer_name=sanitized_layer_name,
                        attribute_value=sanitized_value,
                        attribute_field=sanitized_field
                    )
                    
                    # Create temporary memory layer
                    temp_layer = QgsVectorLayer(
                        f"Point?crs={crs.authid()}",
                        layer_name,
                        "memory"
                    )
                    
                    if not temp_layer.isValid():
                        raise Exception("Failed to create temporary layer")
                    
                    # Add fields
                    temp_layer.dataProvider().addAttributes(fields.toList())
                    temp_layer.updateFields()
                    
                    # Add features
                    temp_layer.dataProvider().addFeatures(feature_list)
                    temp_layer.updateExtents()
                    
                    if create_permanent:
                        # Create file path
                        file_name = layer_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                        file_path = os.path.join(layer_dir, file_name + file_extension)
                        
                        # Write to file
                        options = QgsVectorFileWriter.SaveVectorOptions()
                        options.driverName = file_format
                        options.fileEncoding = "UTF-8"
                        
                        # For GeoPackage, specify layer name
                        if file_format == "GPKG":
                            options.layerName = layer_name
                        
                        error_code, error_message = QgsVectorFileWriter.writeAsVectorFormat(
                            temp_layer,
                            file_path,
                            options
                        )
                        
                        if error_code != QgsVectorFileWriter.NoError:
                            raise Exception(f"Failed to write file: {error_message}")
                        
                        # Load the file-based layer
                        new_layer = QgsVectorLayer(file_path, layer_name, "ogr")
                        if not new_layer.isValid():
                            raise Exception("Failed to load created layer file")
                    else:
                        # Use the temporary memory layer directly
                        new_layer = temp_layer
                    
                    # Add to project if enabled
                    if add_to_project:
                        project.addMapLayer(new_layer)
                    
                    created_layers.append((new_layer, value_str, len(feature_list)))
                    
                except Exception as e:
                    self.show_error("Error", f"Failed to create layer for value '{value_str}': {str(e)}")
                    continue
            
            # Delete original layer and files if requested
            if delete_original and created_layers:
                try:
                    # Store layer ID and source before removal
                    layer_id = layer.id()
                    
                    # Try to close the layer's data provider explicitly
                    try:
                        if layer.dataProvider():
                            layer.dataProvider().close()
                    except:
                        pass
                    
                    # Remove layer from project
                    project.removeMapLayer(layer_id)
                    
                    # Force garbage collection to release file handles
                    import gc
                    gc.collect()
                    
                    # Process events and wait to ensure file handles are released
                    QApplication.processEvents()
                    time.sleep(0.2)  # 200ms delay to ensure files are released
                    QApplication.processEvents()
                    time.sleep(0.1)  # Additional 100ms delay
                    QApplication.processEvents()
                    
                    # Delete all associated files
                    deleted_success, failed_files = self._delete_layer_files(actual_source, original_file_format)
                    
                    # Check for critical files that couldn't be deleted (.shp and .dbf)
                    critical_failed = []
                    if failed_files:
                        for failed_file in failed_files:
                            # Extract just the filename if it contains path info
                            file_name = os.path.basename(failed_file) if os.path.sep in failed_file else failed_file
                            if file_name.lower().endswith('.shp') or file_name.lower().endswith('.dbf'):
                                critical_failed.append(file_name)
                    
                    if critical_failed:
                        # Build message with file paths
                        directory = os.path.dirname(actual_source)
                        base_path = os.path.splitext(actual_source)[0]
                        
                        message = "The following files could not be deleted automatically and must be deleted manually:\n\n"
                        
                        # Build full paths for each critical file
                        for file_name in critical_failed:
                            # Clean up file name (remove any error messages)
                            clean_name = file_name.split(':')[0] if ':' in file_name else file_name
                            
                            # Determine extension and build full path
                            if clean_name.lower().endswith('.shp'):
                                full_path = base_path + '.shp'
                            elif clean_name.lower().endswith('.dbf'):
                                full_path = base_path + '.dbf'
                            else:
                                # Fallback: try to extract extension and use base_path
                                ext = os.path.splitext(clean_name)[1]
                                if ext:
                                    full_path = base_path + ext
                                else:
                                    full_path = os.path.join(directory, clean_name)
                            
                            message += f"  • {full_path}\n"
                        
                        message += f"\nDirectory location: {directory}\n\n"
                        message += "These files (.shp and .dbf) may be locked by QGIS or another process.\n"
                        message += "Please close QGIS completely and delete them manually."
                        
                        self.show_warning("Files Must Be Deleted Manually", message)
                    elif not deleted_success and failed_files:
                        # Other files failed but not critical ones
                        directory = os.path.dirname(actual_source)
                        message = f"Some files could not be deleted automatically:\n\n"
                        for failed_file in failed_files:
                            file_name = os.path.basename(failed_file) if os.path.sep in failed_file else failed_file
                            message += f"  • {os.path.join(directory, file_name)}\n"
                        message += f"\nLocation: {directory}\n\n"
                        message += "Please close QGIS and delete them manually if needed."
                        self.show_warning("Some Files Could Not Be Deleted", message)
                    
                except Exception as e:
                    self.show_warning("Warning", f"Failed to delete original layer: {str(e)}")
            
            # Show success message
            if show_success_message and created_layers:
                success_text = f"Successfully split layer into {len(created_layers)} layers:\n\n"
                for new_layer, value_str, feature_count in created_layers:
                    success_text += f"  • {new_layer.name()}: {feature_count} feature(s)\n"
                
                if create_permanent:
                    success_text += f"\nLayer type: Permanent (saved to disk)"
                else:
                    success_text += f"\nLayer type: Temporary (memory only)"
                
                if add_to_project:
                    success_text += "\n\nAll layers have been added to the project."
                else:
                    success_text += "\n\nNote: Layers were created but not added to the project."
                
                if delete_original:
                    success_text += f"\n\nOriginal layer '{original_layer_name}' and its files have been deleted."
                
                self.show_info("Split Complete", success_text)
            elif not created_layers:
                self.show_error("Error", "No layers were created")
                
        except Exception as e:
            self.show_error("Error", f"Failed to split layer: {str(e)}")
            return
    
    def _delete_layer_files(self, file_path, file_format):
        """
        Delete all files associated with a layer.
        
        Args:
            file_path (str): Path to the main layer file
            file_format (str): Format of the layer (ESRI Shapefile, GPKG, etc.)
            
        Returns:
            tuple: (success, failed_files_list) where success is True if all files were deleted,
                   and failed_files_list contains names of files that couldn't be deleted
        """
        try:
            if not file_path:
                return True, []
            
            # Normalize the path
            file_path = os.path.normpath(file_path)
            
            if not os.path.exists(file_path):
                # File doesn't exist, might have been deleted already
                return True, []
            
            base_path = os.path.splitext(file_path)[0]
            deleted_count = 0
            failed_files = []
            
            if file_format == "ESRI Shapefile":
                # Delete all shapefile-related files
                extensions = [
                    '.shp', '.shx', '.dbf', '.prj', '.cpg', '.qpj',
                    '.sbn', '.sbx', '.fbn', '.fbx', '.ain', '.aih',
                    '.atx', '.ixs', '.mxs', '.qix', '.shp.xml'
                ]
                
                for ext in extensions:
                    file_to_delete = base_path + ext
                    if os.path.exists(file_to_delete):
                        # Try multiple times with retry logic
                        deleted = False
                        for attempt in range(3):
                            try:
                                # On Windows, files might be locked - try to remove read-only flag first
                                if os.name == 'nt':  # Windows
                                    try:
                                        os.chmod(file_to_delete, stat.S_IWRITE)
                                    except:
                                        pass
                                
                                os.remove(file_to_delete)
                                deleted = True
                                deleted_count += 1
                                break
                            except PermissionError:
                                if attempt < 2:
                                    # Wait a bit and try again
                                    time.sleep(0.1)
                                    QApplication.processEvents()
                                else:
                                    failed_files.append(os.path.basename(file_to_delete))
                            except OSError as e:
                                # File is locked or in use
                                if attempt >= 2:
                                    failed_files.append(os.path.basename(file_to_delete))
                                else:
                                    time.sleep(0.1)
                                    QApplication.processEvents()
                                    continue
                            except Exception as e:
                                if attempt >= 2:
                                    failed_files.append(os.path.basename(file_to_delete))
                                break
            
            elif file_format == "GPKG":
                # Delete the GeoPackage file
                if os.path.exists(file_path):
                    deleted = False
                    for attempt in range(3):
                        try:
                            if os.name == 'nt':
                                try:
                                    os.chmod(file_path, stat.S_IWRITE)
                                except:
                                    pass
                            
                            os.remove(file_path)
                            deleted = True
                            deleted_count += 1
                            break
                        except PermissionError:
                            if attempt < 2:
                                time.sleep(0.1)
                                QApplication.processEvents()
                            else:
                                failed_files.append(os.path.basename(file_path))
                        except Exception as e:
                            failed_files.append(f"{os.path.basename(file_path)}: {str(e)}")
                            break
            
            elif file_format == "GeoJSON":
                # Delete the GeoJSON file
                if os.path.exists(file_path):
                    deleted = False
                    for attempt in range(3):
                        try:
                            if os.name == 'nt':
                                try:
                                    os.chmod(file_path, stat.S_IWRITE)
                                except:
                                    pass
                            
                            os.remove(file_path)
                            deleted = True
                            deleted_count += 1
                            break
                        except PermissionError:
                            if attempt < 2:
                                time.sleep(0.1)
                                QApplication.processEvents()
                            else:
                                failed_files.append(os.path.basename(file_path))
                        except Exception as e:
                            failed_files.append(f"{os.path.basename(file_path)}: {str(e)}")
                            break
            
            elif file_format in ["KML", "KMZ"]:
                # Delete the KML/KMZ file
                if os.path.exists(file_path):
                    deleted = False
                    for attempt in range(3):
                        try:
                            if os.name == 'nt':
                                try:
                                    os.chmod(file_path, stat.S_IWRITE)
                                except:
                                    pass
                            
                            os.remove(file_path)
                            deleted = True
                            deleted_count += 1
                            break
                        except PermissionError:
                            if attempt < 2:
                                time.sleep(0.1)
                                QApplication.processEvents()
                            else:
                                failed_files.append(os.path.basename(file_path))
                        except Exception as e:
                            failed_files.append(f"{os.path.basename(file_path)}: {str(e)}")
                            break
            
            else:
                # For unknown formats, try to delete the main file
                if os.path.exists(file_path):
                    deleted = False
                    for attempt in range(3):
                        try:
                            if os.name == 'nt':
                                try:
                                    os.chmod(file_path, stat.S_IWRITE)
                                except:
                                    pass
                            
                            os.remove(file_path)
                            deleted = True
                            deleted_count += 1
                            break
                        except PermissionError:
                            if attempt < 2:
                                time.sleep(0.1)
                                QApplication.processEvents()
                            else:
                                failed_files.append(os.path.basename(file_path))
                        except Exception as e:
                            failed_files.append(f"{os.path.basename(file_path)}: {str(e)}")
                            break
            
            # Return success status and list of failed files
            success = len(failed_files) == 0 and (deleted_count > 0 or not os.path.exists(file_path))
            
            if failed_files:
                print(f"Warning: Failed to delete files: {', '.join(failed_files)}")
            
            return success, failed_files
                        
        except Exception as e:
            # Log the error
            print(f"Warning: Failed to delete layer files: {str(e)}")
            # Return failed files list - try to get at least the main file name
            if file_path and os.path.exists(file_path):
                return False, [os.path.basename(file_path)]
            return False, []


# REQUIRED: Create global instance for automatic discovery
split_point_layer_by_attribute_action = SplitPointLayerByAttributeAction()

