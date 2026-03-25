"""
Undo Handler Registry for Right-click Actions Toolkit

This module provides a registry for undo handlers, automatically discovering
and loading handlers from the undo_handlers package.

Usage:
    from undo_handlers import get_handler_registry
    
    registry = get_handler_registry()
    handler = registry.get_handler('create_feature')
    success, message = handler.undo(entry)
"""

import os
import importlib
from typing import Dict, Optional, Type, Any

from .base_handler import BaseUndoHandler


class UndoHandlerRegistry:
    """
    Registry for undo handlers.
    
    Maintains a mapping of undo_type strings to handler instances.
    Automatically discovers handlers in the undo_handlers package.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the registry."""
        if self._initialized:
            return
        
        self._initialized = True
        self._handlers: Dict[str, BaseUndoHandler] = {}
        
        # Auto-discover and register handlers
        self._discover_handlers()
    
    def _discover_handlers(self) -> None:
        """
        Automatically discover and register all handlers in the package.
        
        Looks for files ending in '_handler.py' and registers any handlers
        that define the 'handler' singleton instance.
        """
        package_dir = os.path.dirname(__file__)
        
        # Get the actual package name (works when running as QGIS plugin)
        # __name__ will be something like 'RightclickActionsToolkit.undo_handlers.handler_registry'
        # We need 'RightclickActionsToolkit.undo_handlers'
        current_package = __name__.rsplit('.', 1)[0] if '.' in __name__ else __name__
        
        for filename in os.listdir(package_dir):
            if filename.endswith('_handler.py') and filename != 'base_handler.py':
                module_name = filename[:-3]  # Remove .py
                
                try:
                    # Import the module using the correct package path
                    module = importlib.import_module(f'.{module_name}', package=current_package)
                    
                    # Look for the 'handler' singleton
                    if hasattr(module, 'handler'):
                        handler = module.handler
                        if isinstance(handler, BaseUndoHandler):
                            self.register(handler)
                            
                            # Special handling for composite handler
                            if handler.undo_type == 'composite' and hasattr(handler, 'set_handler_registry'):
                                handler.set_handler_registry(self)
                
                except Exception as e:
                    # Log error but continue with other handlers
                    print(f"Warning: Failed to load undo handler from {filename}: {e}")
    
    def register(self, handler: BaseUndoHandler) -> None:
        """
        Register an undo handler.
        
        Args:
            handler: The handler instance to register
        """
        if not hasattr(handler, 'undo_type') or not handler.undo_type:
            raise ValueError(f"Handler {handler.__class__.__name__} must define 'undo_type'")
        
        self._handlers[handler.undo_type] = handler
    
    def register_custom(self, undo_type: str, handler: BaseUndoHandler) -> None:
        """
        Register a custom handler for a specific undo type.
        
        This can be used to override default handlers or add new types.
        
        Args:
            undo_type: The undo type string
            handler: The handler instance
        """
        self._handlers[undo_type] = handler
    
    def unregister(self, undo_type: str) -> None:
        """
        Unregister a handler.
        
        Args:
            undo_type: The undo type to unregister
        """
        if undo_type in self._handlers:
            del self._handlers[undo_type]
    
    def get_handler(self, undo_type: str) -> Optional[BaseUndoHandler]:
        """
        Get a handler for the specified undo type.
        
        Args:
            undo_type: The undo type string
        
        Returns:
            BaseUndoHandler instance or None if not found
        """
        return self._handlers.get(undo_type)
    
    def has_handler(self, undo_type: str) -> bool:
        """
        Check if a handler exists for the undo type.
        
        Args:
            undo_type: The undo type string
        
        Returns:
            True if handler exists
        """
        return undo_type in self._handlers
    
    def get_registered_types(self) -> list:
        """
        Get a list of all registered undo types.
        
        Returns:
            List of undo type strings
        """
        return list(self._handlers.keys())
    
    def undo(self, entry: Any) -> tuple:
        """
        Perform undo using the appropriate handler.
        
        Args:
            entry: HistoryEntry to undo
        
        Returns:
            Tuple of (success, message)
        """
        handler = self.get_handler(entry.undo_type)
        
        if not handler:
            return False, f"No handler registered for undo type: {entry.undo_type}"
        
        return handler.undo(entry)
    
    def redo(self, entry: Any) -> tuple:
        """
        Perform redo using the appropriate handler.
        
        Args:
            entry: HistoryEntry to redo
        
        Returns:
            Tuple of (success, message)
        """
        handler = self.get_handler(entry.undo_type)
        
        if not handler:
            return False, f"No handler registered for undo type: {entry.undo_type}"
        
        return handler.redo(entry)


# Singleton accessor
_registry_instance = None

def get_handler_registry() -> UndoHandlerRegistry:
    """
    Get the singleton UndoHandlerRegistry instance.
    
    Returns:
        UndoHandlerRegistry singleton
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = UndoHandlerRegistry()
    return _registry_instance
