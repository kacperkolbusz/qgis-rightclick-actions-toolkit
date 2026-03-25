"""
RAT History Manager for Right-click Actions Toolkit

This module provides a comprehensive history tracking and undo/redo system for actions
performed by the plugin. It records actions with timestamps, stores undo payloads,
and enables reverting changes for supported actions.

Key Features:
- Records all plugin actions with timestamps
- Stores undo payloads for reversible actions
- Provides undo/redo functionality for supported actions
- Persists history to disk for session continuity
- Manages large backup artifacts efficiently
- Modular undo handlers in undo_handlers/ package

Undo handlers are now modular - see undo_handlers/ folder for implementations.
To add a new undo type, create a new handler file in that folder.
"""

import json
import os
import uuid
from datetime import datetime
from collections import deque
from typing import Optional, Dict, List, Tuple, Any

from qgis.PyQt.QtCore import QSettings, QStandardPaths, QObject, pyqtSignal
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsField, QgsFields, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsFeatureRequest
)

# Import the modular undo handler registry
from .undo_handlers import get_handler_registry


class HistoryEntry:
    """
    Represents a single history entry recording an action performed by the plugin.
    
    Attributes:
        entry_id (str): Unique identifier (UUID) for this entry
        timestamp (str): ISO8601 timestamp when the action was performed
        action_id (str): Identifier of the action that was performed
        action_name (str): Human-readable name of the action
        description (str): Detailed description of what was done
        undo_type (str): Type of undo operation needed
        can_undo (bool): Whether this entry can be undone
        is_undone (bool): Whether this entry has been undone
        undo_payload (dict): Data needed to perform undo
        redo_payload (dict): Data needed to perform redo (after undo)
        layers (list): List of layer descriptors affected
        features (list): List of feature backups/references
        payload_size_bytes (int): Size of the payload data
        status (str): Status of the entry (ok, partial, failed, undone)
        atomic (bool): Whether all changes are atomic (all-or-nothing)
        meta (dict): Additional action-specific metadata
    """
    
    def __init__(
        self,
        action_id: str,
        action_name: str,
        description: str,
        undo_type: str = "none",
        can_undo: bool = False,
        undo_payload: Optional[Dict] = None,
        redo_payload: Optional[Dict] = None,
        layers: Optional[List[Dict]] = None,
        features: Optional[List[Dict]] = None,
        atomic: bool = True,
        meta: Optional[Dict] = None
    ):
        """Initialize a new history entry."""
        self.entry_id = str(uuid.uuid4())
        self.timestamp = datetime.now().isoformat()
        self.action_id = action_id
        self.action_name = action_name
        self.description = description
        self.undo_type = undo_type
        self.can_undo = can_undo
        self.is_undone = False
        self.undo_payload = undo_payload or {}
        self.redo_payload = redo_payload or {}
        self.layers = layers or []
        self.features = features or []
        self.payload_size_bytes = self._calculate_payload_size()
        self.status = "ok"
        self.atomic = atomic
        self.meta = meta or {}
    
    def _calculate_payload_size(self) -> int:
        """Calculate approximate size of the payload in bytes."""
        try:
            payload_str = json.dumps({
                'undo_payload': self.undo_payload,
                'redo_payload': self.redo_payload,
                'features': self.features
            })
            return len(payload_str.encode('utf-8'))
        except (TypeError, ValueError):
            return 0
    
    def to_dict(self) -> Dict:
        """Convert entry to dictionary for serialization."""
        return {
            'entry_id': self.entry_id,
            'timestamp': self.timestamp,
            'action_id': self.action_id,
            'action_name': self.action_name,
            'description': self.description,
            'undo_type': self.undo_type,
            'can_undo': self.can_undo,
            'is_undone': self.is_undone,
            'undo_payload': self.undo_payload,
            'redo_payload': self.redo_payload,
            'layers': self.layers,
            'features': self.features,
            'payload_size_bytes': self.payload_size_bytes,
            'status': self.status,
            'atomic': self.atomic,
            'meta': self.meta
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HistoryEntry':
        """Create an entry from a dictionary."""
        entry = cls(
            action_id=data.get('action_id', ''),
            action_name=data.get('action_name', ''),
            description=data.get('description', ''),
            undo_type=data.get('undo_type', 'none'),
            can_undo=data.get('can_undo', False),
            undo_payload=data.get('undo_payload'),
            redo_payload=data.get('redo_payload'),
            layers=data.get('layers'),
            features=data.get('features'),
            atomic=data.get('atomic', True),
            meta=data.get('meta')
        )
        # Restore saved values
        entry.entry_id = data.get('entry_id', entry.entry_id)
        entry.timestamp = data.get('timestamp', entry.timestamp)
        entry.is_undone = data.get('is_undone', False)
        entry.payload_size_bytes = data.get('payload_size_bytes', 0)
        entry.status = data.get('status', 'ok')
        return entry
    
    def get_formatted_timestamp(self) -> str:
        """Get a human-readable formatted timestamp."""
        try:
            dt = datetime.fromisoformat(self.timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return self.timestamp
    
    def get_layers_summary(self) -> str:
        """Get a summary string of affected layers."""
        if not self.layers:
            return "No layers"
        layer_names = [layer.get('layer_name', 'Unknown') for layer in self.layers]
        return ", ".join(layer_names[:3]) + ("..." if len(layer_names) > 3 else "")
    
    def get_features_count(self) -> int:
        """Get the count of affected features."""
        return len(self.features)


class HistoryManager(QObject):
    """
    Manages the history of actions performed by the Right-click Actions Toolkit.
    
    This class provides:
    - Recording of actions with undo payloads
    - Undo/redo functionality for supported actions
    - Persistence of history to disk
    - Large artifact management
    
    Signals:
        history_changed: Emitted when history is modified
        undo_performed: Emitted after an undo operation (entry_id, success)
        redo_performed: Emitted after a redo operation (entry_id, success)
    """
    
    # Signals
    history_changed = pyqtSignal()
    undo_performed = pyqtSignal(str, bool)
    redo_performed = pyqtSignal(str, bool)
    
    # Singleton instance
    _instance = None
    
    # Undo type constants
    UNDO_TYPE_NONE = "none"
    UNDO_TYPE_CREATE_FEATURE = "create_feature"
    UNDO_TYPE_DELETE_FEATURE = "delete_feature"
    UNDO_TYPE_UPDATE_ATTRIBUTES = "update_attributes"
    UNDO_TYPE_UPDATE_GEOMETRY = "update_geometry"
    UNDO_TYPE_CREATE_LAYER = "create_layer"
    UNDO_TYPE_DELETE_LAYER = "delete_layer"
    UNDO_TYPE_COMPOSITE = "composite"
    UNDO_TYPE_INFORMATIONAL = "informational"
    UNDO_TYPE_VIEW_CHANGE = "view_change"
    
    def __new__(cls):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the history manager."""
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        
        # History storage
        self._entries: deque = deque()
        self._redo_stack: List[HistoryEntry] = []
        
        # Settings
        self._settings = QSettings()
        self._max_entries = self._get_setting('max_entries', 200)
        self._persistence_enabled = self._get_setting('persistence_enabled', True)
        self._backup_size_threshold_kb = self._get_setting('backup_size_threshold_kb', 1024)
        
        # Paths
        self._data_path = self._get_data_path()
        self._history_file = os.path.join(self._data_path, 'history.json')
        self._entries_path = os.path.join(self._data_path, 'entries')
        
        # Ensure directories exist
        os.makedirs(self._entries_path, exist_ok=True)
        
        # Action handlers registry (for custom undo implementations)
        self._action_handlers: Dict[str, Any] = {}
        
        # Load persisted history
        if self._persistence_enabled:
            self.load_from_disk()
    
    def _get_setting(self, key: str, default: Any) -> Any:
        """Get a setting value from QSettings."""
        return self._settings.value(f"RightClickUtilities/history/{key}", default)
    
    def _set_setting(self, key: str, value: Any) -> None:
        """Set a setting value in QSettings."""
        self._settings.setValue(f"RightClickUtilities/history/{key}", value)
    
    def _get_data_path(self) -> str:
        """Get the data path for storing history files."""
        # Try custom path first
        custom_path = self._get_setting('history_path', None)
        if custom_path and os.path.isdir(custom_path):
            return custom_path
        
        # Use standard application data location
        app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        history_path = os.path.join(app_data, 'RightClickActionsToolkit', 'history')
        os.makedirs(history_path, exist_ok=True)
        return history_path
    
    # =========================================================================
    # Recording Methods
    # =========================================================================
    
    def record(
        self,
        action_id: str,
        action_name: str,
        description: str,
        undo_type: str = UNDO_TYPE_NONE,
        can_undo: bool = False,
        undo_payload: Optional[Dict] = None,
        redo_payload: Optional[Dict] = None,
        layers: Optional[List[Dict]] = None,
        features: Optional[List[Dict]] = None,
        atomic: bool = True,
        meta: Optional[Dict] = None
    ) -> str:
        """
        Record a new history entry.
        
        This method should be called AFTER an action has been successfully
        committed. It creates a history entry that can be used for undo/redo.
        
        Args:
            action_id: Unique identifier of the action
            action_name: Human-readable name of the action
            description: Detailed description of what was done
            undo_type: Type of undo operation (use UNDO_TYPE_* constants)
            can_undo: Whether this entry can be undone
            undo_payload: Data needed to perform undo
            redo_payload: Data needed to perform redo (optional)
            layers: List of layer descriptors affected
            features: List of feature backups/references
            atomic: Whether all changes are atomic
            meta: Additional action-specific metadata
        
        Returns:
            str: The entry_id of the created history entry
        """
        # Create entry
        entry = HistoryEntry(
            action_id=action_id,
            action_name=action_name,
            description=description,
            undo_type=undo_type,
            can_undo=can_undo,
            undo_payload=undo_payload,
            redo_payload=redo_payload,
            layers=layers,
            features=features,
            atomic=atomic,
            meta=meta
        )
        
        # Handle large payloads
        if entry.payload_size_bytes > self._backup_size_threshold_kb * 1024:
            self._externalize_payload(entry)
        
        # Add to history
        self._entries.append(entry)
        
        # Clear redo stack when new action is recorded
        self._redo_stack.clear()
        
        # Enforce max entries limit
        while len(self._entries) > self._max_entries:
            old_entry = self._entries.popleft()
            self._cleanup_entry_artifacts(old_entry)
        
        # Persist if enabled
        if self._persistence_enabled:
            self.save_to_disk()
        
        # Emit signal
        self.history_changed.emit()
        
        return entry.entry_id
    
    def record_informational(
        self,
        action_id: str,
        action_name: str,
        description: str,
        meta: Optional[Dict] = None
    ) -> str:
        """
        Record an informational-only history entry (no undo capability).
        
        Use this for actions that only display information, change views,
        or perform read-only operations.
        
        Args:
            action_id: Unique identifier of the action
            action_name: Human-readable name of the action
            description: Description of what was done
            meta: Additional metadata
        
        Returns:
            str: The entry_id of the created history entry
        """
        return self.record(
            action_id=action_id,
            action_name=action_name,
            description=description,
            undo_type=self.UNDO_TYPE_INFORMATIONAL,
            can_undo=False,
            meta=meta
        )
    
    def _externalize_payload(self, entry: HistoryEntry) -> None:
        """Write large payloads to external files."""
        entry_dir = os.path.join(self._entries_path, entry.entry_id)
        os.makedirs(entry_dir, exist_ok=True)
        
        # Write features to external file
        if entry.features:
            features_file = os.path.join(entry_dir, 'features.json')
            with open(features_file, 'w', encoding='utf-8') as f:
                json.dump(entry.features, f, indent=2)
            entry.features = [{"backup_file": features_file}]
        
        # Recalculate size (now just reference)
        entry.payload_size_bytes = entry._calculate_payload_size()
    
    def _cleanup_entry_artifacts(self, entry: HistoryEntry) -> None:
        """Clean up external files for an entry."""
        entry_dir = os.path.join(self._entries_path, entry.entry_id)
        if os.path.isdir(entry_dir):
            import shutil
            try:
                shutil.rmtree(entry_dir)
            except Exception:
                pass  # Ignore cleanup errors
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def list_entries(self) -> List[HistoryEntry]:
        """
        Get all history entries in chronological order.
        
        Returns:
            List[HistoryEntry]: List of history entries (oldest first)
        """
        return list(self._entries)
    
    def get_entry(self, entry_id: str) -> Optional[HistoryEntry]:
        """
        Get a specific history entry by ID.
        
        Args:
            entry_id: The entry ID to find
        
        Returns:
            HistoryEntry or None if not found
        """
        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None
    
    def get_last_entry(self) -> Optional[HistoryEntry]:
        """Get the most recent history entry."""
        if self._entries:
            return self._entries[-1]
        return None
    
    def get_undoable_entries(self) -> List[HistoryEntry]:
        """Get all entries that can be undone."""
        return [e for e in self._entries if e.can_undo and not e.is_undone]
    
    def get_redoable_entries(self) -> List[HistoryEntry]:
        """Get all entries that can be redone."""
        return list(self._redo_stack)
    
    def get_entries_count(self) -> int:
        """Get the total number of history entries."""
        return len(self._entries)
    
    # =========================================================================
    # Undo/Redo Methods
    # =========================================================================
    
    def can_undo(self, entry_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check if an undo operation can be performed.
        
        Args:
            entry_id: Optional specific entry ID (default: last undoable entry)
        
        Returns:
            Tuple of (can_undo, reason_if_not)
        """
        # Find the entry
        if entry_id:
            entry = self.get_entry(entry_id)
        else:
            undoable = self.get_undoable_entries()
            entry = undoable[-1] if undoable else None
        
        if not entry:
            return False, "No entry found"
        
        if not entry.can_undo:
            return False, "This action does not support undo"
        
        if entry.is_undone:
            return False, "This action has already been undone"
        
        # Check if layers still exist and are writable
        for layer_info in entry.layers:
            layer_id = layer_info.get('layer_id')
            if layer_id:
                layer = QgsProject.instance().mapLayer(layer_id)
                if not layer:
                    return False, f"Layer '{layer_info.get('layer_name', 'Unknown')}' no longer exists"
                if isinstance(layer, QgsVectorLayer) and not layer.isEditable() and layer.readOnly():
                    return False, f"Layer '{layer.name()}' is read-only"
        
        return True, ""
    
    def undo(self, entry_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Undo a history entry.
        
        Args:
            entry_id: Optional specific entry ID (default: last undoable entry)
        
        Returns:
            Tuple of (success, message)
        """
        # Check if undo is possible
        can, reason = self.can_undo(entry_id)
        if not can:
            return False, reason
        
        # Find the entry
        if entry_id:
            entry = self.get_entry(entry_id)
        else:
            undoable = self.get_undoable_entries()
            entry = undoable[-1] if undoable else None
        
        if not entry:
            return False, "No entry found"
        
        try:
            # Check if there's a custom handler for this action
            if entry.action_id in self._action_handlers:
                handler = self._action_handlers[entry.action_id]
                if hasattr(handler, 'apply_undo'):
                    success, message = handler.apply_undo(entry.undo_payload)
                    if success:
                        entry.is_undone = True
                        entry.status = "undone"
                        self._redo_stack.append(entry)
                        self.history_changed.emit()
                        self.undo_performed.emit(entry.entry_id, True)
                        if self._persistence_enabled:
                            self.save_to_disk()
                    return success, message
            
            # Use generic undo based on undo_type
            success, message = self._apply_generic_undo(entry)
            
            if success:
                entry.is_undone = True
                entry.status = "undone"
                self._redo_stack.append(entry)
                self.history_changed.emit()
                self.undo_performed.emit(entry.entry_id, True)
                if self._persistence_enabled:
                    self.save_to_disk()
            else:
                self.undo_performed.emit(entry.entry_id, False)
            
            return success, message
            
        except Exception as e:
            entry.status = "failed"
            self.undo_performed.emit(entry.entry_id, False)
            return False, f"Undo failed: {str(e)}"
    
    def _apply_generic_undo(self, entry: HistoryEntry) -> Tuple[bool, str]:
        """
        Apply generic undo based on undo_type using modular handlers.
        
        Handlers are loaded from the undo_handlers/ package.
        To add a new undo type, create a new handler file in that folder.
        
        Args:
            entry: The history entry to undo
        
        Returns:
            Tuple of (success, message)
        """
        registry = get_handler_registry()
        
        if registry.has_handler(entry.undo_type):
            return registry.undo(entry)
        else:
            return False, f"No handler registered for undo type: {entry.undo_type}"
    
    def _apply_generic_redo(self, entry: HistoryEntry) -> Tuple[bool, str]:
        """
        Apply generic redo based on undo_type using modular handlers.
        
        Args:
            entry: The history entry to redo
        
        Returns:
            Tuple of (success, message)
        """
        registry = get_handler_registry()
        
        if registry.has_handler(entry.undo_type):
            return registry.redo(entry)
        else:
            return False, f"No handler registered for redo type: {entry.undo_type}"
    
    def can_redo(self, entry_id: Optional[str] = None) -> Tuple[bool, str]:
        """Check if a redo operation can be performed."""
        if not self._redo_stack:
            return False, "Nothing to redo"
        
        if entry_id:
            entry = None
            for e in self._redo_stack:
                if e.entry_id == entry_id:
                    entry = e
                    break
            if not entry:
                return False, "Entry not found in redo stack"
        else:
            entry = self._redo_stack[-1]
        
        return True, ""
    
    def redo(self, entry_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Redo a previously undone action.
        
        Args:
            entry_id: Optional specific entry ID (default: last undone entry)
        
        Returns:
            Tuple of (success, message)
        """
        can, reason = self.can_redo(entry_id)
        if not can:
            return False, reason
        
        if entry_id:
            entry = None
            for i, e in enumerate(self._redo_stack):
                if e.entry_id == entry_id:
                    entry = self._redo_stack.pop(i)
                    break
        else:
            entry = self._redo_stack.pop()
        
        if not entry:
            return False, "No entry found"
        
        try:
            # Check if there's a custom handler
            if entry.action_id in self._action_handlers:
                handler = self._action_handlers[entry.action_id]
                if hasattr(handler, 'apply_redo'):
                    success, message = handler.apply_redo(entry.redo_payload or entry.undo_payload)
                    if success:
                        entry.is_undone = False
                        entry.status = "ok"
                        self.history_changed.emit()
                        self.redo_performed.emit(entry.entry_id, True)
                        if self._persistence_enabled:
                            self.save_to_disk()
                    return success, message
            
            # Generic redo based on undo_type
            success, message = self._apply_generic_redo(entry)
            
            if success:
                entry.is_undone = False
                entry.status = "ok"
                entry.can_undo = True
                self.history_changed.emit()
                self.redo_performed.emit(entry.entry_id, True)
                if self._persistence_enabled:
                    self.save_to_disk()
            else:
                self.redo_performed.emit(entry.entry_id, False)
            
            return success, message
            
        except Exception as e:
            self.redo_performed.emit(entry.entry_id, False)
            return False, f"Redo failed: {str(e)}"
    
    # =========================================================================
    # Handler Registration
    # =========================================================================
    
    def register_action_handler(self, action_id: str, handler: Any) -> None:
        """
        Register a custom undo/redo handler for an action.
        
        The handler should implement:
        - apply_undo(payload: dict) -> Tuple[bool, str]
        - apply_redo(payload: dict) -> Tuple[bool, str] (optional)
        
        Args:
            action_id: The action ID to register the handler for
            handler: The handler object with apply_undo/apply_redo methods
        """
        self._action_handlers[action_id] = handler
    
    def unregister_action_handler(self, action_id: str) -> None:
        """Unregister a custom action handler."""
        if action_id in self._action_handlers:
            del self._action_handlers[action_id]
    
    # =========================================================================
    # Persistence Methods
    # =========================================================================
    
    def save_to_disk(self) -> None:
        """Persist history to disk."""
        try:
            data = {
                'version': 1,
                'entries': [e.to_dict() for e in self._entries],
                'redo_stack': [e.to_dict() for e in self._redo_stack]
            }
            
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"HistoryManager: Failed to save history: {e}")
    
    def load_from_disk(self) -> None:
        """Load persisted history from disk."""
        if not os.path.exists(self._history_file):
            return
        
        try:
            with open(self._history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Clear existing
            self._entries.clear()
            self._redo_stack.clear()
            
            # Load entries
            for entry_data in data.get('entries', []):
                entry = HistoryEntry.from_dict(entry_data)
                self._entries.append(entry)
            
            # Load redo stack
            for entry_data in data.get('redo_stack', []):
                entry = HistoryEntry.from_dict(entry_data)
                self._redo_stack.append(entry)
                
        except Exception as e:
            print(f"HistoryManager: Failed to load history: {e}")
    
    def clear_history(self) -> None:
        """Clear all history entries."""
        # Cleanup artifacts
        for entry in self._entries:
            self._cleanup_entry_artifacts(entry)
        
        self._entries.clear()
        self._redo_stack.clear()
        
        if self._persistence_enabled:
            self.save_to_disk()
        
        self.history_changed.emit()
    
    def export_entry(self, entry_id: str, path: str) -> bool:
        """
        Export a single entry and its backup artifacts to disk.
        
        Args:
            entry_id: The entry ID to export
            path: The path to export to
        
        Returns:
            bool: True if successful
        """
        entry = self.get_entry(entry_id)
        if not entry:
            return False
        
        try:
            data = entry.to_dict()
            
            # Load external features if any
            features = self._load_features(entry)
            data['features'] = features
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"HistoryManager: Failed to export entry: {e}")
            return False
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    @staticmethod
    def create_layer_descriptor(layer: QgsVectorLayer) -> Dict:
        """
        Create a layer descriptor dictionary for a layer.
        
        Args:
            layer: The QgsVectorLayer to describe
        
        Returns:
            dict: Layer descriptor with id, name, source, and type info
        """
        return {
            'layer_id': layer.id(),
            'layer_name': layer.name(),
            'data_source': layer.dataProvider().dataSourceUri() if layer.dataProvider() else '',
            'is_temporary': layer.dataProvider().name() == 'memory' if layer.dataProvider() else True,
            'geometry_type': QgsWkbTypes.displayString(layer.wkbType()),
            'crs': layer.crs().authid() if layer.crs().isValid() else ''
        }
    
    @staticmethod
    def create_feature_backup(
        feature: QgsFeature,
        layer: QgsVectorLayer,
        include_geometry: bool = True,
        include_attributes: bool = True
    ) -> Dict:
        """
        Create a feature backup dictionary.
        
        Args:
            feature: The QgsFeature to backup
            layer: The layer the feature belongs to
            include_geometry: Whether to include geometry
            include_attributes: Whether to include attributes
        
        Returns:
            dict: Feature backup with fid, geometry, and attributes
        """
        import base64
        
        backup = {
            'fid': feature.id(),
            'orig_fid_preserved': True
        }
        
        if include_geometry and feature.hasGeometry():
            geom = feature.geometry()
            # Use WKB for accuracy
            backup['geometry'] = {
                'wkb_base64': base64.b64encode(geom.asWkb()).decode('utf-8')
            }
        
        if include_attributes:
            attrs = {}
            for field in layer.fields():
                idx = layer.fields().indexOf(field.name())
                if idx >= 0:
                    value = feature.attribute(idx)
                    # Convert to JSON-serializable types
                    if hasattr(value, 'isNull') and value.isNull():
                        value = None
                    attrs[field.name()] = value
            backup['attributes'] = attrs
        
        return backup


# Create singleton instance for easy access
def get_history_manager() -> HistoryManager:
    """Get the singleton HistoryManager instance."""
    return HistoryManager()
