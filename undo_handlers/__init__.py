"""
Undo Handlers Package for Right-click Actions Toolkit

This package contains modular undo/redo handlers for different operation types.
Each handler is responsible for undoing and redoing a specific type of operation.

To add a new undo type:
1. Create a new file: my_handler.py
2. Inherit from BaseUndoHandler
3. Implement undo() and redo() methods
4. Register in handler_registry.py

See ACTION_DEVELOPMENT_GUIDE.md for detailed instructions.
"""

from .handler_registry import UndoHandlerRegistry, get_handler_registry
from .base_handler import BaseUndoHandler

__all__ = [
    'UndoHandlerRegistry',
    'get_handler_registry',
    'BaseUndoHandler',
]

# Ensure handlers that are added to the package get imported when the package is imported.
# This helps guarantee handlers are available to the registry even if discovery timing
# would otherwise miss recently added handler files.
try:
    from . import update_rendering_handler  # noqa: F401
except Exception:
    pass
