"""
Merge Polygon Layer Action for Right-click Utilities and Shortcuts Hub

Merges multiple polygon layers together, combining all features and attributes.
Checks for attribute compatibility and allows user to proceed even if
attribute columns differ. Optionally deletes source layers after merge.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsFields, QgsField, QgsProject,
    QgsWkbTypes, QgsVectorFileWriter, QgsMapLayer, QgsMemoryProviderUtils
)
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import (
    QInputDialog, QMessageBox, QDialog, QVBoxLayout, 
    QLabel, QCheckBox, QPushButton, QHBoxLayout, QApplication, QScrollArea, QWidget
)
import os
import time
import stat


class LayerSelectionDialog(QDialog):
    """Dialog for selecting multiple layers to merge."""
    
    def __init__(self, layers, initial_layer_name, parent=None):
        """
        Initialize the layer selection dialog.
        
        Args:
            layers: List of layers available for selection
            initial_layer_name: Name of the initial layer (will be pre-selected)
            parent: Parent widget
        """
        super().__init__(parent)
        self.layers = layers
        self.initial_layer_name = initial_layer_name
        self.selected_layers = []
        self.checkboxes = {}
        
        self.setWindowTitle("Select Layers to Merge")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Title
        title_label = QLabel(f"Select polygon layers to merge with '{self.initial_layer_name}':")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(scroll_layout)
        
        # Create checkboxes for each layer
        for layer in self.layers:
            checkbox = QCheckBox(f"{layer.name()} ({layer.featureCount()} features)")
            checkbox.setChecked(True)  # Pre-select all by default
            self.checkboxes[layer.id()] = checkbox
            scroll_layout.addWidget(checkbox)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
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
        self.merge_btn = QPushButton("Merge")
        self.merge_btn.setEnabled(True)
        self.merge_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.merge_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
    
    def select_all(self):
        """Select all layers."""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(True)
    
    def select_none(self):
        """Deselect all layers."""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(False)
    
    def get_selected_layers(self):
        """Get list of selected layers."""
        selected = []
        for layer in self.layers:
            if self.checkboxes[layer.id()].isChecked():
                selected.append(layer)
        return selected


class MergePolygonLayerAction(BaseAction):
    """Action to merge multiple polygon layers together."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "merge_polygon_layer"
        self.name = "Merge Polygon Layer"
        self.category = "Editing"
        self.description = "Merge multiple polygon layers together, combining all features and attributes. Checks for attribute compatibility and allows merging even if attribute columns differ. Optionally deletes source layers after merge."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with polygon layers
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
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
            'merged_layer_name_template': {
                'type': 'str',
                'default': 'merged_{layer_count}_layers',
                'label': 'Merged Layer Name Template',
                'description': 'Template for merged layer name. Available variables: {layer_count}, {first_layer_name}, {second_layer_name}',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add Merged Layer to Project',
                'description': 'Automatically add the merged layer to the QGIS project',
            },
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when merge is completed successfully',
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
    
    def _get_polygon_layers(self, exclude_layer):
        """
        Get all polygon layers from the project, excluding the specified layer.
        
        Args:
            exclude_layer: Layer to exclude from the list
            
        Returns:
            list: List of polygon layers
        """
        project = QgsProject.instance()
        all_layers = project.mapLayers().values()
        
        polygon_layers = []
        for layer in all_layers:
            if not layer.isValid():
                continue
            
            # Check if it's a vector layer
            if layer.type() != QgsMapLayer.VectorLayer:
                continue
            
            # Check if it's a polygon layer
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                continue
            
            # Exclude the current layer
            if layer.id() == exclude_layer.id():
                continue
            
            polygon_layers.append(layer)
        
        return polygon_layers
    
    def _compare_fields_multiple(self, layers):
        """
        Compare field collections across multiple layers and return differences.
        
        Args:
            layers: List of QgsVectorLayer objects
            
        Returns:
            dict: Dictionary with field names as keys and list of layer names that have that field as values
        """
        field_to_layers = {}
        all_field_names = set()
        
        for layer in layers:
            fields = layer.fields()
            layer_name = layer.name()
            for field in fields:
                field_name = field.name()
                all_field_names.add(field_name)
                if field_name not in field_to_layers:
                    field_to_layers[field_name] = []
                field_to_layers[field_name].append(layer_name)
        
        return field_to_layers, all_field_names
    
    def execute(self, context):
        """Execute the merge polygon layer action."""
        try:
            # Get settings with proper type conversion
            try:
                schema = self.get_settings_schema()
                layer_storage_type = str(self.get_setting('layer_storage_type', schema['layer_storage_type']['default']))
                merged_layer_name_template = str(self.get_setting('merged_layer_name_template', schema['merged_layer_name_template']['default']))
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
            layer1 = detected_feature.layer
            
            if not layer1 or not layer1.isValid():
                self.show_error("Error", "Invalid layer")
                return
            
            # Check if layer has polygon features
            if layer1.geometryType() != QgsWkbTypes.PolygonGeometry:
                self.show_error("Error", "This action only works with polygon layers")
                return
            
            # Get all other polygon layers
            other_layers = self._get_polygon_layers(layer1)
            
            if not other_layers:
                self.show_error("Error", "No other polygon layers found in the project to merge with")
                return
            
            # Show dialog to select multiple layers
            selection_dialog = LayerSelectionDialog(other_layers, layer1.name(), None)
            if selection_dialog.exec_() != QDialog.Accepted:
                return  # User cancelled
            
            # Get selected layers
            selected_layers = selection_dialog.get_selected_layers()
            
            if not selected_layers:
                self.show_error("Error", "No layers selected for merge")
                return
            
            # Combine initial layer with selected layers
            all_layers_to_merge = [layer1] + selected_layers
            
            # Compare attribute fields across all layers
            field_to_layers, all_field_names = self._compare_fields_multiple(all_layers_to_merge)
            
            # Check for field differences
            layers_with_all_fields = set()
            for field_name in all_field_names:
                if len(field_to_layers[field_name]) == len(all_layers_to_merge):
                    layers_with_all_fields.add(field_name)
            
            fields_only_in_some = all_field_names - layers_with_all_fields
            
            # If there are differences, ask user
            if fields_only_in_some:
                diff_message = "The layers have different attribute columns:\n\n"
                
                # Group fields by which layers have them
                for field_name in sorted(fields_only_in_some):
                    layers_with_field = field_to_layers[field_name]
                    diff_message += f"  • {field_name}: only in {', '.join(layers_with_field)}\n"
                
                diff_message += "\nCommon columns will be merged.\n"
                diff_message += "Missing columns will be added with NULL values.\n\n"
                diff_message += "Do you want to proceed with the merge?"
                
                reply = QMessageBox.question(
                    None,
                    "Attribute Column Differences",
                    diff_message,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply != QMessageBox.Yes:
                    return  # User cancelled
            
            # Get source file information for all layers
            layers_with_sources = []
            for layer in all_layers_to_merge:
                layer_source = layer.source()
                if not layer_source or layer_source.startswith('memory:'):
                    if layer_source.startswith('ogr:'):
                        parts = layer_source.split('|')
                        if parts:
                            file_part = parts[0].replace('ogr:', '')
                            if file_part and os.path.exists(file_part):
                                layer_source = file_part
                            else:
                                self.show_error("Error", f"Layer '{layer.name()}' must be a file-based layer (not a temporary/scratch layer)")
                                return
                        else:
                            self.show_error("Error", f"Layer '{layer.name()}' must be a file-based layer (not a temporary/scratch layer)")
                            return
                    else:
                        self.show_error("Error", f"Layer '{layer.name()}' must be a file-based layer (not a temporary/scratch layer)")
                        return
                
                actual_source = layer_source.split('|')[0] if '|' in layer_source else layer_source
                layers_with_sources.append((layer, actual_source))
            
            # Determine file format and directory from first layer
            first_layer, first_source = layers_with_sources[0]
            layer_dir = os.path.dirname(first_source)
            if not layer_dir or not os.path.exists(layer_dir):
                self.show_error("Error", f"Could not determine source directory for layer: {first_source}")
                return
            
            # Determine file format from source
            file_format = "ESRI Shapefile"  # Default
            file_extension = ".shp"
            
            source_lower = first_source.lower()
            if source_lower.endswith('.gpkg') or 'gpkg' in source_lower:
                file_format = "GPKG"
                file_extension = ".gpkg"
            elif source_lower.endswith('.geojson') or source_lower.endswith('.json'):
                file_format = "GeoJSON"
                file_extension = ".geojson"
            elif source_lower.endswith('.shp'):
                file_format = "ESRI Shapefile"
                file_extension = ".shp"
            elif source_lower.endswith('.kml'):
                file_format = "KML"
                file_extension = ".kml"
            elif source_lower.endswith('.kmz'):
                file_format = "KMZ"
                file_extension = ".kmz"
            
            # Create merged layer name
            layer_count = len(all_layers_to_merge)
            first_layer_name = all_layers_to_merge[0].name().replace(' ', '_').replace('/', '_').replace('\\', '_')
            second_layer_name = all_layers_to_merge[1].name().replace(' ', '_').replace('/', '_').replace('\\', '_') if len(all_layers_to_merge) > 1 else ""
            
            merged_layer_name = merged_layer_name_template.format(
                layer_count=layer_count,
                first_layer_name=first_layer_name,
                second_layer_name=second_layer_name
            )
            
            # Create combined fields from all layers
            combined_fields = QgsFields()
            field_names_added = set()
            
            # Add all fields from all layers (avoid duplicates)
            for layer in all_layers_to_merge:
                fields = layer.fields()
                for field in fields:
                    if field.name() not in field_names_added:
                        combined_fields.append(field)
                        field_names_added.add(field.name())
            
            # Get CRS (use first layer's CRS)
            crs = first_layer.crs()
            geometry_type = first_layer.wkbType()
            
            # Create temporary memory layer for merge
            temp_layer = QgsVectorLayer(
                f"Polygon?crs={crs.authid()}",
                merged_layer_name,
                "memory"
            )
            
            if not temp_layer.isValid():
                self.show_error("Error", "Failed to create temporary layer for merge")
                return
            
            # Add fields
            temp_layer.dataProvider().addAttributes(combined_fields.toList())
            temp_layer.updateFields()
            
            # Merge features from all layers
            temp_layer.startEditing()
            
            # Add features from all layers
            for layer in all_layers_to_merge:
                fields = layer.fields()
                field_map = {fields[i].name(): i for i in range(fields.count())}
                
                for feature in layer.getFeatures():
                    new_feature = QgsFeature(combined_fields)
                    new_feature.setGeometry(feature.geometry())
                    
                    # Set attributes
                    attrs = feature.attributes()
                    
                    for i, field in enumerate(combined_fields):
                        field_name = field.name()
                        if field_name in field_map:
                            attr_idx = field_map[field_name]
                            if attr_idx < len(attrs):
                                new_feature.setAttribute(i, attrs[attr_idx])
                        # Otherwise leave as NULL (default)
                    
                    temp_layer.addFeature(new_feature)
            
            temp_layer.commitChanges()
            temp_layer.updateExtents()
            
            # Check layer storage type setting
            if layer_storage_type == 'permanent':
                # Prompt user for save location
                from qgis.PyQt.QtWidgets import QFileDialog
                save_path, _ = QFileDialog.getSaveFileName(
                    None, "Save Merged Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                )
                if not save_path:
                    return  # User cancelled
                
                # Save temporary layer to file
                from qgis.core import QgsVectorFileWriter
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    temp_layer, save_path, "UTF-8", temp_layer.crs(), "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer to file: {error[1] if len(error) > 1 else 'Unknown error'}")
                    return
                
                # Load the saved layer
                merged_layer = QgsVectorLayer(save_path, merged_layer_name, "ogr")
                if not merged_layer.isValid():
                    self.show_error("Error", "Failed to load saved layer")
                    return
                
                create_permanent = True
            else:
                # Use the temporary memory layer directly
                merged_layer = temp_layer
                create_permanent = False
            
            # Get feature counts before potential deletion
            layer_counts = {layer.name(): layer.featureCount() for layer in all_layers_to_merge}
            merged_count = merged_layer.featureCount()
            
            # Ask user if they want to delete source layers
            delete_dialog = QDialog(None)
            delete_dialog.setWindowTitle("Delete Source Layers?")
            delete_dialog.setMinimumWidth(400)
            
            layout = QVBoxLayout()
            delete_dialog.setLayout(layout)
            
            message = f"Merged layer created successfully:\n\n"
            message += f"  • {merged_layer_name}\n"
            message += f"  • {merged_count} total features\n\n"
            message += "Do you want to delete the source layers and their files?"
            
            label = QLabel(message)
            label.setWordWrap(True)
            layout.addWidget(label)
            
            layer_names_list = ', '.join([layer.name() for layer in all_layers_to_merge[:3]])
            if len(all_layers_to_merge) > 3:
                layer_names_list += f" and {len(all_layers_to_merge) - 3} more"
            
            delete_checkbox = QCheckBox(f"Delete source layers ({len(all_layers_to_merge)} layers) and all associated files")
            delete_checkbox.setChecked(False)
            layout.addWidget(delete_checkbox)
            
            button_layout = QHBoxLayout()
            yes_button = QPushButton("Yes")
            no_button = QPushButton("No")
            yes_button.clicked.connect(delete_dialog.accept)
            no_button.clicked.connect(delete_dialog.reject)
            button_layout.addWidget(yes_button)
            button_layout.addWidget(no_button)
            layout.addLayout(button_layout)
            
            delete_original = False
            if delete_dialog.exec_() == QDialog.Accepted:
                delete_original = delete_checkbox.isChecked()
            
            # Delete source layers if requested
            if delete_original:
                project = QgsProject.instance()
                layers_to_delete = [
                    (layer, source, file_format)
                    for layer, source in layers_with_sources
                ]
                
                all_failed_files = []
                
                for layer, source_path, fmt in layers_to_delete:
                    try:
                        layer_id = layer.id()
                        
                        # Try to close the layer's data provider explicitly
                        try:
                            if layer.dataProvider():
                                layer.dataProvider().close()
                        except:
                            pass
                        
                        # Remove layer from project
                        project.removeMapLayer(layer_id)
                        
                        # Force garbage collection
                        import gc
                        gc.collect()
                        
                        # Process events and wait
                        QApplication.processEvents()
                        time.sleep(0.2)
                        QApplication.processEvents()
                        time.sleep(0.1)
                        QApplication.processEvents()
                        
                        # Delete files
                        deleted_success, failed_files = self._delete_layer_files(source_path, fmt)
                        if failed_files:
                            all_failed_files.extend(failed_files)
                        
                    except Exception as e:
                        self.show_warning("Warning", f"Failed to delete layer '{layer.name()}': {str(e)}")
                
                # Check for critical files that couldn't be deleted
                if all_failed_files:
                    critical_failed = []
                    for failed_file in all_failed_files:
                        file_name = os.path.basename(failed_file) if os.path.sep in failed_file else failed_file
                        if file_name.lower().endswith('.shp') or file_name.lower().endswith('.dbf'):
                            critical_failed.append(file_name)
                    
                    if critical_failed:
                        message = "The following files could not be deleted automatically and must be deleted manually:\n\n"
                        
                        for file_name in critical_failed:
                            clean_name = file_name.split(':')[0] if ':' in file_name else file_name
                            
                            # Try to find the file path
                            for layer, source_path, fmt in layers_to_delete:
                                base_path = os.path.splitext(source_path)[0]
                                if clean_name.lower().endswith('.shp'):
                                    full_path = base_path + '.shp'
                                    if os.path.exists(full_path):
                                        message += f"  • {full_path}\n"
                                        break
                                elif clean_name.lower().endswith('.dbf'):
                                    full_path = base_path + '.dbf'
                                    if os.path.exists(full_path):
                                        message += f"  • {full_path}\n"
                                        break
                        
                        message += f"\nDirectory location: {layer_dir}\n\n"
                        message += "These files (.shp and .dbf) may be locked by QGIS or another process.\n"
                        message += "Please close QGIS completely and delete them manually."
                        
                        self.show_warning("Files Must Be Deleted Manually", message)
            
            # Add merged layer to project if enabled
            if add_to_project:
                project = QgsProject.instance()
                project.addMapLayer(merged_layer)
            
            # Show success message
            if show_success_message:
                success_text = f"Successfully merged {len(all_layers_to_merge)} layers:\n\n"
                for layer in all_layers_to_merge:
                    success_text += f"  • '{layer.name()}' ({layer_counts[layer.name()]} features)\n"
                success_text += f"\nCreated merged layer: '{merged_layer_name}'\n"
                success_text += f"Total features: {merged_count}\n"
                
                if create_permanent:
                    success_text += f"\nLayer type: Permanent (saved to disk)"
                else:
                    success_text += f"\nLayer type: Temporary (memory only)"
                
                if add_to_project:
                    success_text += "\n\nMerged layer has been added to the project."
                
                if delete_original:
                    success_text += "\n\nSource layers and their files have been deleted."
                
                self.show_info("Merge Complete", success_text)
                
        except Exception as e:
            self.show_error("Error", f"Failed to merge layers: {str(e)}")
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
merge_polygon_layer_action = MergePolygonLayerAction()

