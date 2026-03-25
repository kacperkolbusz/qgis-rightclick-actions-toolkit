"""
Create Feature Undo Handler

Handles undo/redo for actions that CREATE new features.

Undo: Delete the created feature(s)
Redo: Re-create the deleted feature(s) from backup
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFeatureRequest
except ImportError:
    pass


class CreateFeatureHandler(BaseUndoHandler):
    """
    Handler for undoing feature creation.
    
    When a feature is created, undo means deleting it.
    When undone, redo means re-creating it from the stored backup.
    """
    
    undo_type = "create_feature"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo feature creation by deleting the created feature(s).
        
        Args:
            entry: HistoryEntry with layers and features info
        
        Returns:
            Tuple of (success, message)
        """
        features = self.load_features(entry)
        if not features:
            return False, "No feature data found in undo payload"
        
        deleted_count = 0
        not_found_count = 0
        
        for layer_info in entry.layers:
            layer = self.get_layer(layer_info.get('layer_id'))
            
            if not isinstance(layer, QgsVectorLayer):
                continue
            
            # Start editing
            success, was_editing = self.start_editing(layer)
            if not success:
                return False, f"Could not start editing layer '{layer.name()}'"
            
            try:
                # Delete created features
                for feat_info in features:
                    fid = feat_info.get('fid')
                    if fid is not None:
                        # Ensure fid is an integer
                        fid = int(fid)
                        
                        # Check if feature exists
                        exists, _ = self.feature_exists(layer, fid)
                        
                        if exists:
                            if layer.deleteFeature(fid):
                                deleted_count += 1
                            else:
                                self.rollback(layer, was_editing)
                                return False, f"Failed to delete feature {fid} from layer '{layer.name()}'"
                        else:
                            not_found_count += 1
                
                # Commit changes
                if deleted_count > 0:
                    success, message = self.commit_or_rollback(layer, was_editing)
                    if not success:
                        return False, message
                else:
                    self.rollback(layer, was_editing)
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during undo: {str(e)}"
        
        if deleted_count == 0 and not_found_count > 0:
            # Collect existing feature IDs for debugging
            existing_fids = []
            for layer_info in entry.layers:
                layer = self.get_layer(layer_info.get('layer_id'))
                if isinstance(layer, QgsVectorLayer):
                    for f in layer.getFeatures():
                        existing_fids.append(f.id())
            
            requested_fids = [feat_info.get('fid') for feat_info in features]
            return False, f"Feature(s) no longer exist - may have been already deleted. Requested FID(s): {requested_fids}, Existing FID(s) in layer: {existing_fids}"
        
        return True, f"Feature creation undone successfully ({deleted_count} deleted)"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo feature creation by re-creating the deleted feature(s).
        
        Args:
            entry: HistoryEntry with feature backup data
        
        Returns:
            Tuple of (success, message)
        """
        import base64
        
        features = self.load_features(entry)
        if not features:
            return False, "No feature backup found for redo"
        
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
                for i, feat_info in enumerate(features):
                    # Create new feature
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
                    
                    # Add feature using data provider to get correct FID
                    add_success, added_features = layer.dataProvider().addFeatures([feature])
                    if add_success and added_features:
                        new_fid = added_features[0].id()
                        new_fids.append((i, new_fid))
                        created_count += 1
                    else:
                        self.rollback(layer, was_editing)
                        return False, f"Failed to re-create feature in layer '{layer.name()}'"
                
                # Commit changes
                success, message = self.commit_or_rollback(layer, was_editing)
                if not success:
                    return False, message
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during redo: {str(e)}"
        
        if created_count == 0:
            return False, "No features were re-created"
        
        # Update the entry's feature FIDs with the new FIDs
        # This is important for subsequent undo operations
        for i, new_fid in new_fids:
            if i < len(entry.features):
                entry.features[i]['fid'] = new_fid
        
        return True, f"Redo successful: {created_count} feature(s) re-created"


# Create singleton instance for registration
handler = CreateFeatureHandler()
