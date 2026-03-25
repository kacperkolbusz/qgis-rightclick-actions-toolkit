"""
Delete Feature Undo Handler

Handles undo/redo for actions that DELETE existing features.

Undo: Re-create the deleted feature(s) from backup
Redo: Delete the re-created feature(s)
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry
except ImportError:
    pass


class DeleteFeatureHandler(BaseUndoHandler):
    """
    Handler for undoing feature deletion.
    
    When a feature is deleted, undo means re-creating it from backup.
    When undone, redo means deleting it again.
    """
    
    undo_type = "delete_feature"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo feature deletion by re-creating the deleted feature(s).
        
        Args:
            entry: HistoryEntry with feature backup data
        
        Returns:
            Tuple of (success, message)
        """
        import base64
        
        features = self.load_features(entry)
        if not features:
            return False, "No feature backup found in undo payload"
        
        created_count = 0
        new_fids = []
        
        for layer_info in entry.layers:
            layer = self.get_layer(layer_info.get('layer_id'))
            
            if not isinstance(layer, QgsVectorLayer):
                continue
            
            # Start editing
            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Could not start editing layer '{layer.name()}'"
            
            try:
                # Re-create deleted features
                for i, feat_info in enumerate(features):
                    feature = QgsFeature(layer.fields())
                    
                    # Restore geometry
                    geom = self.restore_geometry(feat_info.get('geometry'))
                    if geom:
                        feature.setGeometry(geom)
                    
                    # Restore attributes
                    attrs_data = feat_info.get('attributes', {})
                    for field_name, value in attrs_data.items():
                        idx = layer.fields().indexOf(field_name)
                        if idx >= 0:
                            feature.setAttribute(idx, value)
                    
                    # Add feature
                    add_success, added_features = layer.dataProvider().addFeatures([feature])
                    if add_success and added_features:
                        new_fid = added_features[0].id()
                        new_fids.append((i, new_fid))
                        created_count += 1
                    else:
                        self.rollback(layer, was_editing)
                        return False, f"Failed to restore feature in layer '{layer.name()}'"
                
                # Commit changes
                success, message = self.commit_or_rollback(layer, was_editing)
                if not success:
                    return False, message
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during undo: {str(e)}"
        
        # Update entry with new FIDs for subsequent operations
        for i, new_fid in new_fids:
            if i < len(entry.features):
                entry.features[i]['fid'] = new_fid
        
        return True, f"Feature deletion undone ({created_count} restored)"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo feature deletion by deleting the restored feature(s).
        
        This is essentially the same as undoing a create operation.
        
        Args:
            entry: HistoryEntry with feature info
        
        Returns:
            Tuple of (success, message)
        """
        features = self.load_features(entry)
        if not features:
            return False, "No feature data found for redo"
        
        deleted_count = 0
        
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
                    if fid is not None:
                        fid = int(fid)
                        exists, _ = self.feature_exists(layer, fid)
                        
                        if exists:
                            if layer.deleteFeature(fid):
                                deleted_count += 1
                            else:
                                self.rollback(layer, was_editing)
                                return False, f"Failed to delete feature {fid}"
                
                if deleted_count > 0:
                    success, message = self.commit_or_rollback(layer, was_editing)
                    if not success:
                        return False, message
                else:
                    self.rollback(layer, was_editing)
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during redo: {str(e)}"
        
        return True, f"Redo successful: {deleted_count} feature(s) deleted"


# Create singleton instance for registration
handler = DeleteFeatureHandler()
