"""
Check CRS for All Layers Action for Right-click Utilities and Shortcuts Hub

Displays a window showing all available layers and their CRS information.
Highlights layers in red if their CRS doesn't match the project CRS.
Allows users to change CRS directly in the dialog and save changes.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsCoordinateReferenceSystem, QgsVectorLayer, QgsRasterLayer
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                                QTableWidgetItem, QPushButton, QLabel, QHeaderView,
                                QMessageBox, QFrame, QComboBox, QCheckBox, QGroupBox,
                                QGridLayout, QSpacerItem, QSizePolicy)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from ..history_manager import get_history_manager
from qgis.PyQt.QtGui import QFont, QColor, QPalette


class CheckCrsAllLayersAction(BaseAction):
    """
    Action to check CRS for all layers and display them in a window.
    
    This action shows all available layers in the project with their CRS information.
    Layers with CRS that doesn't match the project CRS are highlighted in red.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "check_crs_all_layers"
        self.name = "Check CRS for All Layers"
        self.category = "Information"
        self.description = "Display a window showing all available layers and their CRS information. Layers with CRS that doesn't match the project CRS are highlighted in red. Allows editing CRS directly in the dialog with save/discard functionality for easy CRS management."
        self.enabled = True
        
        # Action scoping - universal action that works everywhere
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - works everywhere
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['universal'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'show_crs_details': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Details',
                'description': 'Display detailed CRS information including EPSG code and description',
            },
            'highlight_mismatched': {
                'type': 'bool',
                'default': True,
                'label': 'Highlight Mismatched CRS',
                'description': 'Highlight layers with CRS that doesn\'t match project CRS in red',
            },
            'include_raster_layers': {
                'type': 'bool',
                'default': True,
                'label': 'Include Raster Layers',
                'description': 'Include raster layers in the CRS check (in addition to vector layers)',
            },
            'show_layer_count': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Count',
                'description': 'Display the total number of features/features in each layer',
            },
            'allow_crs_editing': {
                'type': 'bool',
                'default': True,
                'label': 'Allow CRS Editing',
                'description': 'Enable CRS editing functionality in the dialog',
            },
            'confirm_crs_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm CRS Changes',
                'description': 'Show confirmation dialog before applying CRS changes to layers',
            },
            'auto_save_changes': {
                'type': 'bool',
                'default': False,
                'label': 'Auto Save Changes',
                'description': 'Automatically save CRS changes without confirmation (use with caution)',
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
        Execute the CRS check action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            show_crs_details = bool(self.get_setting('show_crs_details', True))
            highlight_mismatched = bool(self.get_setting('highlight_mismatched', True))
            include_raster_layers = bool(self.get_setting('include_raster_layers', True))
            show_layer_count = bool(self.get_setting('show_layer_count', True))
            allow_crs_editing = bool(self.get_setting('allow_crs_editing', True))
            confirm_crs_changes = bool(self.get_setting('confirm_crs_changes', True))
            auto_save_changes = bool(self.get_setting('auto_save_changes', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        try:
            # Get project and canvas
            project = QgsProject.instance()
            canvas = context.get('canvas')
            
            if not canvas:
                self.show_error("Error", "Could not access map canvas")
                return
            
            # Get project CRS
            project_crs = canvas.mapSettings().destinationCrs()
            
            # Get all layers
            layers = project.mapLayers().values()
            
            if not layers:
                self.show_warning("No Layers", "No layers found in the project.")
                return
            
            # Filter layers based on settings
            filtered_layers = []
            for layer in layers:
                if not layer.isValid():
                    continue
                
                # Check if we should include this layer type
                if not include_raster_layers and layer.type() == layer.RasterLayer:
                    continue
                
                filtered_layers.append(layer)
            
            if not filtered_layers:
                self.show_warning("No Valid Layers", "No valid layers found in the project.")
                return
            
            # Create and show the CRS check dialog
            dialog = CrsCheckDialog(filtered_layers, project_crs, show_crs_details, 
                                  highlight_mismatched, show_layer_count, allow_crs_editing,
                                  confirm_crs_changes, auto_save_changes)
            dialog.exec_()
            
        except Exception as e:
            self.show_error("Error", f"Failed to check CRS: {str(e)}")


class CrsCheckDialog(QDialog):
    """Dialog to display CRS information for all layers with editing capabilities."""
    
    def __init__(self, layers, project_crs, show_crs_details, highlight_mismatched, show_layer_count, 
                 allow_crs_editing, confirm_crs_changes, auto_save_changes):
        """
        Initialize the CRS check dialog.
        
        Args:
            layers: List of QGIS layers
            project_crs: Project CRS
            show_crs_details: Whether to show detailed CRS information
            highlight_mismatched: Whether to highlight mismatched CRS
            show_layer_count: Whether to show layer feature count
            allow_crs_editing: Whether to allow CRS editing
            confirm_crs_changes: Whether to confirm CRS changes
            auto_save_changes: Whether to auto-save changes
        """
        super().__init__()
        self.layers = layers
        self.project_crs = project_crs
        self.show_crs_details = show_crs_details
        self.highlight_mismatched = highlight_mismatched
        self.show_layer_count = show_layer_count
        self.allow_crs_editing = allow_crs_editing
        self.confirm_crs_changes = confirm_crs_changes
        self.auto_save_changes = auto_save_changes
        
        # Track pending changes
        self.pending_changes = {}  # layer_id -> new_crs
        
        self.setWindowTitle("CRS Check & Edit - All Layers")
        self.setModal(True)
        self.resize(1000, 700)
        
        self.setup_ui()
        self.populate_table()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        
        # Title and project CRS info
        title_label = QLabel("Coordinate Reference System Check & Edit")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Project CRS information
        project_crs_label = QLabel(f"Project CRS: {self.project_crs.description()}")
        if self.show_crs_details:
            project_crs_label.setText(f"Project CRS: {self.project_crs.description()} (EPSG:{self.project_crs.authid()})")
        project_crs_label.setStyleSheet("font-weight: bold; color: #2E8B57;")
        layout.addWidget(project_crs_label)
        
        # Summary information
        self.summary_label = QLabel()
        self.update_summary()
        self.summary_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.summary_label)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Table for layer information
        self.table = QTableWidget()
        if self.allow_crs_editing:
            self.table.setColumnCount(6)
            self.table.setHorizontalHeaderLabels([
                "Layer Name", "Layer Type", "Current CRS", "New CRS", "Feature Count", "Status"
            ])
        else:
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels([
                "Layer Name", "Layer Type", "CRS", "Feature Count", "Status"
            ])
        
        # Set table properties
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        if self.allow_crs_editing:
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        else:
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_data)
        
        if self.allow_crs_editing:
            self.save_changes_button = QPushButton("Save Changes")
            self.save_changes_button.clicked.connect(self.save_changes)
            self.save_changes_button.setEnabled(False)
            self.save_changes_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
            
            self.discard_changes_button = QPushButton("Discard Changes")
            self.discard_changes_button.clicked.connect(self.discard_changes)
            self.discard_changes_button.setEnabled(False)
            self.discard_changes_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
            
            button_layout.addWidget(self.refresh_button)
            button_layout.addWidget(self.discard_changes_button)
            button_layout.addStretch()
            button_layout.addWidget(self.save_changes_button)
        else:
            button_layout.addWidget(self.refresh_button)
            button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def populate_table(self):
        """Populate the table with layer information."""
        self.table.setRowCount(len(self.layers))
        
        for row, layer in enumerate(self.layers):
            # Layer name
            name_item = QTableWidgetItem(layer.name())
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            
            # Layer type
            layer_type = "Vector" if layer.type() == layer.VectorLayer else "Raster"
            type_item = QTableWidgetItem(layer_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, type_item)
            
            # Current CRS information
            layer_crs = layer.crs()
            if self.show_crs_details:
                crs_text = f"{layer_crs.description()} (EPSG:{layer_crs.authid()})"
            else:
                crs_text = layer_crs.description()
            
            crs_item = QTableWidgetItem(crs_text)
            crs_item.setFlags(crs_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, crs_item)
            
            # New CRS column (if editing is enabled)
            if self.allow_crs_editing:
                crs_combo = QComboBox()
                crs_combo.setEditable(True)
                crs_combo.setInsertPolicy(QComboBox.NoInsert)
                
                # Populate with common CRS options
                self.populate_crs_combo(crs_combo, layer_crs)
                
                # Connect signal to track changes
                crs_combo.currentTextChanged.connect(lambda text, layer_id=layer.id(): self.on_crs_changed(layer_id, text))
                
                self.table.setCellWidget(row, 3, crs_combo)
                
                # Feature count column
                count_col = 4
                status_col = 5
            else:
                count_col = 3
                status_col = 4
            
            # Feature count
            if self.show_layer_count:
                if layer.type() == layer.VectorLayer:
                    count = layer.featureCount()
                    count_text = str(count) if count >= 0 else "Unknown"
                else:
                    count_text = "N/A"
            else:
                count_text = "Hidden"
            
            count_item = QTableWidgetItem(count_text)
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, count_col, count_item)
            
            # Status
            self.update_row_status(row, layer, status_col)
            
            # Highlight entire row if CRS doesn't match
            crs_matches = layer_crs == self.project_crs
            if self.highlight_mismatched and not crs_matches:
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(QColor(255, 240, 240))  # Light red background
    
    def update_summary(self):
        """Update the summary information."""
        total_layers = len(self.layers)
        mismatched_count = sum(1 for layer in self.layers if layer.crs() != self.project_crs)
        
        summary_text = f"Total Layers: {total_layers}"
        if mismatched_count > 0:
            summary_text += f" | Mismatched CRS: {mismatched_count}"
        else:
            summary_text += " | All layers match project CRS ✓"
        
        if self.allow_crs_editing and self.pending_changes:
            summary_text += f" | Pending Changes: {len(self.pending_changes)}"
        
        self.summary_label.setText(summary_text)
    
    def populate_crs_combo(self, combo, current_crs):
        """Populate a CRS combo box with common options."""
        # Common CRS options
        common_crs = [
            ("EPSG:4326", "WGS 84"),
            ("EPSG:3857", "WGS 84 / Pseudo-Mercator"),
            ("EPSG:32633", "WGS 84 / UTM zone 33N"),
            ("EPSG:32634", "WGS 84 / UTM zone 34N"),
            ("EPSG:32635", "WGS 84 / UTM zone 35N"),
            ("EPSG:32636", "WGS 84 / UTM zone 36N"),
            ("EPSG:32637", "WGS 84 / UTM zone 37N"),
            ("EPSG:32638", "WGS 84 / UTM zone 38N"),
            ("EPSG:32639", "WGS 84 / UTM zone 39N"),
            ("EPSG:32640", "WGS 84 / UTM zone 40N"),
            ("EPSG:32641", "WGS 84 / UTM zone 41N"),
            ("EPSG:32642", "WGS 84 / UTM zone 42N"),
            ("EPSG:32643", "WGS 84 / UTM zone 43N"),
            ("EPSG:32644", "WGS 84 / UTM zone 44N"),
            ("EPSG:32645", "WGS 84 / UTM zone 45N"),
            ("EPSG:32646", "WGS 84 / UTM zone 46N"),
            ("EPSG:32647", "WGS 84 / UTM zone 47N"),
            ("EPSG:32648", "WGS 84 / UTM zone 48N"),
            ("EPSG:32649", "WGS 84 / UTM zone 49N"),
            ("EPSG:32650", "WGS 84 / UTM zone 50N"),
            ("EPSG:32651", "WGS 84 / UTM zone 51N"),
            ("EPSG:32652", "WGS 84 / UTM zone 52N"),
            ("EPSG:32653", "WGS 84 / UTM zone 53N"),
            ("EPSG:32654", "WGS 84 / UTM zone 54N"),
            ("EPSG:32655", "WGS 84 / UTM zone 55N"),
            ("EPSG:32656", "WGS 84 / UTM zone 56N"),
            ("EPSG:32657", "WGS 84 / UTM zone 57N"),
            ("EPSG:32658", "WGS 84 / UTM zone 58N"),
            ("EPSG:32659", "WGS 84 / UTM zone 59N"),
            ("EPSG:32660", "WGS 84 / UTM zone 60N"),
        ]
        
        # Add current CRS first
        current_text = f"{current_crs.description()} (EPSG:{current_crs.authid()})"
        combo.addItem(current_text, current_crs.authid())
        
        # Add project CRS if different
        if current_crs != self.project_crs:
            project_text = f"{self.project_crs.description()} (EPSG:{self.project_crs.authid()})"
            combo.addItem(project_text, self.project_crs.authid())
        
        # Add separator
        combo.addItem("───────────────", "")
        
        # Add common CRS options
        for authid, description in common_crs:
            if authid != current_crs.authid() and authid != self.project_crs.authid():
                combo.addItem(f"{description} ({authid})", authid)
    
    def on_crs_changed(self, layer_id, text):
        """Handle CRS change in combo box."""
        if not text or text == "───────────────":
            return
        
        # Extract EPSG code from text
        epsg_code = None
        if "EPSG:" in text:
            epsg_code = text.split("EPSG:")[-1].split(")")[0]
        elif text.startswith("EPSG:"):
            epsg_code = text.split("EPSG:")[1]
        
        if epsg_code:
            try:
                new_crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg_code}")
                if new_crs.isValid():
                    self.pending_changes[layer_id] = new_crs
                    self.update_buttons_state()
                    self.update_summary()
                    
                    # Update status for this row
                    for row in range(self.table.rowCount()):
                        layer = self.layers[row]
                        if layer.id() == layer_id:
                            self.update_row_status(row, layer, 5 if self.allow_crs_editing else 4)
                            break
            except Exception as e:
                QMessageBox.warning(self, "Invalid CRS", f"Invalid CRS code: {epsg_code}")
    
    def update_row_status(self, row, layer, status_col):
        """Update the status column for a specific row."""
        layer_crs = layer.crs()
        pending_crs = self.pending_changes.get(layer.id())
        
        if pending_crs:
            if pending_crs == self.project_crs:
                status_text = "✓ Will Match"
                status_color = QColor(34, 139, 34)  # Green
            else:
                status_text = "⚠ Changed"
                status_color = QColor(255, 165, 0)  # Orange
        else:
            crs_matches = layer_crs == self.project_crs
            if crs_matches:
                status_text = "✓ Match"
                status_color = QColor(34, 139, 34)  # Green
            else:
                status_text = "✗ Mismatch"
                status_color = QColor(220, 20, 60)  # Red
        
        status_item = QTableWidgetItem(status_text)
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        status_item.setForeground(status_color)
        self.table.setItem(row, status_col, status_item)
    
    def update_buttons_state(self):
        """Update the state of save/discard buttons."""
        if not self.allow_crs_editing:
            return
        
        has_changes = len(self.pending_changes) > 0
        self.save_changes_button.setEnabled(has_changes)
        self.discard_changes_button.setEnabled(has_changes)
    
    def refresh_data(self):
        """Refresh the table data."""
        # Clear pending changes
        self.pending_changes.clear()
        
        # Re-get layers from project
        project = QgsProject.instance()
        self.layers = list(project.mapLayers().values())
        
        # Filter out invalid layers
        self.layers = [layer for layer in self.layers if layer.isValid()]
        
        # Repopulate table
        self.populate_table()
        
        # Update summary and buttons
        self.update_summary()
        self.update_buttons_state()
    
    def save_changes(self):
        """Save all pending CRS changes to layers."""
        if not self.pending_changes:
            return
        
        # Show confirmation if enabled
        if self.confirm_crs_changes:
            changes_text = "\n".join([f"• {self.get_layer_name(layer_id)}: {self.pending_changes[layer_id].description()}" 
                                    for layer_id in self.pending_changes])
            
            reply = QMessageBox.question(
                self, 
                "Confirm CRS Changes", 
                f"Are you sure you want to change the CRS for the following layers?\n\n{changes_text}\n\nThis action cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
        
        # Apply changes
        success_count = 0
        error_count = 0
        errors = []
        changed_layers = []

        # Try to get history manager for informational logging (non-undoable)
        try:
            hm = get_history_manager()
        except Exception:
            hm = None

        for layer_id, new_crs in self.pending_changes.items():
            try:
                layer = self.get_layer_by_id(layer_id)
                if layer:
                    # Capture old CRS for logging
                    try:
                        old_crs = layer.crs().authid() if layer.crs() and layer.crs().isValid() else ''
                    except Exception:
                        old_crs = ''

                    # Set the new CRS
                    layer.setCrs(new_crs)

                    # Track for informational history
                    try:
                        changed_layers.append({
                            'layer_id': layer.id(),
                            'layer_name': layer.name(),
                            'from_crs': old_crs,
                            'to_crs': new_crs.authid() if hasattr(new_crs, 'authid') else str(new_crs)
                        })
                    except Exception:
                        pass

                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"Layer with ID {layer_id} not found")
            except Exception as e:
                error_count += 1
                errors.append(f"Error changing CRS for layer {self.get_layer_name(layer_id)}: {str(e)}")

        # Record informational (non-undoable) history entry summarizing the changes
        if hm:
            try:
                meta = {
                    'changed_layers': changed_layers,
                    'success_count': success_count,
                    'error_count': error_count,
                    'errors': errors,
                }

                hm.record_informational(
                    action_id='check_crs_all_layers',
                    action_name='Check CRS for All Layers',
                    description=f"Changed CRS for {len(changed_layers)} layer(s)",
                    meta=meta
                )
            except Exception:
                # Do not let history recording break behavior
                pass
        
        # Show result
        if error_count == 0:
            QMessageBox.information(self, "Success", f"Successfully changed CRS for {success_count} layer(s).")
        else:
            error_text = "\n".join(errors)
            QMessageBox.warning(self, "Partial Success", 
                              f"Changed CRS for {success_count} layer(s).\n\nErrors:\n{error_text}")
        
        # Clear pending changes and refresh
        self.pending_changes.clear()
        self.refresh_data()
    
    def discard_changes(self):
        """Discard all pending CRS changes."""
        if not self.pending_changes:
            return
        
        reply = QMessageBox.question(
            self, 
            "Discard Changes", 
            f"Are you sure you want to discard {len(self.pending_changes)} pending CRS change(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.pending_changes.clear()
            self.refresh_data()
    
    def get_layer_name(self, layer_id):
        """Get layer name by ID."""
        for layer in self.layers:
            if layer.id() == layer_id:
                return layer.name()
        return f"Layer {layer_id}"
    
    def get_layer_by_id(self, layer_id):
        """Get layer by ID."""
        for layer in self.layers:
            if layer.id() == layer_id:
                return layer
        return None


# REQUIRED: Create global instance for automatic discovery
check_crs_all_layers = CheckCrsAllLayersAction()
