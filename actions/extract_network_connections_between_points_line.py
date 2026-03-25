"""
Extract Network Connections Between Points Action for Right-click Utilities and Shortcuts Hub

Extracts road network segments that connect points from a point layer.
For each point in the selected point layer, searches along the road network for nearby points
within a configurable distance and creates line features representing the network paths between them.
Works with line layers (road networks) and requires a point layer to be selected.
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager, HistoryManager
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsVectorFileWriter, QgsPointXY, QgsDistanceArea, QgsGeometryUtils,
    QgsFeatureRequest, QgsSpatialIndex, QgsRectangle, QgsUnitTypes, QgsMessageLog, Qgis
)
from qgis.PyQt.QtCore import QVariant, QMetaType, Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout, QMessageBox, QProgressDialog
import math
import random
import os
from datetime import datetime


class PointLayerSelectionDialog(QDialog):
    """Dialog for selecting a point layer to use for network connections."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Point Layer")
        self.selected_layer = None
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout()
        
        # Add label
        label = QLabel("Select the point layer containing stops/locations to connect:")
        layout.addWidget(label)
        
        # Add combo box for layer selection
        self.layer_combo = QComboBox()
        
        # Populate with point layers
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    self.layer_combo.addItem(layer.name(), layer.id())
        
        if self.layer_combo.count() == 0:
            self.layer_combo.addItem("No point layers found", None)
            self.layer_combo.setEnabled(False)
        
        layout.addWidget(self.layer_combo)
        
        # Add buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        
        ok_button.clicked.connect(self.accept_selection)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def accept_selection(self):
        """Accept the selected layer."""
        if self.layer_combo.count() > 0 and self.layer_combo.isEnabled():
            layer_id = self.layer_combo.currentData()
            if layer_id:
                self.selected_layer = QgsProject.instance().mapLayer(layer_id)
        self.accept()


class ExtractNetworkConnectionsBetweenPointsLineAction(BaseAction):
    """
    Action to extract network connections between points along a road network.
    
    This action takes a line layer (road network) and a point layer (stops/locations),
    then creates a new line layer with connections between points that are within
    a specified distance along the network. Each connection includes the road network
    path between the two points and attributes showing which points are connected.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "extract_network_connections_between_points_line"
        self.name = "Extract Network Connections Between Points"
        self.category = "Analysis"
        self.description = "Extract road network segments connecting points from a point layer. Searches along the network for nearby points and creates connections showing the actual road paths between them. Includes point names and distances."
        self.enabled = True
        
        # Action scoping - works on line layers (road networks)
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with line layers
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def supports_undo(self) -> bool:
        """This action creates a new layer and is undoable via layer removal."""
        return True

    def get_undo_category(self) -> str:
        """Classify as 'trivial' (create -> delete) per the guide."""
        return 'trivial'
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # SEARCH SETTINGS
            'search_distance': {
                'type': 'float',
                'default': 1000.0,
                'label': 'Search Distance',
                'description': 'Maximum distance along the network to search for connecting points (in map units)',
                'min': 1.0,
                'max': 100000.0,
                'step': 100.0,
            },
            'point_field_name': {
                'type': 'str',
                'default': 'stop_name',
                'label': 'Point Identifier Field',
                'description': 'Field name in the point layer to use for identifying points (e.g., "stop_name", "id", "name")',
            },
            
            # OUTPUT SETTINGS
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            'output_layer_name': {
                'type': 'str',
                'default': 'Network Connections',
                'label': 'Output Layer Name',
                'description': 'Name for the new line layer that will be created',
            },
            'add_to_project': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Project',
                'description': 'Automatically add the new line layer to the current project',
            },
            
            # CONNECTION ATTRIBUTES
            'include_distance_field': {
                'type': 'bool',
                'default': True,
                'label': 'Include Distance Field',
                'description': 'Add a field with the distance of each connection along the network',
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places for distance values',
                'min': 0,
                'max': 6,
                'step': 1,
            },
            
            # BEHAVIOR SETTINGS
            'show_info_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Info Message',
                'description': 'Display information message when connection extraction completes',
            },
            'show_error_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Error Messages',
                'description': 'Display error messages if connection extraction fails',
            },
            'show_unconnected_points': {
                'type': 'bool',
                'default': True,
                'label': 'Show Unconnected Points Log',
                'description': 'Display log of points that have no connections within search distance',
            },
            
            # LOGGING SETTINGS
            'log_folder_path': {
                'type': 'str',
                'default': '',
                'label': 'Log Folder Path',
                'description': 'Folder where log files are saved. Leave empty to use Downloads folder.',
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
        """
        Execute the extract network connections action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Initialize log file
        log_file = None
        log_path = None
        start_time = datetime.now()
        try:
            # Get log folder from settings or use Downloads folder as default
            log_folder_setting = str(self.get_setting('log_folder_path', '')).strip()
            if log_folder_setting:
                log_dir = log_folder_setting
            else:
                # Default to Downloads folder
                log_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
            
            # Create log directory if it doesn't exist
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file with timestamp
            timestamp = start_time.strftime('%Y%m%d_%H%M%S')
            log_path = os.path.join(log_dir, f'network_connections_{timestamp}.txt')
            log_file = open(log_path, 'w', encoding='utf-8')
            
            log_file.write(f"Network Connections Extraction Log\n")
            log_file.write(f"{'='*50}\n")
            log_file.write(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        except Exception:
            log_file = None  # If logging fails, continue without it
        
        # Get settings with proper type conversion
        try:
            search_distance = float(self.get_setting('search_distance', 1000.0))
            point_field_name = str(self.get_setting('point_field_name', 'stop_name'))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            output_layer_name = str(self.get_setting('output_layer_name', 'Network Connections'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            include_distance_field = bool(self.get_setting('include_distance_field', True))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_info_message = bool(self.get_setting('show_info_message', True))
            show_error_messages = bool(self.get_setting('show_error_messages', True))
            show_unconnected_points = bool(self.get_setting('show_unconnected_points', True))
            
            if log_file:
                log_file.write(f"Settings:\n")
                log_file.write(f"  Search Distance: {search_distance} units\n")
                log_file.write(f"  Point Field: {point_field_name}\n")
                log_file.write(f"  Output Layer: {output_layer_name}\n\n")
                log_file.flush()
        except (ValueError, TypeError) as e:
            if log_file:
                log_file.write(f"ERROR: Invalid setting values: {str(e)}\n")
                log_file.close()
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            if log_file:
                log_file.write("ERROR: No features found at this location\n")
                log_file.close()
            if show_error_messages:
                self.show_error("Error", "No features found at this location")
            return
        
        # Get the road network layer
        detected_feature = detected_features[0]
        network_layer = detected_feature.layer
        
        if log_file:
            log_file.write(f"Network Layer: {network_layer.name()}\n")
            log_file.write(f"  CRS: {network_layer.crs().authid()}\n")
            log_file.write(f"  Features: {network_layer.featureCount()}\n\n")
            log_file.flush()
        
        # Validate that this is a line layer
        if network_layer.geometryType() not in [QgsWkbTypes.LineGeometry, QgsWkbTypes.MultiLineString]:
            if log_file:
                log_file.write("ERROR: Not a line layer\n")
                log_file.close()
            if show_error_messages:
                self.show_error("Error", "This action only works with line layers (road networks)")
            return
        
        # Show point layer selection dialog
        dialog = PointLayerSelectionDialog()
        if dialog.exec_() != QDialog.Accepted or not dialog.selected_layer:
            if log_file:
                log_file.write("Action cancelled: No point layer selected\n")
                log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.close()
            return  # User cancelled or no layer selected
        
        point_layer = dialog.selected_layer
        
        if log_file:
            log_file.write(f"Point Layer: {point_layer.name()}\n")
            log_file.write(f"  CRS: {point_layer.crs().authid()}\n")
        
        # Validate point field exists
        if point_field_name not in [field.name() for field in point_layer.fields()]:
            if log_file:
                log_file.write(f"ERROR: Field '{point_field_name}' not found in point layer\n")
                log_file.close()
            if show_error_messages:
                self.show_error(
                    "Error",
                    f"Field '{point_field_name}' not found in point layer.\n"
                    f"Available fields: {', '.join([f.name() for f in point_layer.fields()])}\n\n"
                    f"Please update the 'Point Identifier Field' setting."
                )
            return
        
        try:
            # Get all points from the point layer
            points = list(point_layer.getFeatures())
            
            if log_file:
                log_file.write(f"  Points: {len(points)}\n\n")
                log_file.flush()
            
            if len(points) < 2:
                if log_file:
                    log_file.write("ERROR: Point layer must contain at least 2 points\n")
                    log_file.close()
                if show_error_messages:
                    self.show_error("Error", "Point layer must contain at least 2 points to create connections")
                return
            
            # Create progress dialog
            progress = QProgressDialog("Extracting network connections...", "Cancel", 0, 100)
            progress.setWindowTitle("Network Connection Extraction")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            
            try:
                # Build spatial index for road network
                if log_file:
                    log_file.write("Building spatial index...\n")
                    log_file.flush()
                progress.setLabelText("Building spatial index for network...")
                progress.setValue(5)
                network_index = QgsSpatialIndex(network_layer.getFeatures())
                
                if progress.wasCanceled():
                    if log_file:
                        log_file.write("Action cancelled by user during index build\n")
                        log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        log_file.close()
                    return
                
                # Find connections between points
                if log_file:
                    log_file.write(f"Searching for connections between {len(points)} points...\n")
                    log_file.flush()
                progress.setLabelText(f"Finding connections between {len(points)} points...")
                progress.setValue(10)
                
                connections, unconnected_points = self._find_network_connections(
                    points,
                    network_layer,
                    network_index,
                    point_field_name,
                    search_distance,
                    include_distance_field,
                    progress,
                    log_file
                )
                
                if progress.wasCanceled():
                    if log_file:
                        log_file.write("Action cancelled by user during connection search\n")
                        log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        log_file.close()
                    return
            
                if not connections:
                    progress.close()
                    if log_file:
                        log_file.write(f"\n{'='*50}\n")
                        log_file.write("RESULT: No connections found\n")
                        log_file.write(f"{'='*50}\n")
                        if unconnected_points:
                            log_file.write(f"Unconnected points: {len(unconnected_points)}\n")
                            for up in unconnected_points[:20]:
                                log_file.write(f"  - {up}\n")
                            if len(unconnected_points) > 20:
                                log_file.write(f"  ... and {len(unconnected_points) - 20} more\n")
                        log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        log_file.close()
                    if show_error_messages:
                        self.show_error(
                            "No Connections Found",
                            f"No points found within {search_distance} map units of each other along the network.\n"
                            f"Try increasing the search distance setting."
                        )
                    return
                
                if log_file:
                    log_file.write(f"\n{'='*50}\n")
                    log_file.write(f"CONNECTION SEARCH COMPLETED\n")
                    log_file.write(f"{'='*50}\n")
                    log_file.write(f"Total connections found: {len(connections)}\n")
                    log_file.write(f"Total points processed: {len(points)}\n")
                    if unconnected_points:
                        log_file.write(f"Unconnected points: {len(unconnected_points)}\n")
                        for up in unconnected_points[:20]:
                            log_file.write(f"  - {up}\n")
                        if len(unconnected_points) > 20:
                            log_file.write(f"  ... and {len(unconnected_points) - 20} more\n")
                    log_file.write(f"\nCreating output layer...\n")
                    log_file.flush()
                
                progress.setLabelText("Creating output layer...")
                progress.setValue(60)
            
                # Create the new connection layer
                if layer_storage_type == 'permanent':
                    # Prompt user for save location
                    from qgis.PyQt.QtWidgets import QFileDialog
                    save_path, _ = QFileDialog.getSaveFileName(
                        None, "Save Connections Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                    )
                    if not save_path:
                        progress.close()
                        if log_file:
                            log_file.write("Action cancelled: No save path selected\n")
                            log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            log_file.close()
                        return  # User cancelled
                
                    progress.setLabelText("Creating temporary layer...")
                    progress.setValue(65)
                    
                    # Create temporary layer first
                    temp_layer = self._create_connection_layer(
                        output_layer_name,
                        network_layer.crs(),
                        include_distance_field
                    )
                    
                    if not temp_layer:
                        progress.close()
                        if show_error_messages:
                            self.show_error("Error", "Failed to create temporary layer")
                        return
                    
                    progress.setLabelText(f"Adding {len(connections)} connections to layer...")
                    progress.setValue(70)
                    
                    # Add connections to temporary layer
                    if not self._add_connections_to_layer(temp_layer, connections, decimal_places, progress):
                        if log_file:
                            log_file.write("Action cancelled during feature addition\n")
                            log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            log_file.close()
                        return  # Cancelled
                    
                    progress.setLabelText("Saving layer to file...")
                    progress.setValue(80)
                
                    # Save temporary layer to file
                    error = QgsVectorFileWriter.writeAsVectorFormat(
                        temp_layer, save_path, "UTF-8", temp_layer.crs(),
                        "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                    )
                    if error[0] != QgsVectorFileWriter.NoError:
                        progress.close()
                        self.show_error("Error", f"Failed to save layer to file: {error[1] if len(error) > 1 else 'Unknown error'}")
                        return
                    
                    progress.setLabelText("Loading saved layer...")
                    progress.setValue(90)
                    
                    # Load the saved layer
                    new_layer = QgsVectorLayer(save_path, output_layer_name, "ogr")
                    if not new_layer.isValid():
                        progress.close()
                        self.show_error("Error", "Failed to load saved layer")
                        return
                else:
                    progress.setLabelText("Creating in-memory layer...")
                    progress.setValue(65)
                    
                    # Create temporary in-memory layer
                    new_layer = self._create_connection_layer(
                        output_layer_name,
                        network_layer.crs(),
                        include_distance_field
                    )
                    
                    if not new_layer:
                        progress.close()
                        if show_error_messages:
                            self.show_error("Error", "Failed to create new connection layer")
                        return
                    
                    progress.setLabelText(f"Adding {len(connections)} connections to layer...")
                    progress.setValue(70)
                    
                    # Add connections to layer
                    if not self._add_connections_to_layer(new_layer, connections, decimal_places, progress):
                        if log_file:
                            log_file.write("Action cancelled during feature addition\n")
                            log_file.write(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            log_file.close()
                        return  # Cancelled
                    progress.setValue(90)
            
                # Add layer to project if requested
                if add_to_project:
                    progress.setLabelText("Adding layer to project...")
                    progress.setValue(95)
                    project = QgsProject.instance()
                    project.addMapLayer(new_layer)
                
                    # Record history for created layer
                    try:
                        features_backup = []
                        for f in new_layer.getFeatures():
                            try:
                                features_backup.append(self.create_feature_backup(f, new_layer))
                            except Exception:
                                features_backup.append({'fid': f.id()})
                        
                        fields_def = []
                        for fld in new_layer.fields():
                            try:
                                fields_def.append({'name': fld.name(), 'qmeta_type': fld.type()})
                            except Exception:
                                fields_def.append({'name': fld.name()})
                        
                        layer_def = {
                            'layer_name': new_layer.name(),
                            'crs': new_layer.crs().authid() if new_layer.crs().isValid() else '',
                            'geometry_type': QgsWkbTypes.displayString(new_layer.wkbType()),
                            'fields': fields_def,
                            'features': features_backup
                        }
                        
                        hm = get_history_manager()
                        hm.record(
                            action_id=self.action_id,
                            action_name=self.name,
                            description=f"Created {len(connections)} network connections in layer '{new_layer.name()}'",
                            undo_type=HistoryManager.UNDO_TYPE_CREATE_LAYER,
                            can_undo=True,
                            undo_payload={'layer_definition': layer_def},
                            layers=[self.create_layer_descriptor(new_layer)],
                            features=features_backup,
                            atomic=True,
                            meta={
                                'network_layer_id': network_layer.id(),
                                'network_layer_name': network_layer.name(),
                                'point_layer_id': point_layer.id(),
                                'point_layer_name': point_layer.name(),
                                'num_points': len(points),
                                'num_connections': len(connections)
                            }
                        )
                    except Exception:
                        pass  # History recording must not break action
                
                progress.setValue(100)
                progress.close()
                
                if log_file:
                    end_time = datetime.now()
                    elapsed = (end_time - start_time).total_seconds()
                    log_file.write(f"\n{'='*50}\n")
                    log_file.write(f"ACTION COMPLETED SUCCESSFULLY\n")
                    log_file.write(f"{'='*50}\n")
                    log_file.write(f"Output layer: {output_layer_name}\n")
                    log_file.write(f"Layer type: {layer_storage_type}\n")
                    log_file.write(f"Added to project: {'Yes' if add_to_project else 'No'}\n")
                    log_file.write(f"Total connections created: {len(connections)}\n")
                    if include_distance_field:
                        log_file.write(f"Distance field included: Yes\n")
                    log_file.write(f"\nEnd Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_file.write(f"Elapsed Time: {int(elapsed//60)}m {int(elapsed%60)}s ({elapsed:.1f} seconds)\n")
                    log_file.flush()
                
            finally:
                # Ensure progress dialog is closed
                if 'progress' in locals():
                    progress.close()
            
            # Build success message
            success_msg = f"Successfully created {len(connections)} network connections.\n"
            success_msg += f"Points processed: {len(points)}\n"
            success_msg += f"New layer: {output_layer_name}\n"
            success_msg += f"Added to project: {'Yes' if add_to_project else 'No'}\n"
            if log_path:
                success_msg += f"\nLog saved to: {log_path}"
            
            # Add unconnected points info if any
            if unconnected_points and show_unconnected_points:
                success_msg += f"\n\nUnconnected points ({len(unconnected_points)}):\n"
                success_msg += "\n".join(f"  - {name}" for name in unconnected_points[:10])
                if len(unconnected_points) > 10:
                    success_msg += f"\n  ... and {len(unconnected_points) - 10} more"
            
            # Show success message if enabled
            if show_info_message:
                self.show_info("Network Connections Created", success_msg)
            
            # Close log file on success
            if log_file:
                log_file.close()
                
        except Exception as e:
            if log_file:
                end_time = datetime.now()
                elapsed = (end_time - start_time).total_seconds()
                log_file.write(f"\n{'='*50}\n")
                log_file.write(f"ERROR OCCURRED\n")
                log_file.write(f"{'='*50}\n")
                log_file.write(f"Error: {str(e)}\n")
                log_file.write(f"\nEnd Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"Elapsed Time: {int(elapsed//60)}m {int(elapsed%60)}s ({elapsed:.1f} seconds)\n")
                log_file.close()
            if show_error_messages:
                self.show_error("Error", f"Failed to extract network connections: {str(e)}")
    
    def _create_connection_layer(self, layer_name, crs, include_distance):
        """
        Create a new line layer for network connections.
        
        Args:
            layer_name (str): Name for the new layer
            crs: Coordinate reference system for the layer
            include_distance (bool): Whether to include distance field
            
        Returns:
            QgsVectorLayer: New line layer or None if failed
        """
        try:
            # Create memory layer for connections
            layer_uri = f"LineString?crs={crs.authid()}"
            new_layer = QgsVectorLayer(layer_uri, layer_name, "memory")
            
            if not new_layer.isValid():
                return None
            
            # Add fields
            new_layer.startEditing()
            
            # Add from_point and to_point fields
            new_layer.dataProvider().addAttributes([
                QgsField("from_point", QMetaType.QString),
                QgsField("to_point", QMetaType.QString)
            ])
            
            # Add distance field if requested
            if include_distance:
                distance_field = QgsField("distance", QMetaType.Double)
                distance_field.setPrecision(10)
                distance_field.setLength(20)
                new_layer.dataProvider().addAttributes([distance_field])
            
            new_layer.updateFields()
            new_layer.commitChanges()
            
            return new_layer
            
        except Exception as e:
            return None
    
    def _find_network_connections(self, points, network_layer, network_index, point_field_name, search_distance, include_distance, progress=None, log_file=None):
        """
        Find connections between points along the network using graph traversal.
        
        Args:
            points (list): List of point features
            network_layer (QgsVectorLayer): Road network layer
            network_index (QgsSpatialIndex): Spatial index for network layer
            point_field_name (str): Field name for point identifiers
            search_distance (float): Maximum search distance along network
            include_distance (bool): Whether to calculate distances
            progress (QProgressDialog): Optional progress dialog
            log_file: Optional file handle for detailed logging
            
        Returns:
            tuple: (connections list, unconnected_points list)
        """
        connections = []
        connected_pairs = set()  # Track connected pairs to avoid duplicates
        unconnected_points = []
        
        if log_file:
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"NETWORK EXPLORATION STARTED\n")
            log_file.write(f"{'='*50}\n")
            log_file.flush()
        
        # Randomize point processing order to start from different point each time
        points_list = list(points)
        random.shuffle(points_list)
        
        # Map points to their locations for quick lookup
        point_locations = {}
        for point in points_list:
            point_geom = point.geometry()
            if point_geom and not point_geom.isEmpty():
                point_name = str(point[point_field_name]) if point[point_field_name] else f"Point_{point.id()}"
                point_locations[point_name] = point_geom.asPoint()
        
        # Calculate progress step
        total_points = len(points_list)
        progress_step = 50 / total_points if total_points > 0 else 0
        
        # Process each point
        for i, point1 in enumerate(points_list):
            point1_geom = point1.geometry()
            if not point1_geom or point1_geom.isEmpty():
                continue
            
            point1_name = str(point1[point_field_name]) if point1[point_field_name] else f"Point_{point1.id()}"
            point1_xy = point1_geom.asPoint()
            
            if log_file:
                log_file.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing point {i+1}/{total_points}: {point1_name}\n")
                log_file.flush()
            
            # Update progress and process events to keep UI responsive
            if progress:
                progress_value = 10 + int(i * progress_step)
                progress.setValue(progress_value)
                progress.setLabelText(
                    f"Point {i+1}/{total_points}: {point1_name}\n"
                    f"Connections found so far: {len(connections)}\n"
                    f"Locating network segment..."
                )
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    return connections, unconnected_points
            
            # Find which network segment this point is on
            if progress:
                progress.setLabelText(
                    f"Point {i+1}/{total_points}: {point1_name}\n"
                    f"Connections found so far: {len(connections)}\n"
                    f"Finding closest network segment..."
                )
                QCoreApplication.processEvents()
            
            start_segment = self._find_closest_network_segment(point1_geom, network_layer, network_index)
            if not start_segment:
                if log_file:
                    log_file.write(f"  ⚠ Point not on network (too far from roads)\n")
                    log_file.flush()
                if progress:
                    progress.setLabelText(
                        f"Point {i+1}/{total_points}: {point1_name}\n"
                        f"⚠ Not on network (too far from roads)\n"
                        f"Moving to next point..."
                    )
                    QCoreApplication.processEvents()
                unconnected_points.append(point1_name)
                continue
            
            # Explore the network graph from this point
            if progress:
                progress.setLabelText(
                    f"Point {i+1}/{total_points}: {point1_name}\n"
                    f"Connections found so far: {len(connections)}\n"
                    f"Exploring network (max {int(search_distance)} units)..."
                )
                QCoreApplication.processEvents()
            
            if log_file:
                log_file.write(f"  Starting BFS exploration (max distance: {int(search_distance)} units)\n")
                log_file.flush()
            
            found_connections = self._explore_network_from_point(
                point1_name,
                point1_xy,
                start_segment,
                point_locations,
                network_layer,
                network_index,
                search_distance,
                connected_pairs,
                progress,
                i + 1,
                total_points,
                log_file
            )
            
            # Add found connections
            if found_connections:
                if log_file:
                    log_file.write(f"  ✓ Found {len(found_connections)} connection(s): ")
                    log_file.write(", ".join([c['to_point'] for c in found_connections]))
                    log_file.write("\n")
                    log_file.flush()
                if progress:
                    progress.setLabelText(
                        f"Point {i+1}/{total_points}: {point1_name}\n"
                        f"✓ Found {len(found_connections)} connection(s)\n"
                        f"Adding to results..."
                    )
                    QCoreApplication.processEvents()
            elif log_file:
                log_file.write(f"  No connections found within search distance\n")
                log_file.flush()
            
            for connection_info in found_connections:
                to_point_name = connection_info['to_point']
                path_geometry = connection_info['geometry']
                
                # Calculate distance if requested
                network_distance = 0.0
                if include_distance:
                    network_distance = path_geometry.length()
                
                # Check if within search distance
                if network_distance <= search_distance or not include_distance:
                    connections.append({
                        'from_point': point1_name,
                        'to_point': to_point_name,
                        'geometry': path_geometry,
                        'distance': network_distance
                    })
                    
                    # Mark pair as connected
                    pair_id = tuple(sorted([point1_name, to_point_name]))
                    connected_pairs.add(pair_id)
            
            # Check if this point had any connections
            if not found_connections:
                if point1_name not in [conn['from_point'] for conn in connections] and \
                   point1_name not in [conn['to_point'] for conn in connections]:
                    if progress:
                        progress.setLabelText(
                            f"Point {i+1}/{total_points}: {point1_name}\n"
                            f"⚠ No connections found within {int(search_distance)} units\n"
                            f"Will be listed as unconnected"
                        )
                        QCoreApplication.processEvents()
                    unconnected_points.append(point1_name)
            else:
                if progress:
                    progress.setLabelText(
                        f"Point {i+1}/{total_points}: {point1_name}\n"
                        f"✓ Successfully created {len(found_connections)} connection(s)\n"
                        f"Total connections: {len(connections)}"
                    )
                    QCoreApplication.processEvents()
        
        # Final summary
        if progress:
            progress.setLabelText(
                f"Completed network exploration\n"
                f"Total connections: {len(connections)}\n"
                f"Unconnected points: {len(unconnected_points)}"
            )
            progress.setValue(60)
            QCoreApplication.processEvents()
        
        return connections, unconnected_points
    
    def _find_closest_network_segment(self, point_geom, network_layer, network_index):
        """
        Find the closest network segment to a point.
        
        Args:
            point_geom: Point geometry
            network_layer: Network layer
            network_index: Spatial index
            
        Returns:
            QgsFeature: Closest network segment or None
        """
        SNAP_TOLERANCE = 100
        
        # Search in area around point
        search_rect = QgsRectangle(point_geom.boundingBox())
        search_rect.grow(SNAP_TOLERANCE)
        
        nearby_ids = network_index.intersects(search_rect)
        if not nearby_ids:
            return None
        
        closest_segment = None
        min_distance = float('inf')
        
        for seg_id in nearby_ids:
            request = QgsFeatureRequest().setFilterFid(seg_id)
            for feat in network_layer.getFeatures(request):
                seg_geom = feat.geometry()
                if seg_geom and not seg_geom.isEmpty():
                    dist = point_geom.distance(seg_geom)
                    if dist < min_distance:
                        min_distance = dist
                        closest_segment = feat
        
        # Only return if within tolerance
        if min_distance > SNAP_TOLERANCE:
            return None
        
        return closest_segment
    
    def _explore_network_from_point(self, start_point_name, start_point_xy, start_segment, 
                                     point_locations, network_layer, network_index, 
                                     max_distance, connected_pairs, progress=None, 
                                     current_point_num=0, total_points=0, log_file=None):
        """
        Explore the network graph from a starting point to find connections to other points.
        Uses breadth-first search to traverse the network.
        
        Args:
            start_point_name: Name of the starting point
            start_point_xy: QgsPointXY of starting point
            start_segment: Network feature containing the starting point
            point_locations: Dictionary mapping point names to coordinates
            network_layer: Network layer
            network_index: Spatial index
            max_distance: Maximum distance to explore
            connected_pairs: Set of already connected point pairs
            progress: Optional progress dialog
            current_point_num: Current point number being processed
            total_points: Total number of points
            log_file: Optional file handle for detailed logging
            
        Returns:
            list: List of connection dictionaries with 'to_point' and 'geometry'
        """
        from collections import deque
        
        connections_found = []
        segments_explored = 0
        points_found = set()  # Track points we've already connected to
        MAX_CONNECTIONS_PER_POINT = 6  # User expects 4-5, so 6 is reasonable
        MAX_SEGMENTS_TO_EXPLORE = 3000  # Hard limit to prevent excessive exploration
        MAX_QUEUE_SIZE = 5000  # Stop if queue grows too large
        last_log_time = datetime.now()
        last_connection_at_segment = 0  # Track when we last found a connection
        
        # Queue for BFS: (current_segment, accumulated_path, accumulated_distance, visited_segments)
        queue = deque()
        
        # Start exploring from the initial segment
        start_geom = start_segment.geometry()
        queue.append((start_segment, [start_geom], 0.0, {start_segment.id()}))
        
        while queue and len(connections_found) < MAX_CONNECTIONS_PER_POINT:
            segments_explored += 1
            
            # SAFETY LIMITS - stop if exploring too much
            if segments_explored > MAX_SEGMENTS_TO_EXPLORE:
                if log_file:
                    log_file.write(
                        f"    [{datetime.now().strftime('%H:%M:%S')}] Stopping: Segment limit reached ({MAX_SEGMENTS_TO_EXPLORE})\n"
                    )
                    log_file.flush()
                break
            
            # Stop if queue is growing too large (exponential growth)
            if len(queue) > MAX_QUEUE_SIZE:
                if log_file:
                    log_file.write(
                        f"    [{datetime.now().strftime('%H:%M:%S')}] Stopping: Queue too large ({len(queue)} segments)\n"
                    )
                    log_file.flush()
                break
            
            # Stop if we haven't found a connection in a long time
            if len(connections_found) > 0 and (segments_explored - last_connection_at_segment) > 1500:
                if log_file:
                    log_file.write(
                        f"    [{datetime.now().strftime('%H:%M:%S')}] Stopping: No new connections in last 1500 segments\n"
                    )
                    log_file.flush()
                break
            
            # Update progress periodically
            if progress and segments_explored % 25 == 0:
                progress.setLabelText(
                    f"Point {current_point_num}/{total_points}: {start_point_name}\n"
                    f"Explored {segments_explored} segments, found {len(connections_found)} connection(s)\n"
                    f"Queue size: {len(queue)} segments to check"
                )
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    return connections_found
            
            # Log BFS progress every 5-10 seconds (check every 50 segments)
            if log_file and segments_explored % 50 == 0:
                current_time = datetime.now()
                elapsed = (current_time - last_log_time).total_seconds()
                if elapsed >= 5.0:  # Log if at least 5 seconds have passed
                    log_file.write(
                        f"    [{current_time.strftime('%H:%M:%S')}] BFS: {segments_explored} segments explored, "
                        f"{len(connections_found)} connection(s) found, "
                        f"queue: {len(queue)} segments\n"
                    )
                    log_file.flush()
                    last_log_time = current_time
            
            current_segment, path_so_far, distance_so_far, visited = queue.popleft()
            current_geom = current_segment.geometry()
            
            # Check if we've exceeded max distance
            if distance_so_far > max_distance:
                continue
            
            # Check if this segment has any other points on it
            found_point_on_this_segment = False
            for other_point_name, other_point_xy in point_locations.items():
                # Skip the starting point itself
                if other_point_name == start_point_name:
                    continue
                
                # Skip if already connected to this point
                if other_point_name in points_found:
                    continue
                
                # Check if already connected
                pair_id = tuple(sorted([start_point_name, other_point_name]))
                if pair_id in connected_pairs:
                    continue
                
                # Check if the other point is on this segment
                other_point_geom = QgsGeometry.fromPointXY(other_point_xy)
                dist_to_segment = other_point_geom.distance(current_geom)
                
                if dist_to_segment < 100:  # Point is on this segment
                    # Create path geometry from start to this point
                    path_geometry = self._create_path_geometry(path_so_far, start_point_xy, other_point_xy)
                    
                    if path_geometry:
                        connections_found.append({
                            'to_point': other_point_name,
                            'geometry': path_geometry
                        })
                        
                        # Mark this point as found
                        points_found.add(other_point_name)
                        found_point_on_this_segment = True
                        last_connection_at_segment = segments_explored  # Update last connection time
                        
                        # Log connection found
                        if log_file:
                            log_file.write(
                                f"    [{datetime.now().strftime('%H:%M:%S')}] ✓ Connection found: {start_point_name} -> {other_point_name} "
                                f"(distance: {int(distance_so_far)} units, segments: {segments_explored})\n"
                            )
                            log_file.flush()
                        
                        # Update progress when connection found
                        if progress:
                            progress.setLabelText(
                                f"Point {current_point_num}/{total_points}: {start_point_name}\n"
                                f"✓ Connected to: {other_point_name}\n"
                                f"Distance: {int(distance_so_far)} units, Total found: {len(connections_found)}"
                            )
                            QCoreApplication.processEvents()
                        
                        # Stop exploring this path - we found a point!
                        break
            
            # If we found a point on this segment, don't continue exploring from here
            if found_point_on_this_segment:
                continue
            
            # Find connected segments to continue exploration
            connected_segments = self._find_connected_segments(
                current_segment,
                network_layer,
                network_index,
                visited
            )
            
            # Log branching if multiple paths found
            if progress and len(connected_segments) > 1 and segments_explored % 50 == 0:
                progress.setLabelText(
                    f"Point {current_point_num}/{total_points}: {start_point_name}\n"
                    f"Found {len(connected_segments)} branches at intersection\n"
                    f"Exploring all paths..."
                )
                QCoreApplication.processEvents()
            
            for next_segment in connected_segments:
                next_geom = next_segment.geometry()
                next_distance = distance_so_far + next_geom.length()
                
                # Only continue if within search distance
                if next_distance <= max_distance:
                    new_path = path_so_far + [next_geom]
                    new_visited = visited.copy()
                    new_visited.add(next_segment.id())
                    
                    queue.append((next_segment, new_path, next_distance, new_visited))
        
        return connections_found
    
    def _find_connected_segments(self, segment, network_layer, network_index, visited):
        """
        Find all network segments that are connected to the given segment.
        A segment is connected if it shares an endpoint (touches) with the current segment.
        This allows traversal from one line feature to another in the network.
        
        Args:
            segment: Current network segment
            network_layer: Network layer
            network_index: Spatial index
            visited: Set of already visited segment IDs
            
        Returns:
            list: List of connected network features
        """
        connected = []
        segment_geom = segment.geometry()
        
        # Get endpoints of the current segment
        if segment_geom.isMultipart():
            polylines = segment_geom.asMultiPolyline()
            if polylines:
                line_points = polylines[0]
            else:
                return connected
        else:
            line_points = segment_geom.asPolyline()
        
        if not line_points or len(line_points) < 2:
            return connected
        
        # Get start and end points of current segment
        start_point = line_points[0]
        end_point = line_points[-1]
        
        # Search for segments near the endpoints
        ENDPOINT_TOLERANCE = 10  # Map units for endpoint matching
        
        # Create search boxes around each endpoint
        for endpoint in [start_point, end_point]:
            search_box = QgsRectangle(
                endpoint.x() - ENDPOINT_TOLERANCE,
                endpoint.y() - ENDPOINT_TOLERANCE,
                endpoint.x() + ENDPOINT_TOLERANCE,
                endpoint.y() + ENDPOINT_TOLERANCE
            )
            
            nearby_ids = network_index.intersects(search_box)
            
            for seg_id in nearby_ids:
                # Skip if already visited or is the same segment
                if seg_id in visited or seg_id == segment.id():
                    continue
                
                # Skip if already in connected list
                if any(f.id() == seg_id for f in connected):
                    continue
                
                request = QgsFeatureRequest().setFilterFid(seg_id)
                for feat in network_layer.getFeatures(request):
                    feat_geom = feat.geometry()
                    if not feat_geom or feat_geom.isEmpty():
                        continue
                    
                    # Get endpoints of candidate segment
                    if feat_geom.isMultipart():
                        feat_polylines = feat_geom.asMultiPolyline()
                        if feat_polylines:
                            feat_line_points = feat_polylines[0]
                        else:
                            continue
                    else:
                        feat_line_points = feat_geom.asPolyline()
                    
                    if not feat_line_points or len(feat_line_points) < 2:
                        continue
                    
                    feat_start = feat_line_points[0]
                    feat_end = feat_line_points[-1]
                    
                    # Check if any endpoints match (within tolerance)
                    # This handles cases where segments share endpoints but might have slight floating-point differences
                    endpoints_match = False
                    
                    for current_ep in [start_point, end_point]:
                        for feat_ep in [feat_start, feat_end]:
                            distance = math.sqrt(
                                (current_ep.x() - feat_ep.x())**2 + 
                                (current_ep.y() - feat_ep.y())**2
                            )
                            if distance < ENDPOINT_TOLERANCE:
                                endpoints_match = True
                                break
                        if endpoints_match:
                            break
                    
                    if endpoints_match:
                        connected.append(feat)
        
        return connected
    
    def _create_path_geometry(self, path_segments, start_point, end_point):
        """
        Create a continuous path geometry from a list of segments, trimmed to start and end points.
        
        Args:
            path_segments: List of QgsGeometry objects forming the path
            start_point: QgsPointXY of starting point
            end_point: QgsPointXY of ending point
            
        Returns:
            QgsGeometry: Combined path geometry as a valid LineString
        """
        if not path_segments:
            return QgsGeometry.fromPolylineXY([start_point, end_point])
        
        try:
            # Combine all segments
            combined = path_segments[0]
            for seg in path_segments[1:]:
                temp = combined.combine(seg)
                if temp and not temp.isEmpty():
                    combined = temp
            
            # If we have a single segment, extract between the two points
            if len(path_segments) == 1:
                result = self._extract_line_segment_between_points(
                    QgsGeometry.fromPointXY(start_point),
                    QgsGeometry.fromPointXY(end_point),
                    path_segments[0]
                )
                if result:
                    return self._ensure_linestring(result)
            
            # Convert MultiLineString to LineString if needed
            return self._ensure_linestring(combined)
            
        except Exception:
            # Fallback to straight line
            return QgsGeometry.fromPolylineXY([start_point, end_point])
    
    def _ensure_linestring(self, geometry):
        """
        Ensure geometry is a valid LineString (not MultiLineString).
        
        Args:
            geometry: QgsGeometry to convert
            
        Returns:
            QgsGeometry: Valid LineString geometry
        """
        if not geometry or geometry.isEmpty():
            return None
        
        # If it's already a simple LineString, return it
        if geometry.type() == QgsWkbTypes.LineGeometry and not geometry.isMultipart():
            return geometry
        
        # If it's a MultiLineString, merge all parts into a single line
        if geometry.isMultipart():
            # Get all line parts
            multiline = geometry.asMultiPolyline()
            if multiline:
                # Combine all points from all line parts
                all_points = []
                for line in multiline:
                    all_points.extend(line)
                
                # Remove duplicates while preserving order
                unique_points = []
                for pt in all_points:
                    # Check if point already exists (within small tolerance)
                    is_dup = False
                    for existing in unique_points:
                        if abs(pt.x() - existing.x()) < 0.01 and abs(pt.y() - existing.y()) < 0.01:
                            is_dup = True
                            break
                    if not is_dup:
                        unique_points.append(pt)
                
                # Create single LineString from all points
                if len(unique_points) >= 2:
                    return QgsGeometry.fromPolylineXY(unique_points)
        
        # Try to convert using asPolyline
        try:
            line_points = geometry.asPolyline()
            if line_points and len(line_points) >= 2:
                return QgsGeometry.fromPolylineXY(line_points)
        except Exception:
            pass
        
        # If all else fails, return original
        return geometry
    
    def _find_network_path_between_points(self, point1_geom, point2_geom, nearby_network_features, network_layer, network_index, max_distance):
        """
        Find the network path between two points.
        
        This extracts the actual road network geometry between two points,
        ensuring the output follows the road network lines.
        
        Args:
            point1_geom: Geometry of first point
            point2_geom: Geometry of second point
            nearby_network_features: List of nearby network features
            network_layer: Road network layer
            network_index: Spatial index for network
            max_distance: Maximum search distance
            
        Returns:
            QgsGeometry: Network path geometry or None if no valid path exists
        """
        SNAP_TOLERANCE = 100  # Maximum distance to snap point to network segment
        
        # Find closest network segment to each point
        closest_to_point1 = None
        min_dist1 = float('inf')
        snap_point1 = None
        
        for net_feat in nearby_network_features:
            net_geom = net_feat.geometry()
            if not net_geom or net_geom.isEmpty():
                continue
            
            dist = point1_geom.distance(net_geom)
            if dist < min_dist1:
                min_dist1 = dist
                closest_to_point1 = net_feat
                snap_point1 = net_geom.nearestPoint(point1_geom)
        
        # Check if point1 is actually close enough to network
        if not closest_to_point1 or min_dist1 > SNAP_TOLERANCE:
            return None
        
        # Find closest network segment to point2
        closest_to_point2 = None
        min_dist2 = float('inf')
        snap_point2 = None
        
        for net_feat in nearby_network_features:
            net_geom = net_feat.geometry()
            if not net_geom or net_geom.isEmpty():
                continue
            
            dist = point2_geom.distance(net_geom)
            if dist < min_dist2:
                min_dist2 = dist
                closest_to_point2 = net_feat
                snap_point2 = net_geom.nearestPoint(point2_geom)
        
        # Check if point2 is actually close enough to network
        if not closest_to_point2 or min_dist2 > SNAP_TOLERANCE:
            return None
        
        # If both points snap to the same network segment
        if closest_to_point1.id() == closest_to_point2.id():
            # Extract the portion of the line between the two points
            return self._extract_line_segment_between_points(
                snap_point1,
                snap_point2,
                closest_to_point1.geometry()
            )
        
        # If points are on different segments, collect segments between them
        path = self._collect_network_segments_between_points(
            snap_point1,
            snap_point2,
            closest_to_point1,
            closest_to_point2,
            network_layer,
            network_index,
            max_distance
        )
        
        # Return None if no valid path was found
        return path
    
    def _extract_line_segment_between_points(self, point1_geom, point2_geom, line_geom):
        """
        Extract the portion of a line between two points, following the actual line geometry.
        
        Args:
            point1_geom: First point geometry (already snapped to line)
            point2_geom: Second point geometry (already snapped to line)
            line_geom: Line geometry to extract from
            
        Returns:
            QgsGeometry: Extracted line segment following the road geometry
        """
        try:
            # Get the line as polyline (list of points)
            if line_geom.isMultipart():
                polylines = line_geom.asMultiPolyline()
                if not polylines:
                    return line_geom
                line_points = polylines[0]  # Use first part
            else:
                line_points = line_geom.asPolyline()
            
            if not line_points or len(line_points) < 2:
                return line_geom
            
            # Find linear positions of snapped points along the line
            point1_xy = point1_geom.asPoint()
            point2_xy = point2_geom.asPoint()
            
            # Find closest vertices on the line to each point
            min_dist1 = float('inf')
            min_dist2 = float('inf')
            idx1 = 0
            idx2 = 0
            
            for i, vertex in enumerate(line_points):
                dist1 = math.sqrt((vertex.x() - point1_xy.x())**2 + (vertex.y() - point1_xy.y())**2)
                dist2 = math.sqrt((vertex.x() - point2_xy.x())**2 + (vertex.y() - point2_xy.y())**2)
                
                if dist1 < min_dist1:
                    min_dist1 = dist1
                    idx1 = i
                
                if dist2 < min_dist2:
                    min_dist2 = dist2
                    idx2 = i
            
            # Ensure idx1 is before idx2
            if idx1 > idx2:
                idx1, idx2 = idx2, idx1
                point1_xy, point2_xy = point2_xy, point1_xy
            
            # Extract segment between these indices
            if idx1 == idx2:
                # Both points snap to same vertex, create minimal segment
                return QgsGeometry.fromPolylineXY([point1_xy, point2_xy])
            
            # Build the segment with actual line geometry
            segment_points = [point1_xy]  # Start with first point
            
            # Add all intermediate vertices
            for i in range(idx1, idx2 + 1):
                if i < len(line_points):
                    segment_points.append(line_points[i])
            
            # Add second point
            segment_points.append(point2_xy)
            
            # Remove duplicate consecutive points
            cleaned_points = [segment_points[0]]
            for pt in segment_points[1:]:
                if pt != cleaned_points[-1]:
                    cleaned_points.append(pt)
            
            if len(cleaned_points) < 2:
                return QgsGeometry.fromPolylineXY([point1_xy, point2_xy])
            
            return QgsGeometry.fromPolylineXY(cleaned_points)
            
        except Exception as e:
            # Fallback: return original line geometry
            return line_geom
    
    def _collect_network_segments_between_points(self, snap_point1, snap_point2, segment1, segment2, network_layer, network_index, max_distance):
        """
        Collect network segments between two points on different network segments.
        
        This finds network segments that connect the two segments and combines them
        to create a path that follows the actual road network.
        
        Args:
            snap_point1: First point snapped to network
            snap_point2: Second point snapped to network
            segment1: Network feature containing first point
            segment2: Network feature containing second point
            network_layer: Network layer
            network_index: Spatial index
            max_distance: Maximum distance
            
        Returns:
            QgsGeometry: Combined network geometry following roads or None if no valid path
        """
        # Get geometries
        geom1 = segment1.geometry()
        geom2 = segment2.geometry()
        
        point1_xy = snap_point1.asPoint()
        point2_xy = snap_point2.asPoint()
        
        # Tolerance for "being on a segment" in map units - match the SNAP_TOLERANCE
        ON_SEGMENT_TOLERANCE = 100
        
        # Check if segments are connected (share endpoints)
        if geom1.touches(geom2):
            # Segments are directly connected, combine them
            # Extract relevant portions and combine
            partial1 = self._extract_from_point_to_end(snap_point1, geom1)
            partial2 = self._extract_from_start_to_point(snap_point2, geom2)
            
            if partial1 and partial2:
                combined = partial1.combine(partial2)
                if combined and not combined.isEmpty():
                    return combined
        
        # Create bounding box between the two segments
        bbox1 = geom1.boundingBox()
        bbox2 = geom2.boundingBox()
        search_rect = QgsRectangle(bbox1)
        search_rect.combineExtentWith(bbox2)
        search_rect.grow(100)  # Add buffer
        
        # Find all segments that might connect them
        candidate_ids = network_index.intersects(search_rect)
        
        # Collect segments that are actually part of the path between points
        # Only include segments where at least one of the points is near
        path_segments = []
        
        # Always include the segments containing the points
        path_segments.append(geom1)
        path_segments.append(geom2)
        
        for seg_id in candidate_ids:
            if seg_id == segment1.id() or seg_id == segment2.id():
                continue
                
            request = QgsFeatureRequest().setFilterFid(seg_id)
            for feat in network_layer.getFeatures(request):
                seg_geom = feat.geometry()
                if seg_geom and not seg_geom.isEmpty():
                    # Check if this segment is actually on the path between points
                    # It should either:
                    # 1. Touch one of the existing segments (forms connected path)
                    # 2. Be very close to both points (intermediate segment)
                    
                    dist_to_point1 = snap_point1.distance(seg_geom)
                    dist_to_point2 = snap_point2.distance(seg_geom)
                    
                    # Include if segment touches existing path segments
                    connects_to_path = False
                    if seg_geom.touches(geom1) or seg_geom.touches(geom2):
                        connects_to_path = True
                    
                    # Include if segment is close to both points (intermediate segment)
                    if dist_to_point1 < ON_SEGMENT_TOLERANCE and dist_to_point2 < ON_SEGMENT_TOLERANCE:
                        connects_to_path = True
                    
                    # Only add if it connects to the path
                    if connects_to_path:
                        path_segments.append(seg_geom)
        
        # Validate that we actually have a path between the two points
        # Combine all segments
        if len(path_segments) < 2:
            return None  # Not enough segments to form a path
        
        combined = path_segments[0]
        for seg in path_segments[1:]:
            temp = combined.combine(seg)
            if temp and not temp.isEmpty():
                combined = temp
        
        # Final validation: check that both points are actually close to the combined geometry
        # This prevents including dead-end roads
        dist1 = snap_point1.distance(combined)
        dist2 = snap_point2.distance(combined)
        
        # If either point is too far from the combined path, it's invalid
        if dist1 > ON_SEGMENT_TOLERANCE or dist2 > ON_SEGMENT_TOLERANCE:
            return None
        
        # Check that the combined path length is reasonable (not too much longer than straight line)
        straight_line_dist = snap_point1.distance(snap_point2)
        if combined.length() > straight_line_dist * 10:  # Path is way too long
            return None
        
        return combined
    
    def _extract_from_point_to_end(self, point_geom, line_geom):
        """Extract line geometry from a point to the end of the line."""
        try:
            line_points = line_geom.asPolyline() if not line_geom.isMultipart() else line_geom.asMultiPolyline()[0]
            point_xy = point_geom.asPoint()
            
            # Find closest vertex
            min_dist = float('inf')
            closest_idx = 0
            for i, vertex in enumerate(line_points):
                dist = math.sqrt((vertex.x() - point_xy.x())**2 + (vertex.y() - point_xy.y())**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i
            
            # Extract from this point to end
            segment_points = [point_xy] + line_points[closest_idx:]
            return QgsGeometry.fromPolylineXY(segment_points) if len(segment_points) >= 2 else line_geom
        except:
            return line_geom
    
    def _extract_from_start_to_point(self, point_geom, line_geom):
        """Extract line geometry from the start to a point."""
        try:
            line_points = line_geom.asPolyline() if not line_geom.isMultipart() else line_geom.asMultiPolyline()[0]
            point_xy = point_geom.asPoint()
            
            # Find closest vertex
            min_dist = float('inf')
            closest_idx = 0
            for i, vertex in enumerate(line_points):
                dist = math.sqrt((vertex.x() - point_xy.x())**2 + (vertex.y() - point_xy.y())**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i
            
            # Extract from start to this point
            segment_points = line_points[:closest_idx + 1] + [point_xy]
            return QgsGeometry.fromPolylineXY(segment_points) if len(segment_points) >= 2 else line_geom
        except:
            return line_geom
    
    def _distance_to_line_segment(self, point, line_start, line_end):
        """Calculate distance from a point to a line segment."""
        # Vector from line_start to line_end
        dx = line_end.x() - line_start.x()
        dy = line_end.y() - line_start.y()
        
        if dx == 0 and dy == 0:
            # Line segment is a point
            return math.sqrt((point.x() - line_start.x())**2 + (point.y() - line_start.y())**2)
        
        # Parameter t of the projection
        t = ((point.x() - line_start.x()) * dx + (point.y() - line_start.y()) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))  # Clamp to [0, 1]
        
        # Closest point on line segment
        closest_x = line_start.x() + t * dx
        closest_y = line_start.y() + t * dy
        
        # Distance from point to closest point
        return math.sqrt((point.x() - closest_x)**2 + (point.y() - closest_y)**2)
    
    def _add_connections_to_layer(self, layer, connections, decimal_places, progress=None):
        """
        Add connection features to the layer.
        
        Args:
            layer (QgsVectorLayer): Layer to add connections to
            connections (list): List of connection dictionaries
            decimal_places (int): Decimal places for distance values
            progress (QProgressDialog): Optional progress dialog
        
        Returns:
            bool: True if successful, False if cancelled
        """
        layer.startEditing()
        
        total_connections = len(connections)
        skipped_count = 0
        
        for idx, conn in enumerate(connections):
            # Process events and check for cancellation
            if progress and idx % 50 == 0:  # Check every 50 features
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    layer.rollBack()
                    return False
                # Update progress (small increment within the 70-90 range)
                if total_connections > 0:
                    sub_progress = 70 + int((idx / total_connections) * 20)
                    progress.setValue(sub_progress)
            
            geom = conn['geometry']
            
            # Validate and ensure geometry is a LineString
            if not geom or geom.isEmpty():
                skipped_count += 1
                continue
            
            # Convert to LineString if needed
            geom = self._ensure_linestring(geom)
            
            # Final validation
            if not geom or geom.isEmpty():
                skipped_count += 1
                continue
            
            # Check geometry type matches layer
            if geom.type() != QgsWkbTypes.LineGeometry:
                skipped_count += 1
                continue
            
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geom)
            
            # Set attributes
            feature['from_point'] = conn['from_point']
            feature['to_point'] = conn['to_point']
            
            if 'distance' in layer.fields().names():
                feature['distance'] = round(conn['distance'], decimal_places)
            
            layer.addFeature(feature)
        
        if skipped_count > 0:
            QgsMessageLog.logMessage(
                f"Skipped {skipped_count} connections due to invalid geometry",
                "RightClick Actions",
                Qgis.Warning
            )
        
        layer.commitChanges()
        return True


# REQUIRED: Create global instance for automatic discovery
extract_network_connections_between_points_line = ExtractNetworkConnectionsBetweenPointsLineAction()
