"""
Change Line Layer CRS Action for Right-click Utilities and Shortcuts Hub

Changes the coordinate reference system (CRS) of a line layer to a user-selected CRS.
Works on line layers and provides a CRS selection dialog.
"""

from .base_action import BaseAction
from qgis.gui import QgsMapCanvas, QgsProjectionSelectionDialog
from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from ..history_manager import get_history_manager
import base64


class ChangeLineLayerCrsAction(BaseAction):
    """Action to change the CRS of a line layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "change_line_layer_crs"
        self.name = "Change Line Layer CRS"
        self.category = "Layer Operations"
        self.description = "Change the coordinate reference system (CRS) of the selected line layer. Transforms all geometries to the new CRS and updates layer metadata."
        self.enabled = True
        
        # Action scoping - this works on entire layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support - only works with line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # BEHAVIOR SETTINGS
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a success message after changing the CRS',
            },
            'show_error_messages': {
                'type': 'bool',
                'default': True,
                'label': 'Show Error Messages',
                'description': 'Display error messages if the operation fails',
            },
            'update_project_crs': {
                'type': 'bool',
                'default': False,
                'label': 'Update Project CRS',
                'description': 'Update the project CRS to match the new layer CRS',
            },
            'refresh_canvas': {
                'type': 'bool',
                'default': True,
                'label': 'Refresh Canvas',
                'description': 'Refresh the map canvas after changing the CRS',
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
        Execute the change line layer CRS action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            show_success = bool(self.get_setting('show_success_message', True))
            show_errors = bool(self.get_setting('show_error_messages', True))
            update_project_crs = bool(self.get_setting('update_project_crs', False))
            refresh_canvas = bool(self.get_setting('refresh_canvas', True))
        except (ValueError, TypeError) as e:
            if show_errors:
                self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        canvas = context.get('canvas')
        
        if not detected_features:
            if show_errors:
                self.show_error("Error", "No line features found at this location")
            return
        
        if not canvas:
            if show_errors:
                self.show_error("Error", "Map canvas not available")
            return
        
        # Get the first (closest) detected feature to determine the layer
        detected_feature = detected_features[0]
        layer = detected_feature.layer
        
        # Check if layer is a vector layer
        if not isinstance(layer, QgsVectorLayer):
            if show_errors:
                self.show_error("Error", "Selected layer is not a vector layer")
            return
        
        # Get current layer CRS
        current_crs = layer.crs()
        
        # Show CRS selection dialog
        crs_dialog = QgsProjectionSelectionDialog(None)
        crs_dialog.setCrs(current_crs)
        crs_dialog.setMessage(f"Select new CRS for layer '{layer.name()}'\nCurrent CRS: {current_crs.description()}")
        
        # If user cancels, exit
        if not crs_dialog.exec_():
            return
        
        # Get selected CRS
        new_crs = crs_dialog.crs()
        
        # Check if CRS is valid
        if not new_crs.isValid():
            if show_errors:
                self.show_error("Error", "Selected CRS is not valid")
            return
        
        # Check if CRS is the same as current
        if new_crs == current_crs:
            if show_errors:
                self.show_error("Information", "Selected CRS is the same as current CRS. No changes made.")
            return
        
        # Start editing the layer
        if not layer.isEditable():
            layer.startEditing()
        
        try:
            # Create transform from current CRS to new CRS
            transform = QgsCoordinateTransform(current_crs, new_crs, QgsProject.instance())

            # Prepare backups of original geometries
            old_geoms = {}
            for feature in layer.getFeatures():
                geom = feature.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    old_geoms[int(feature.id())] = base64.b64encode(geom.asWkb()).decode('utf-8')
                except Exception:
                    # Skip features we cannot serialize for history
                    continue

            # Transform all geometries and capture new geometry WKB
            new_geoms = {}
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if not geometry or geometry.isEmpty():
                    continue

                try:
                    # Transform geometry
                    geometry.transform(transform)

                    # Update feature with new geometry
                    layer.changeGeometry(feature.id(), geometry)

                    # Store new geometry WKB for history
                    try:
                        new_geoms[int(feature.id())] = base64.b64encode(geometry.asWkb()).decode('utf-8')
                    except Exception:
                        # ignore serialization errors for new geometry
                        pass
                except Exception as e:
                    if show_errors:
                        self.show_error("Error", f"Failed to transform feature {feature.id()}: {str(e)}")
                    layer.rollBack()
                    return
            
            # Commit changes
            if not layer.commitChanges():
                if show_errors:
                    self.show_error("Error", f"Failed to commit changes: {layer.commitErrors()}")
                return
            
            # Set the layer's CRS to the new CRS
            layer.setCrs(new_crs)
            
            # Update project CRS if requested
            if update_project_crs:
                QgsProject.instance().setCrs(new_crs)
            
            # Refresh canvas if requested
            if refresh_canvas:
                canvas.refresh()
            
            # Show success message if requested
            if show_success:
                self.show_info("Success", f"Changed CRS of layer '{layer.name()}' from {current_crs.description()} to {new_crs.description()}")
                
            # Record undo history (update_geometry) with per-feature old/new geometry backups
            try:
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {'layer_id': getattr(layer, 'id', lambda: None)(), 'layer_name': getattr(layer, 'name', lambda: '')()}

                features_backups = []
                # Build feature entries with old and new geometries
                for fid, old_wkb in old_geoms.items():
                    entry = {'fid': int(fid)}
                    if old_wkb:
                        entry['old_geometry'] = {'wkb_base64': old_wkb}
                    new_wkb = new_geoms.get(int(fid))
                    if new_wkb:
                        entry['new_geometry'] = {'wkb_base64': new_wkb}
                    features_backups.append(entry)

                meta = {
                    'from_crs': current_crs.authid() if hasattr(current_crs, 'authid') else str(current_crs),
                    'to_crs': new_crs.authid() if hasattr(new_crs, 'authid') else str(new_crs),
                }

                hm.record(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=f"Changed CRS of layer '{layer.name()}' from {current_crs.description()} to {new_crs.description()}",
                    undo_type=hm.UNDO_TYPE_UPDATE_GEOMETRY,
                    can_undo=True,
                    undo_payload=None,
                    redo_payload=None,
                    layers=[layer_desc],
                    features=features_backups,
                    atomic=True,
                    meta=meta
                )
            except Exception:
                # History recording must not break the main action
                pass
        except Exception as e:
            if show_errors:
                self.show_error("Error", f"Failed to change layer CRS: {str(e)}")
            if layer.isEditable():
                layer.rollBack()


# REQUIRED: Create global instance for automatic discovery
change_line_layer_crs_action = ChangeLineLayerCrsAction()