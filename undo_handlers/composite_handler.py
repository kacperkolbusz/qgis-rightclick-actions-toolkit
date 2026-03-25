"""
Composite Undo Handler

Handles undo/redo for actions that perform MULTIPLE operations.

A composite action bundles multiple operations (e.g., create multiple features,
update multiple layers) into a single undoable action.

Undo: Undo all sub-operations in reverse order
Redo: Redo all sub-operations in original order
"""

from typing import Tuple, Dict, List
from .base_handler import BaseUndoHandler

try:
    from qgis.core import QgsProject
except ImportError:
    pass


class CompositeHandler(BaseUndoHandler):
    """
    Handler for undoing composite (multi-operation) actions.
    
    The payload should contain a list of sub-operations, each with its own
    undo type and data.
    """
    
    undo_type = "composite"
    
    def __init__(self):
        super().__init__()
        self._handler_registry = None
    
    def set_handler_registry(self, registry):
        """Set reference to handler registry for sub-operation handling."""
        self._handler_registry = registry
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo all sub-operations in reverse order.
        
        Args:
            entry: HistoryEntry with sub-operations list
        
        Returns:
            Tuple of (success, message)
        """
        sub_operations = entry.undo_payload.get('sub_operations', []) if entry.undo_payload else []
        
        if not sub_operations:
            return False, "No sub-operations found in composite action"

        if not self._handler_registry:
            return False, "Handler registry not available for composite undo"

        # Working copies to collect updated layer/feature descriptors
        working_layers = list(entry.layers or [])
        working_features = list(entry.features or [])

        def _merge_descriptors(target_list, updated_list, key='layer_id'):
            """Merge updated descriptors into target_list by key; replace or append."""
            if not updated_list:
                return target_list
            by_key = {d.get(key): d for d in target_list if d.get(key) is not None}
            for d in updated_list:
                k = d.get(key)
                if k is not None and k in by_key:
                    # replace
                    for idx, existing in enumerate(target_list):
                        if existing.get(key) == k:
                            target_list[idx] = d
                            break
                else:
                    target_list.append(d)
            return target_list

        # Undo in reverse order
        undone_count = 0
        for i, sub_op in enumerate(reversed(sub_operations)):
            sub_type = sub_op.get('undo_type')

            if not sub_type:
                continue

            handler = self._handler_registry.get_handler(sub_type)
            if not handler:
                if entry.atomic:
                    return False, f"No handler for sub-operation type: {sub_type}"
                continue

            # Prepare the main entry with sub-operation context so handlers update the real entry
            orig_layers = entry.layers
            orig_features = entry.features
            orig_undo_payload = entry.undo_payload
            orig_redo_payload = getattr(entry, 'redo_payload', None)

            try:
                # Use updated working_layers from previous sub-ops; update sub_op layers before running handler
                sub_op['layers'] = working_layers
                entry.layers = working_layers
                # Each sub-op carries its own feature set; only fall back to the
                # shared working_features pool when the sub-op has no features of its own.
                sub_op_features = sub_op.get('features')
                entry.features = list(sub_op_features) if sub_op_features is not None else list(working_features)
                entry.undo_payload = sub_op.get('undo_payload', {})
                entry.redo_payload = sub_op.get('redo_payload', None)

                success, message = handler.undo(entry)

                if not success:
                    if entry.atomic:
                        # restore original entry state before returning
                        entry.layers = orig_layers
                        entry.features = orig_features
                        entry.undo_payload = orig_undo_payload
                        entry.redo_payload = orig_redo_payload
                        return False, f"Composite undo failed at step {len(sub_operations) - i}: {message}"
                    # Non-atomic: continue
                else:
                    undone_count += 1

                # Persist any updates back into the sub-operation descriptor
                sub_op['layers'] = entry.layers or []
                sub_op['features'] = entry.features or []
                sub_op['undo_payload'] = entry.undo_payload or {}
                if hasattr(entry, 'redo_payload') and entry.redo_payload is not None:
                    sub_op['redo_payload'] = entry.redo_payload

                # Merge updates into working collections
                working_layers = _merge_descriptors(working_layers, sub_op.get('layers', []), key='layer_id')
                # For features, merge by fid to avoid duplicates
                if sub_op.get('features'):
                    updated_features = sub_op.get('features', [])
                    # Build map of existing features by fid
                    by_fid = {f.get('fid'): f for f in working_features if f.get('fid') is not None}
                    for f in updated_features:
                        fid = f.get('fid')
                        if fid is not None:
                            by_fid[fid] = f  # Replace if exists, otherwise add
                        else:
                            working_features.append(f)  # No fid, append as-is
                    # Rebuild working_features from map
                    working_features = list(by_fid.values())

            finally:
                # Restore main entry to composite-level collections for next sub-op
                entry.layers = working_layers
                entry.features = working_features
                entry.undo_payload = orig_undo_payload
                entry.redo_payload = orig_redo_payload

        # After all sub-ops, persist consolidated descriptors
        entry.layers = working_layers
        entry.features = working_features

        return True, f"Composite undo completed ({undone_count}/{len(sub_operations)} operations)"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo all sub-operations in original order.
        
        Args:
            entry: HistoryEntry with sub-operations list
        
        Returns:
            Tuple of (success, message)
        """
        sub_operations = entry.undo_payload.get('sub_operations', []) if entry.undo_payload else []

        if not sub_operations:
            return False, "No sub-operations found in composite action"

        if not self._handler_registry:
            return False, "Handler registry not available for composite redo"

        # Working copies to collect updated layer/feature descriptors
        working_layers = list(entry.layers or [])
        working_features = list(entry.features or [])

        def _merge_descriptors(target_list, updated_list, key='layer_id'):
            if not updated_list:
                return target_list
            by_key = {d.get(key): d for d in target_list if d.get(key) is not None}
            for d in updated_list:
                k = d.get(key)
                if k is not None and k in by_key:
                    for idx, existing in enumerate(target_list):
                        if existing.get(key) == k:
                            target_list[idx] = d
                            break
                else:
                    target_list.append(d)
            return target_list

        # Redo in original order
        redone_count = 0
        for i, sub_op in enumerate(sub_operations):
            sub_type = sub_op.get('undo_type')

            if not sub_type:
                continue

            handler = self._handler_registry.get_handler(sub_type)
            if not handler:
                if entry.atomic:
                    return False, f"No handler for sub-operation type: {sub_type}"
                continue

            # Prepare the main entry with sub-operation context so handlers update the real entry
            orig_layers = entry.layers
            orig_features = entry.features
            orig_undo_payload = entry.undo_payload
            orig_redo_payload = getattr(entry, 'redo_payload', None)

            try:
                # Use updated working_layers from previous sub-ops; update sub_op layers before running handler
                sub_op['layers'] = working_layers
                entry.layers = working_layers
                # Each sub-op carries its own feature set; only fall back to the
                # shared working_features pool when the sub-op has no features of its own.
                sub_op_features = sub_op.get('features')
                entry.features = list(sub_op_features) if sub_op_features is not None else list(working_features)
                entry.undo_payload = sub_op.get('undo_payload', {})
                entry.redo_payload = sub_op.get('redo_payload', None)

                success, message = handler.redo(entry)

                if not success:
                    if entry.atomic:
                        entry.layers = orig_layers
                        entry.features = orig_features
                        entry.undo_payload = orig_undo_payload
                        entry.redo_payload = orig_redo_payload
                        return False, f"Composite redo failed at step {i + 1}: {message}"
                else:
                    redone_count += 1

                # Persist any updates back into the sub-operation descriptor
                sub_op['layers'] = entry.layers or []
                sub_op['features'] = entry.features or []
                sub_op['undo_payload'] = entry.undo_payload or {}
                if hasattr(entry, 'redo_payload') and entry.redo_payload is not None:
                    sub_op['redo_payload'] = entry.redo_payload

                # Merge updates into working collections
                working_layers = _merge_descriptors(working_layers, sub_op.get('layers', []), key='layer_id')
                # For features, merge by fid to avoid duplicates
                if sub_op.get('features'):
                    updated_features = sub_op.get('features', [])
                    # Build map of existing features by fid
                    by_fid = {f.get('fid'): f for f in working_features if f.get('fid') is not None}
                    for f in updated_features:
                        fid = f.get('fid')
                        if fid is not None:
                            by_fid[fid] = f  # Replace if exists, otherwise add
                        else:
                            working_features.append(f)  # No fid, append as-is
                    # Rebuild working_features from map
                    working_features = list(by_fid.values())

            finally:
                # Restore main entry to composite-level collections for next sub-op
                entry.layers = working_layers
                entry.features = working_features
                entry.undo_payload = orig_undo_payload
                entry.redo_payload = orig_redo_payload

        # After all sub-ops, persist consolidated descriptors
        entry.layers = working_layers
        entry.features = working_features

        return True, f"Composite redo completed ({redone_count}/{len(sub_operations)} operations)"


# Create singleton instance for registration
handler = CompositeHandler()
