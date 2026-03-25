"""
Base Undo Handler for Right-click Actions Toolkit

This module defines the abstract base class for all undo handlers.
Each undo type (create_feature, delete_feature, etc.) should inherit
from this class and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, List, Any, Optional

# Import QGIS modules - these will be available at runtime in QGIS
try:
    from qgis.core import (
        QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
        QgsFeatureRequest
    )
except ImportError:
    # Allow module to load outside QGIS for documentation/testing
    pass


class BaseUndoHandler(ABC):
    """
    Abstract base class for undo handlers.
    
    Each undo handler is responsible for:
    1. Undoing a specific type of operation
    2. Redoing that operation (re-applying the original action)
    
    Subclasses must implement:
    - undo_type: Class attribute defining the undo type string
    - undo(): Method to reverse the operation
    - redo(): Method to re-apply the operation
    
    Example:
        class CreateFeatureHandler(BaseUndoHandler):
            undo_type = "create_feature"
            
            def undo(self, entry):
                # Delete the created feature
                ...
            
            def redo(self, entry):
                # Re-create the deleted feature
                ...
    """
    
    # Class attribute - override in subclass
    undo_type: str = "base"
    
    def __init__(self):
        """Initialize the handler."""
        pass
    
    @abstractmethod
    def undo(self, entry: 'HistoryEntry') -> Tuple[bool, str]:
        """
        Perform the undo operation.
        
        Args:
            entry: The HistoryEntry containing all information about the
                   operation to undo, including:
                   - entry.layers: List of layer descriptors
                   - entry.features: List of feature backups/references
                   - entry.undo_payload: Additional undo data
                   - entry.meta: Action-specific metadata
        
        Returns:
            Tuple of (success: bool, message: str)
            - success: True if undo completed successfully
            - message: Description of result or error
        """
        pass
    
    @abstractmethod
    def redo(self, entry: 'HistoryEntry') -> Tuple[bool, str]:
        """
        Perform the redo operation (re-apply the original action).
        
        Args:
            entry: The HistoryEntry containing operation information
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    # =========================================================================
    # Helper Methods - Available to all handlers
    # =========================================================================
    
    def get_layer(self, layer_id: str) -> Optional['QgsVectorLayer']:
        """
        Get a layer from the project by ID.
        
        Args:
            layer_id: The layer's unique ID
        
        Returns:
            QgsVectorLayer or None if not found
        """
        layer = QgsProject.instance().mapLayer(layer_id)
        if isinstance(layer, QgsVectorLayer):
            return layer
        return None
    
    def get_layer_from_entry(self, entry: 'HistoryEntry', index: int = 0) -> Optional['QgsVectorLayer']:
        """
        Get a layer from the entry's layers list.
        
        Args:
            entry: The history entry
            index: Index in the layers list (default 0)
        
        Returns:
            QgsVectorLayer or None
        """
        if not entry.layers or index >= len(entry.layers):
            return None
        
        layer_info = entry.layers[index]
        layer_id = layer_info.get('layer_id')
        return self.get_layer(layer_id) if layer_id else None
    
    def feature_exists(self, layer: 'QgsVectorLayer', fid: int) -> Tuple[bool, Optional['QgsFeature']]:
        """
        Check if a feature exists in a layer using reliable lookup.
        
        Uses QgsFeatureRequest which is more reliable than getFeature()
        for memory layers after edit sessions.
        
        Args:
            layer: The vector layer
            fid: Feature ID to look for
        
        Returns:
            Tuple of (exists: bool, feature: QgsFeature or None)
        """
        request = QgsFeatureRequest().setFilterFid(fid).setNoAttributes()
        for feature in layer.getFeatures(request):
            if feature.isValid():
                return True, feature
        return False, None
    
    def start_editing(self, layer: 'QgsVectorLayer') -> Tuple[bool, bool]:
        """
        Start editing a layer if not already editing.
        
        Args:
            layer: The vector layer
        
        Returns:
            Tuple of (success: bool, was_already_editing: bool)
        """
        was_editing = layer.isEditable()
        if not was_editing:
            if not layer.startEditing():
                return False, was_editing
        return True, was_editing
    
    def commit_or_rollback(self, layer: 'QgsVectorLayer', was_editing: bool) -> Tuple[bool, str]:
        """
        Commit changes or rollback if commit fails.
        
        Args:
            layer: The vector layer
            was_editing: Whether the layer was already in edit mode
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not was_editing:
            if layer.commitChanges():
                layer.triggerRepaint()
                return True, "Changes committed"
            else:
                layer.rollBack()
                return False, f"Failed to commit changes to layer '{layer.name()}'"
        return True, "Changes pending (layer still in edit mode)"
    
    def rollback(self, layer: 'QgsVectorLayer', was_editing: bool) -> None:
        """
        Rollback changes if we started the edit session.
        
        Args:
            layer: The vector layer
            was_editing: Whether the layer was already in edit mode
        """
        if not was_editing:
            layer.rollBack()
    
    def load_features(self, entry: 'HistoryEntry') -> List[Dict]:
        """
        Load features from entry, handling external backup files.
        
        Args:
            entry: The history entry
        
        Returns:
            List of feature dictionaries
        """
        import os
        import json
        
        features = entry.features
        
        # Check for external backup file
        if features and len(features) == 1 and 'backup_file' in features[0]:
            backup_file = features[0]['backup_file']
            if os.path.exists(backup_file):
                with open(backup_file, 'r', encoding='utf-8') as f:
                    features = json.load(f)
        
        return features or []
    
    def restore_geometry(self, geom_data: Dict) -> Optional['QgsGeometry']:
        """
        Restore a QgsGeometry from backup data.
        
        Args:
            geom_data: Dictionary with geometry backup (wkb_base64)
        
        Returns:
            QgsGeometry or None
        """
        import base64
        
        if not geom_data:
            return None
        
        if isinstance(geom_data, dict) and 'wkb_base64' in geom_data:
            wkb = base64.b64decode(geom_data['wkb_base64'])
            geom = QgsGeometry()
            geom.fromWkb(wkb)
            return geom
        
        return None
