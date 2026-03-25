"""
Action Loader for Right-click Utilities and Shortcuts Hub

This module automatically discovers and loads all action modules from the actions directory.
It provides a centralized way to register all available actions.
"""

import os
import importlib
import inspect
from .base_action import BaseAction


class ActionLoader:
    """
    Loads and manages all available actions from the actions directory.
    """
    
    def __init__(self):
        """Initialize the action loader."""
        self.actions = []
        self._load_actions()
    
    def _load_actions(self):
        """Load all actions from the actions directory."""
        # Get the directory containing this file
        actions_dir = os.path.dirname(__file__)
        
        # Get all Python files in the actions directory
        for filename in os.listdir(actions_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]  # Remove .py extension
                
                try:
                    # Import the module
                    module = importlib.import_module(f'.{module_name}', package='RightclickActionsToolkit.actions')
                    
                    # Look for action instances in the module
                    for name, obj in inspect.getmembers(module):
                        if (isinstance(obj, BaseAction) and 
                            not name.startswith('_') and 
                            hasattr(obj, 'action_id')):
                            
                            # Validate action configuration
                            try:
                                obj.validate_action_configuration()
                                # Add the action to our list
                                self.actions.append(obj)
                                print(f"Loaded action: {obj.name} (ID: {obj.action_id}, Scope: {obj.action_scope})")
                            except ValueError as e:
                                print(f"Warning: Skipping invalid action '{name}' from {module_name}: {e}")
                            
                except Exception as e:
                    print(f"Warning: Failed to load action from {module_name}: {e}")
    
    def get_all_actions(self):
        """
        Get all loaded actions.
        
        Returns:
            list: List of BaseAction instances
        """
        return self.actions.copy()
    
    def get_action_by_id(self, action_id):
        """
        Get an action by its ID.
        
        Args:
            action_id (str): The action ID to search for
            
        Returns:
            BaseAction or None: The action if found, None otherwise
        """
        for action in self.actions:
            if action.action_id == action_id:
                return action
        return None
    
    def get_actions_by_category(self):
        """
        Get actions grouped by category.
        
        Returns:
            dict: Dictionary with categories as keys and action lists as values
        """
        categories = {}
        for action in self.actions:
            category = action.category or 'Other'
            if category not in categories:
                categories[category] = []
            categories[category].append(action)
        return categories
    
    def reload_actions(self):
        """
        Reload all actions from the actions directory.
        This is useful for development when actions are modified.
        """
        self.actions.clear()
        self._load_actions()


# Create a global instance for easy importing
action_loader = ActionLoader()
