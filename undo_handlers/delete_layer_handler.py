"""
Delete Layer Undo Handler

Handles undo/redo for actions that DELETE layers.

Undo: Restore the deleted layer (requires full layer backup)
Redo: Delete the restored layer
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject, QgsVectorLayer
except ImportError:
    pass


class DeleteLayerHandler(BaseUndoHandler):
    """
    Handler for undoing layer deletion.
    
    This requires the complete layer to have been backed up before deletion.
    """
    
    undo_type = "delete_layer"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo layer deletion by restoring the layer.
        
        This requires a full layer backup in the undo payload.
        
        Args:
            entry: HistoryEntry with layer backup
        
        Returns:
            Tuple of (success, message)
        """
        # Layer deletion undo requires complete layer restoration
        # This is complex and depends on how the layer was backed up
        
        layer_backup = entry.undo_payload.get('layer_backup') if entry.undo_payload else None
        
        if not layer_backup:
            return False, "Cannot undo layer deletion: no layer backup found"
        
        # Placeholder for full implementation
        # Would need to:
        # 1. Recreate layer with same structure
        # 2. Restore all features
        # 3. Restore styling
        # 4. Add back to project
        
        return False, "Layer deletion undo requires implementation specific to backup method"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo layer deletion by removing the restored layer.
        
        Args:
            entry: HistoryEntry with layer info
        
        Returns:
            Tuple of (success, message)
        """
        if not entry.layers:
            return False, "No layer information in redo payload"
        
        for layer_info in entry.layers:
            layer_id = layer_info.get('layer_id')
            
            if not layer_id:
                continue
            
            layer = QgsProject.instance().mapLayer(layer_id)
            
            if layer:
                QgsProject.instance().removeMapLayer(layer_id)
                return True, f"Layer '{layer_info.get('layer_name', 'Unknown')}' removed"
        
        return False, "Layer not found"


# Create singleton instance for registration
handler = DeleteLayerHandler()
