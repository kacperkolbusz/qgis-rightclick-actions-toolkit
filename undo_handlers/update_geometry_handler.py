"""
Update Geometry Undo Handler

Handles undo/redo for actions that UPDATE feature geometries.

Undo: Restore old geometry
Redo: Re-apply new geometry
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsCoordinateReferenceSystem
except ImportError:
    pass


class UpdateGeometryHandler(BaseUndoHandler):
    """
    Handler for undoing geometry updates.
    
    Requires the payload to contain both old_geometry and new_geometry
    for each modified feature.
    """
    
    undo_type = "update_geometry"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo geometry updates by restoring old geometries.
        
        Args:
            entry: HistoryEntry with old/new geometry data
        
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
                    old_geom_data = feat_info.get('old_geometry')
                    
                    if fid is None or not old_geom_data:
                        continue
                    
                    fid = int(fid)
                    exists, _ = self.feature_exists(layer, fid)
                    
                    if not exists:
                        self.rollback(layer, was_editing)
                        return False, f"Feature {fid} not found"
                    
                    # Restore old geometry
                    old_geom = self.restore_geometry(old_geom_data)
                    if old_geom:
                        if layer.changeGeometry(fid, old_geom):
                            updated_count += 1
                        else:
                            self.rollback(layer, was_editing)
                            return False, f"Failed to restore geometry for feature {fid}"
                
                # Commit changes
                success, message = self.commit_or_rollback(layer, was_editing)
                if not success:
                    return False, message
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during undo: {str(e)}"

            # After successful geometry restore, restore layer CRS if provided in meta
            try:
                from_crs = None
                if hasattr(entry, 'meta') and entry.meta:
                    from_crs = entry.meta.get('from_crs')
                if from_crs:
                    try:
                        crs_obj = QgsCoordinateReferenceSystem(from_crs)
                        layer.setCrs(crs_obj)
                    except Exception:
                        # Non-fatal: ignore CRS restore failures
                        pass
            except Exception:
                pass
        
        return True, f"Geometry update undone ({updated_count} features restored)"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo geometry updates by re-applying new geometries.
        
        Args:
            entry: HistoryEntry with old/new geometry data
        
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
                    new_geom_data = feat_info.get('new_geometry')
                    
                    if fid is None or not new_geom_data:
                        continue
                    
                    fid = int(fid)
                    exists, _ = self.feature_exists(layer, fid)
                    
                    if not exists:
                        self.rollback(layer, was_editing)
                        return False, f"Feature {fid} not found"
                    
                    # Apply new geometry
                    new_geom = self.restore_geometry(new_geom_data)
                    if new_geom:
                        if layer.changeGeometry(fid, new_geom):
                            updated_count += 1
                        else:
                            self.rollback(layer, was_editing)
                            return False, f"Failed to update geometry for feature {fid}"
                
                # Commit changes
                success, message = self.commit_or_rollback(layer, was_editing)
                if not success:
                    return False, message
                
            except Exception as e:
                self.rollback(layer, was_editing)
                return False, f"Error during redo: {str(e)}"

            # After re-applying new geometries, restore layer CRS to 'to_crs' if provided
            try:
                to_crs = None
                if hasattr(entry, 'meta') and entry.meta:
                    to_crs = entry.meta.get('to_crs')
                if to_crs:
                    try:
                        crs_obj = QgsCoordinateReferenceSystem(to_crs)
                        layer.setCrs(crs_obj)
                    except Exception:
                        pass
            except Exception:
                pass
        
        return True, f"Redo successful: {updated_count} geometry(ies) updated"


# Create singleton instance for registration
handler = UpdateGeometryHandler()
