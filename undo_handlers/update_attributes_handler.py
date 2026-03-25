"""
Update Attributes Undo Handler

Handles undo/redo for actions that UPDATE feature attributes.

Undo: Restore old attribute values
Redo: Re-apply new attribute values
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsFeature
except ImportError:
    pass


class UpdateAttributesHandler(BaseUndoHandler):
    """
    Handler for undoing attribute updates.
    
    Requires the payload to contain both old_attributes and new_attributes
    for each modified feature.
    """
    
    undo_type = "update_attributes"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo attribute updates by restoring old values.
        
        Args:
            entry: HistoryEntry with old/new attribute values
        
        Returns:
            Tuple of (success, message)
        """
        features = self.load_features(entry)
        if not features:
            return False, "No feature data found in undo payload"
        
        updated_count = 0
        
        for layer_info in entry.layers:
            layer = self.get_layer(layer_info.get('layer_id'))
            
            if not isinstance(layer, QgsVectorLayer):
                continue
            
            # Start editing
            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Could not start editing layer '{layer.name()}'"
            
            try:
                for feat_info in features:
                    fid = feat_info.get('fid')
                    old_attrs = feat_info.get('old_attributes', {})
                    
                    if fid is None or not old_attrs:
                        continue
                    
                    fid = int(fid)
                    exists, feature = self.feature_exists(layer, fid)
                    
                    if not exists:
                        self.rollback(layer, was_editing)
                        return False, f"Feature {fid} not found"
                    
                    # Get the full feature for updating
                    feature = layer.getFeature(fid)
                    
                    # Restore old attribute values
                    for field_name, old_value in old_attrs.items():
                        idx = layer.fields().indexOf(field_name)
                        if idx >= 0:
                            feature.setAttribute(idx, old_value)
                    
                    if layer.updateFeature(feature):
                        updated_count += 1
                    else:
                        self.rollback(layer, was_editing)
                        return False, f"Failed to update feature {fid}"
                
                # Commit changes
                success, message = self.commit_or_rollback(layer, was_editing)
                if not success:
                    return False, message
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during undo: {str(e)}"
        
        return True, f"Attribute update undone ({updated_count} features restored)"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo attribute updates by re-applying new values.
        
        Args:
            entry: HistoryEntry with old/new attribute values
        
        Returns:
            Tuple of (success, message)
        """
        features = self.load_features(entry)
        if not features:
            return False, "No feature data found for redo"
        
        updated_count = 0
        
        for layer_info in entry.layers:
            layer = self.get_layer(layer_info.get('layer_id'))
            
            if not isinstance(layer, QgsVectorLayer):
                continue
            
            # Start editing
            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Could not start editing layer '{layer.name()}'"
            
            try:
                for feat_info in features:
                    fid = feat_info.get('fid')
                    new_attrs = feat_info.get('new_attributes', {})
                    
                    if fid is None or not new_attrs:
                        continue
                    
                    fid = int(fid)
                    exists, _ = self.feature_exists(layer, fid)
                    
                    if not exists:
                        self.rollback(layer, was_editing)
                        return False, f"Feature {fid} not found"
                    
                    # Get the full feature for updating
                    feature = layer.getFeature(fid)
                    
                    # Apply new attribute values
                    for field_name, new_value in new_attrs.items():
                        idx = layer.fields().indexOf(field_name)
                        if idx >= 0:
                            feature.setAttribute(idx, new_value)
                    
                    if layer.updateFeature(feature):
                        updated_count += 1
                    else:
                        self.rollback(layer, was_editing)
                        return False, f"Failed to update feature {fid}"
                
                # Commit changes
                success, message = self.commit_or_rollback(layer, was_editing)
                if not success:
                    return False, message
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during redo: {str(e)}"
        
        return True, f"Redo successful: {updated_count} feature(s) updated"


# Create singleton instance for registration
handler = UpdateAttributesHandler()
