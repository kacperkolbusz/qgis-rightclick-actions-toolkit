"""
View Change Undo Handler

Handles undo/redo for actions that change the map view (scale, center, extent).

Undo: Restore previous view state
Redo: Re-apply the view change
"""

from typing import Tuple, Dict
from .base_handler import BaseUndoHandler

try:
    from qgis.utils import iface
    from qgis.core import QgsPointXY
except ImportError:
    pass


class ViewChangeHandler(BaseUndoHandler):
    """
    Handler for undoing view/scale changes.
    
    This handles zoom, pan, and extent changes.
    """
    
    undo_type = "view_change"
    
    def undo(self, entry) -> Tuple[bool, str]:
        """
        Undo a view/scale change by restoring previous center and scale.
        
        Args:
            entry: HistoryEntry with previous view state
        
        Returns:
            Tuple of (success, message)
        """
        try:
            payload = entry.undo_payload or {}
            prev_scale = payload.get('scale')
            prev_center = payload.get('center')  # dict with x, y

            canvas = iface.mapCanvas()
            
            if prev_scale:
                canvas.zoomScale(prev_scale)

            if prev_center and isinstance(prev_center, dict):
                x = prev_center.get('x')
                y = prev_center.get('y')
                if x is not None and y is not None:
                    try:
                        pt = QgsPointXY(float(x), float(y))
                        canvas.setCenter(pt)
                    except Exception:
                        pass

            canvas.refresh()
            return True, "View restored"
            
        except Exception as e:
            return False, f"Failed to restore view: {e}"
    
    def redo(self, entry) -> Tuple[bool, str]:
        """
        Redo a view change by applying the redo payload.
        
        Args:
            entry: HistoryEntry with view state to apply
        
        Returns:
            Tuple of (success, message)
        """
        try:
            payload = entry.redo_payload or entry.undo_payload or {}
            scale = payload.get('scale')
            center = payload.get('center')

            canvas = iface.mapCanvas()
            
            if scale:
                canvas.zoomScale(scale)

            if center and isinstance(center, dict):
                x = center.get('x')
                y = center.get('y')
                if x is not None and y is not None:
                    try:
                        pt = QgsPointXY(float(x), float(y))
                        canvas.setCenter(pt)
                    except Exception:
                        pass

            canvas.refresh()
            return True, "View re-applied"
            
        except Exception as e:
            return False, f"Failed to re-apply view: {e}"


# Create singleton instance for registration
handler = ViewChangeHandler()
