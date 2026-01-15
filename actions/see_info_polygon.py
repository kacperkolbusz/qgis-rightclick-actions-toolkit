"""
See Info Polygon Action for Right-click Utilities and Shortcuts Hub

Displays comprehensive information about the selected polygon feature, including
geometry details, attributes, layer information, and any available audit data.
"""

from .base_action import BaseAction
from qgis.core import QgsFeature, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel, QScrollArea, QWidget
)
from qgis.PyQt.QtCore import Qt
from datetime import datetime


class InfoViewerDialog(QDialog):
    """Dialog for displaying feature information."""
    
    def __init__(self, parent=None, info_text=""):
        super().__init__(parent)
        self.setWindowTitle("Feature Information")
        self.setModal(True)
        self.resize(700, 500)
        
        layout = QVBoxLayout()
        
        # Info text display
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setPlainText(info_text)
        self.info_text.setFontFamily("Courier")
        self.info_text.setFontPointSize(9)
        layout.addWidget(self.info_text)
        
        # Buttons
        button_layout = QVBoxLayout()
        
        # Copy button
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(copy_button)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def copy_to_clipboard(self):
        """Copy info text to clipboard."""
        from qgis.PyQt.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.info_text.toPlainText())


class SeeInfoPolygonAction(BaseAction):
    """
    Action to display comprehensive information about polygon features.
    
    Shows detailed feature information including geometry details, attributes,
    layer information, and any available audit data.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "see_info_polygon"
        self.name = "See Info"
        self.category = "Information"
        self.description = "Display comprehensive information about the selected polygon feature, including geometry details, attributes, layer information, and any available audit data."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygon features
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # DISPLAY SETTINGS
            'show_creation_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Creation Info',
                'description': 'Display creation date/time and creator information if available',
            },
            'show_modification_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show Modification Info',
                'description': 'Display modification date/time and modifier information if available',
            },
            'show_audit_fields': {
                'type': 'bool',
                'default': True,
                'label': 'Show Audit Fields',
                'description': 'Display audit fields (created_at, modified_at, created_by, etc.) if present',
            },
            'show_edit_buffer_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Show Edit Buffer Changes',
                'description': 'Display pending changes in edit buffer if layer is in edit mode',
            },
            'show_current_state': {
                'type': 'bool',
                'default': True,
                'label': 'Show Current State',
                'description': 'Display current feature state (attributes, geometry info)',
            },
            'show_geometry_history': {
                'type': 'bool',
                'default': True,
                'label': 'Show Geometry History',
                'description': 'Display geometry information (area, perimeter, vertex count, etc.)',
            },
            'show_attribute_history': {
                'type': 'bool',
                'default': True,
                'label': 'Show Attribute History',
                'description': 'Display all attribute values and their history if available',
            },
            
            # FORMAT SETTINGS
            'date_format': {
                'type': 'str',
                'default': '%Y-%m-%d %H:%M:%S',
                'label': 'Date Format',
                'description': 'Format string for displaying dates (Python strftime format)',
            },
            'show_timestamps': {
                'type': 'bool',
                'default': True,
                'label': 'Show Timestamps',
                'description': 'Display timestamps in history information',
            },
            'show_field_names': {
                'type': 'bool',
                'default': True,
                'label': 'Show Field Names',
                'description': 'Display field names along with values',
            },
            
            # BEHAVIOR SETTINGS
            'open_in_dialog': {
                'type': 'bool',
                'default': True,
                'label': 'Open in Dialog',
                'description': 'Open history in a dialog window. If disabled, shows in information message.',
            },
            'copy_to_clipboard': {
                'type': 'bool',
                'default': False,
                'label': 'Copy to Clipboard',
                'description': 'Automatically copy history to clipboard when displayed',
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
        Execute the see info action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            show_creation_info = bool(self.get_setting('show_creation_info', True))
            show_modification_info = bool(self.get_setting('show_modification_info', True))
            show_audit_fields = bool(self.get_setting('show_audit_fields', True))
            show_edit_buffer = bool(self.get_setting('show_edit_buffer_changes', True))
            show_current_state = bool(self.get_setting('show_current_state', True))
            show_geometry_history = bool(self.get_setting('show_geometry_history', True))
            show_attribute_history = bool(self.get_setting('show_attribute_history', True))
            date_format = str(self.get_setting('date_format', '%Y-%m-%d %H:%M:%S'))
            show_timestamps = bool(self.get_setting('show_timestamps', True))
            show_field_names = bool(self.get_setting('show_field_names', True))
            open_in_dialog = bool(self.get_setting('open_in_dialog', True))
            copy_to_clipboard = bool(self.get_setting('copy_to_clipboard', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Validate that this is a polygon feature
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon features")
            return
        
        try:
            # Build info text
            info_text = self._build_info_text(
                feature, layer,
                show_creation_info, show_modification_info, show_audit_fields,
                show_edit_buffer, show_current_state, show_geometry_history,
                show_attribute_history, date_format, show_timestamps, show_field_names
            )
            
            # Display info
            if open_in_dialog:
                dialog = InfoViewerDialog(None, info_text)
                if copy_to_clipboard:
                    from qgis.PyQt.QtWidgets import QApplication
                    clipboard = QApplication.clipboard()
                    clipboard.setText(info_text)
                dialog.exec_()
            else:
                self.show_info("Feature Information", info_text)
                if copy_to_clipboard:
                    from qgis.PyQt.QtWidgets import QApplication
                    clipboard = QApplication.clipboard()
                    clipboard.setText(info_text)
            
        except Exception as e:
            self.show_error("Error", f"Failed to retrieve feature information: {str(e)}")
    
    def _build_info_text(self, feature, layer, show_creation_info, show_modification_info,
                           show_audit_fields, show_edit_buffer, show_current_state,
                           show_geometry_history, show_attribute_history, date_format,
                           show_timestamps, show_field_names):
        """
        Build formatted info text for the feature.
        
        Args:
            feature (QgsFeature): Feature to get info for
            layer (QgsVectorLayer): Layer containing the feature
            show_* (bool): Flags for what to include
            date_format (str): Date format string
            show_timestamps (bool): Whether to show timestamps
            show_field_names (bool): Whether to show field names
            
        Returns:
            str: Formatted info text
        """
        lines = []
        lines.append("=" * 70)
        lines.append("FEATURE INFORMATION")
        lines.append("=" * 70)
        lines.append("")
        
        # Basic feature info
        lines.append(f"Feature ID: {feature.id()}")
        lines.append(f"Layer: {layer.name()}")
        lines.append(f"Layer Source: {layer.source()}")
        lines.append("")
        
        # Current timestamp
        if show_timestamps:
            current_time = datetime.now().strftime(date_format)
            lines.append(f"Information Retrieved: {current_time}")
            lines.append("")
        
        # Creation info - only show if data exists
        if show_creation_info:
            creation_info = self._get_creation_info(feature, layer, date_format, show_field_names)
            if creation_info:
                lines.append("-" * 70)
                lines.append("CREATION INFORMATION")
                lines.append("-" * 70)
                lines.append(creation_info)
                lines.append("")
        
        # Modification info - only show if data exists
        if show_modification_info:
            modification_info = self._get_modification_info(feature, layer, date_format, show_field_names)
            if modification_info:
                lines.append("-" * 70)
                lines.append("MODIFICATION INFORMATION")
                lines.append("-" * 70)
                lines.append(modification_info)
                lines.append("")
        
        # Audit fields - only show if data exists
        if show_audit_fields:
            audit_info = self._get_audit_fields(feature, layer, date_format, show_field_names)
            if audit_info:
                lines.append("-" * 70)
                lines.append("AUDIT FIELDS")
                lines.append("-" * 70)
                lines.append(audit_info)
                lines.append("")
        
        # Edit buffer changes
        if show_edit_buffer and layer.isEditable():
            lines.append("-" * 70)
            lines.append("PENDING CHANGES (Edit Buffer)")
            lines.append("-" * 70)
            edit_buffer_info = self._get_edit_buffer_info(feature, layer, show_field_names)
            if edit_buffer_info:
                lines.append(edit_buffer_info)
            else:
                lines.append("No pending changes in edit buffer.")
            lines.append("")
        
        # Current state - Geometry (always show, more detailed)
        if show_current_state and show_geometry_history:
            lines.append("-" * 70)
            lines.append("GEOMETRY INFORMATION")
            lines.append("-" * 70)
            geometry_info = self._get_geometry_info(feature, layer, show_field_names)
            if geometry_info:
                lines.append(geometry_info)
            lines.append("")
        
        # Current state - Attributes (always show, more detailed)
        if show_current_state and show_attribute_history:
            lines.append("-" * 70)
            lines.append("ATTRIBUTE INFORMATION")
            lines.append("-" * 70)
            attribute_info = self._get_attribute_info(feature, layer, show_field_names)
            if attribute_info:
                lines.append(attribute_info)
            lines.append("")
        
        # Layer metadata (more detailed)
        lines.append("-" * 70)
        lines.append("LAYER INFORMATION")
        lines.append("-" * 70)
        lines.append(f"Layer Name: {layer.name()}")
        lines.append(f"Layer ID: {layer.id()}")
        lines.append(f"Data Source: {layer.source()}")
        lines.append(f"Data Provider: {layer.dataProvider().name()}")
        lines.append("")
        crs = layer.crs()
        lines.append(f"CRS: {crs.authid()}")
        lines.append(f"CRS Description: {crs.description()}")
        try:
            if crs.isGeographic():
                unit_name = "degrees"
            elif crs.isValid() and crs.mapUnits() != 0:
                unit_name = crs.mapUnits().name().lower()
            else:
                unit_name = "unknown"
            lines.append(f"CRS Units: {unit_name}")
        except:
            lines.append(f"CRS Units: unknown")
        lines.append("")
        lines.append(f"Feature Count: {layer.featureCount()}")
        lines.append(f"Total Fields: {len(layer.fields())}")
        lines.append(f"Geometry Type: {layer.geometryType()}")
        lines.append(f"Editable: {layer.isEditable()}")
        lines.append(f"Read Only: {layer.readOnly()}")
        lines.append(f"Valid: {layer.isValid()}")
        if hasattr(layer, 'crsTransformContext'):
            lines.append(f"Has CRS Transform: {layer.crsTransformContext().isValid()}")
        lines.append("")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def _get_creation_info(self, feature, layer, date_format, show_field_names):
        """Get creation information from feature."""
        info_lines = []
        
        # Check for common creation fields (case-insensitive)
        creation_field_patterns = ['created', 'creation', 'create', 'date_created', 'date_create',
                                  'created_by', 'creator', 'created_user', 'user_created',
                                  'created_at', 'created_date', 'creation_date',
                                  'date_added', 'added_date', 'added_at', 'add_date',
                                  'insert', 'inserted', 'insert_date', 'inserted_at',
                                  'origin', 'original', 'orig_date', 'origin_date']
        
        fields = layer.fields()
        found_fields = set()
        
        # Search all fields for creation-related patterns
        for field in fields:
            field_name_lower = field.name().lower()
            field_name = field.name()
            
            # Check if field name matches any creation pattern
            for pattern in creation_field_patterns:
                if pattern in field_name_lower and field_name not in found_fields:
                    value = feature.attribute(field_name)
                    if value and str(value).strip():
                        found_fields.add(field_name)
                        if show_field_names:
                            info_lines.append(f"{field_name}: {value}")
                        else:
                            info_lines.append(f"Created: {value}")
                        break
        
        # Also check for date/time fields that might be creation dates
        date_fields = []
        for field in fields:
            field_type = field.type()
            field_name = field.name()
            # Check for date/time field types
            if field_type in [14, 15, 16, 17, 18]:  # Date, Time, DateTime types
                value = feature.attribute(field_name)
                if value and str(value).strip():
                    date_fields.append((field_name, value))
        
        # If we found date fields but no creation info, check if any look like creation dates
        if not info_lines and date_fields:
            # Check field names for creation hints
            for field_name, value in date_fields:
                field_name_lower = field_name.lower()
                if any(hint in field_name_lower for hint in ['create', 'add', 'insert', 'origin', 'first']):
                    if field_name not in found_fields:
                        found_fields.add(field_name)
                        if show_field_names:
                            info_lines.append(f"{field_name}: {value}")
                        else:
                            info_lines.append(f"Created: {value}")
        
        # Check for version field (might indicate creation)
        version_field = layer.fields().indexFromName('version')
        if version_field >= 0:
            version = feature.attribute(version_field)
            if version:
                info_lines.append(f"Version: {version}")
        
        return "\n".join(info_lines) if info_lines else None
    
    def _get_modification_info(self, feature, layer, date_format, show_field_names):
        """Get modification information from feature."""
        info_lines = []
        
        # Check for common modification fields (case-insensitive)
        modification_field_patterns = ['modified', 'modification', 'modify', 'mod_date',
                                     'updated', 'update', 'upd_date', 'upd_at',
                                     'changed', 'change', 'chg_date', 'chg_at',
                                     'edited', 'edit', 'edit_date', 'edit_at',
                                     'last_modified', 'last_updated', 'last_changed',
                                     'date_modified', 'date_updated', 'date_changed',
                                     'modified_by', 'modifier', 'modified_user', 'user_modified',
                                     'updated_by', 'updater', 'updated_user', 'user_updated',
                                     'changed_by', 'changer', 'changed_user', 'user_changed',
                                     'edited_by', 'editor', 'edited_user', 'user_edited']
        
        fields = layer.fields()
        found_fields = set()
        
        # Search all fields for modification-related patterns
        for field in fields:
            field_name_lower = field.name().lower()
            field_name = field.name()
            
            # Check if field name matches any modification pattern
            for pattern in modification_field_patterns:
                if pattern in field_name_lower and field_name not in found_fields:
                    value = feature.attribute(field_name)
                    if value and str(value).strip():
                        found_fields.add(field_name)
                        if show_field_names:
                            info_lines.append(f"{field_name}: {value}")
                        else:
                            info_lines.append(f"Modified: {value}")
                        break
        
        # Also check for date/time fields that might be modification dates
        date_fields = []
        for field in fields:
            field_type = field.type()
            field_name = field.name()
            # Check for date/time field types
            if field_type in [14, 15, 16, 17, 18]:  # Date, Time, DateTime types
                value = feature.attribute(field_name)
                if value and str(value).strip():
                    field_name_lower = field_name.lower()
                    # Skip if already found as creation field
                    if not any(hint in field_name_lower for hint in ['create', 'add', 'insert', 'origin', 'first']):
                        date_fields.append((field_name, value))
        
        # If we found date fields but no modification info, check if any look like modification dates
        if not info_lines and date_fields:
            # Check field names for modification hints
            for field_name, value in date_fields:
                field_name_lower = field_name.lower()
                if any(hint in field_name_lower for hint in ['modify', 'update', 'change', 'edit', 'last']):
                    if field_name not in found_fields:
                        found_fields.add(field_name)
                        if show_field_names:
                            info_lines.append(f"{field_name}: {value}")
                        else:
                            info_lines.append(f"Modified: {value}")
        
        return "\n".join(info_lines) if info_lines else None
    
    def _get_audit_fields(self, feature, layer, date_format, show_field_names):
        """Get all audit-related fields from feature."""
        info_lines = []
        
        # Common audit field patterns (expanded list)
        audit_patterns = ['_at', '_date', '_by', '_user', '_time', '_timestamp',
                         'version', 'revision', 'history', 'hist',
                         'audit', 'track', 'log', 'change', 'modified', 'created', 'updated',
                         'edit', 'add', 'insert', 'delete', 'remove',
                         'user', 'author', 'owner', 'creator', 'modifier', 'editor',
                         'status', 'state', 'stage', 'phase',
                         'id', 'uuid', 'guid', 'oid', 'fid',
                         'source', 'origin', 'reference', 'ref']
        
        fields = layer.fields()
        found_fields = set()
        
        # First pass: Check all fields for audit patterns
        for field in fields:
            field_name = field.name()
            field_name_lower = field.name().lower()
            value = feature.attribute(field_name)
            
            # Skip if value is empty/null
            if not value or (isinstance(value, str) and not value.strip()):
                continue
            
            # Check if field matches audit patterns
            matches_pattern = False
            for pattern in audit_patterns:
                if pattern in field_name_lower:
                    matches_pattern = True
                    break
            
            # Also check field type - date/time fields are likely audit fields
            field_type = field.type()
            is_date_time = field_type in [14, 15, 16, 17, 18]  # Date, Time, DateTime types
            
            # Also check if field name suggests it's metadata/audit
            is_metadata_like = any(meta in field_name_lower for meta in ['meta', 'info', 'note', 'comment', 'desc'])
            
            if matches_pattern or is_date_time or is_metadata_like:
                if field_name not in found_fields:
                    found_fields.add(field_name)
                    if show_field_names:
                        info_lines.append(f"{field_name}: {value}")
                    else:
                        info_lines.append(f"{field_name}: {value}")
        
        # Second pass: Show ALL fields if we didn't find many audit fields
        if len(info_lines) < 3:
            # Show all non-empty fields as potential audit fields
            all_fields_info = []
            for field in fields:
                field_name = field.name()
                if field_name not in found_fields:
                    value = feature.attribute(field_name)
                    if value and str(value).strip():
                        # Skip geometry fields and very common non-audit fields
                        skip_fields = ['id', 'fid', 'objectid', 'shape', 'geometry', 'geom']
                        if field_name.lower() not in skip_fields:
                            all_fields_info.append(f"{field_name}: {value}")
            
            if all_fields_info:
                info_lines.append("")
                info_lines.append("All available fields (may contain history info):")
                info_lines.extend(all_fields_info[:20])  # Limit to first 20 to avoid clutter
                if len(all_fields_info) > 20:
                    info_lines.append(f"... and {len(all_fields_info) - 20} more fields")
        
        return "\n".join(info_lines) if info_lines else None
    
    def _get_edit_buffer_info(self, feature, layer, show_field_names):
        """Get pending changes from edit buffer."""
        info_lines = []
        
        if not layer.isEditable():
            return None
        
        try:
            # Check if feature has pending changes
            # Get original feature from data provider
            original_feature = QgsFeature()
            if layer.dataProvider().getFeatures([feature.id()]):
                provider_features = list(layer.dataProvider().getFeatures([feature.id()]))
                if provider_features:
                    original_feature = provider_features[0]
            
            # Compare current feature with original
            if original_feature and original_feature.id() == feature.id():
                # Check geometry changes
                original_geom = original_feature.geometry()
                current_geom = feature.geometry()
                if original_geom and current_geom:
                    if not original_geom.equals(current_geom):
                        info_lines.append("Geometry: MODIFIED (pending)")
                        try:
                            original_area = original_geom.area()
                            current_area = current_geom.area()
                            area_change = current_area - original_area
                            crs = layer.crs()
                            try:
                                if crs.isGeographic():
                                    unit_name = "square degrees"
                                elif crs.isValid() and crs.mapUnits() != 0:
                                    unit_name = f"square {crs.mapUnits().name().lower()}"
                                else:
                                    unit_name = "square map units"
                                info_lines.append(f"  Area: {original_area:.2f} → {current_area:.2f} {unit_name} ({area_change:+.2f})")
                            except:
                                info_lines.append(f"  Area: {original_area:.2f} → {current_area:.2f} ({area_change:+.2f})")
                        except:
                            pass
                
                # Check attribute changes
                original_attrs = original_feature.attributes()
                current_attrs = feature.attributes()
                fields = layer.fields()
                
                changed_attrs = []
                for i, field in enumerate(fields):
                    if i < len(original_attrs) and i < len(current_attrs):
                        if original_attrs[i] != current_attrs[i]:
                            field_name = field.name()
                            old_value = original_attrs[i]
                            new_value = current_attrs[i]
                            if show_field_names:
                                changed_attrs.append(f"  {field_name}: {old_value} → {new_value}")
                            else:
                                changed_attrs.append(f"  {field_name}: {old_value} → {new_value}")
                
                if changed_attrs:
                    info_lines.append("Attributes: MODIFIED (pending)")
                    info_lines.extend(changed_attrs)
                elif not info_lines:
                    info_lines.append("No pending changes detected.")
            else:
                info_lines.append("Feature is new (not yet saved to data source).")
        
        except Exception as e:
            info_lines.append(f"Could not retrieve edit buffer info: {str(e)}")
        
        return "\n".join(info_lines) if info_lines else None
    
    def _get_geometry_info(self, feature, layer, show_field_names):
        """Get detailed geometry information for polygon."""
        info_lines = []
        
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            return "No geometry"
        
        try:
            # Geometry type (detailed)
            geom_type = geometry.type()
            wkb_type = geometry.wkbType()
            if geom_type == QgsWkbTypes.PolygonGeometry:
                if QgsWkbTypes.isMultiType(wkb_type):
                    info_lines.append("Geometry Type: MultiPolygon")
                    # Count parts
                    try:
                        multi_polygon = geometry.asMultiPolygon()
                        info_lines.append(f"Number of Parts: {len(multi_polygon)}")
                    except:
                        pass
                else:
                    info_lines.append("Geometry Type: Polygon")
            
            # Polygon-specific info - Area (primary metric)
            area = geometry.area()
            crs = layer.crs()
            try:
                if crs.isGeographic():
                    unit_name = "square degrees"
                elif crs.isValid() and crs.mapUnits() != 0:
                    unit_name = f"square {crs.mapUnits().name().lower()}"
                else:
                    unit_name = "square map units"
                info_lines.append(f"Area: {area:.2f} {unit_name}")
            except:
                info_lines.append(f"Area: {area:.2f} square map units")
            
            # Perimeter/length
            perimeter = geometry.length()
            try:
                if crs.isGeographic():
                    unit_name = "degrees"
                elif crs.isValid() and crs.mapUnits() != 0:
                    unit_name = crs.mapUnits().name().lower()
                else:
                    unit_name = "map units"
                info_lines.append(f"Perimeter: {perimeter:.2f} {unit_name}")
            except:
                info_lines.append(f"Perimeter: {perimeter:.2f} map units")
            
            # Count vertices (detailed)
            try:
                vertices = list(geometry.vertices())
                vertex_count = len(vertices)
                info_lines.append(f"Total Vertices: {vertex_count}")
            except:
                pass
            
            # Bounding box (detailed)
            bbox = geometry.boundingBox()
            info_lines.append("")
            info_lines.append("Bounding Box:")
            info_lines.append(f"  Minimum X: {bbox.xMinimum():.2f}")
            info_lines.append(f"  Maximum X: {bbox.xMaximum():.2f}")
            info_lines.append(f"  Minimum Y: {bbox.yMinimum():.2f}")
            info_lines.append(f"  Maximum Y: {bbox.yMaximum():.2f}")
            info_lines.append(f"  Width: {bbox.width():.2f}")
            info_lines.append(f"  Height: {bbox.height():.2f}")
            info_lines.append(f"  Center: ({bbox.center().x():.2f}, {bbox.center().y():.2f})")
            
            # Geometry validity
            validity_result = geometry.validateGeometry()
            if validity_result:
                if len(validity_result) > 0:
                    info_lines.append("")
                    info_lines.append(f"Geometry Issues: {len(validity_result)}")
                    for i, error in enumerate(validity_result[:5]):  # Show first 5 errors
                        info_lines.append(f"  {i+1}. {error.what()}")
                    if len(validity_result) > 5:
                        info_lines.append(f"  ... and {len(validity_result) - 5} more issues")
                else:
                    info_lines.append("")
                    info_lines.append("Geometry: Valid")
            else:
                info_lines.append("")
                info_lines.append("Geometry: Valid")
            
        except Exception as e:
            info_lines.append(f"Error getting geometry info: {str(e)}")
        
        return "\n".join(info_lines) if info_lines else None
    
    def _get_attribute_info(self, feature, layer, show_field_names):
        """Get detailed attribute information."""
        info_lines = []
        
        fields = layer.fields()
        attributes = feature.attributes()
        
        # Group fields by type for better organization
        field_groups = {
            'Text': [],
            'Numeric': [],
            'Date/Time': [],
            'Boolean': [],
            'Other': []
        }
        
        for i, field in enumerate(fields):
            if i < len(attributes):
                field_name = field.name()
                field_type = field.type()
                value = attributes[i]
                
                # Format value with type info
                if value is None:
                    value_str = "(NULL)"
                elif isinstance(value, (int, float)):
                    value_str = str(value)
                else:
                    value_str = str(value)
                
                # Determine field category
                if field_type in [10, 11, 12, 13]:  # String types
                    category = 'Text'
                elif field_type in [2, 4, 5, 6]:  # Numeric types
                    category = 'Numeric'
                elif field_type in [14, 15, 16, 17, 18]:  # Date/Time types
                    category = 'Date/Time'
                elif field_type == 1:  # Boolean
                    category = 'Boolean'
                else:
                    category = 'Other'
                
                # Get field type name
                type_name = field.typeName()
                field_info = {
                    'name': field_name,
                    'value': value_str,
                    'type': type_name,
                    'length': field.length() if hasattr(field, 'length') else None,
                    'precision': field.precision() if hasattr(field, 'precision') else None
                }
                field_groups[category].append(field_info)
        
        # Display grouped fields
        for category, field_list in field_groups.items():
            if field_list:
                info_lines.append(f"{category} Fields ({len(field_list)}):")
                for field_info in field_list:
                    name = field_info['name']
                    value = field_info['value']
                    type_name = field_info['type']
                    
                    if show_field_names:
                        type_info = f" [{type_name}]" if type_name else ""
                        info_lines.append(f"  {name}{type_info}: {value}")
                    else:
                        info_lines.append(f"  {name}: {value}")
                info_lines.append("")
        
        # Summary
        total_fields = len([f for group in field_groups.values() for f in group])
        non_null_fields = len([f for group in field_groups.values() for f in group if f['value'] != "(NULL)"])
        info_lines.append(f"Total Fields: {total_fields} ({non_null_fields} with values, {total_fields - non_null_fields} NULL)")
        
        return "\n".join(info_lines) if info_lines else None


# REQUIRED: Create global instance for automatic discovery
see_info_polygon = SeeInfoPolygonAction()

