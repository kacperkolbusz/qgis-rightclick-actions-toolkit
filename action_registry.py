"""
Action Registry Module for Right-click Utilities and Shortcuts Hub

This module provides a modular system for registering and managing right-click actions.
It automatically loads actions from separate files and manages their settings.
"""

from qgis.PyQt.QtCore import QSettings
from .actions.action_loader import action_loader


class ActionRegistry:
    """
    Registry for managing right-click actions with enable/disable functionality.
    """
    
    def __init__(self):
        """Initialize the action registry."""
        self.settings = QSettings()
        self._load_actions()
        
    def _load_actions(self):
        """Load actions from the action loader and apply settings."""
        # Get all actions from the action loader
        loaded_actions = action_loader.get_all_actions()
        
        # Apply settings to each action
        for action in loaded_actions:
            # Load saved setting or use default
            enabled = self.settings.value(f"RightClickUtilities/{action.action_id}", action.enabled, type=bool)
            action.enabled = enabled
    
    def register_action(self, action_id, name, callback, enabled=True, category=None, description=""):
        """
        Register a new action in the registry.
        
        Args:
            action_id (str): Unique identifier for the action
            name (str): Display name for the action
            callback (callable): Function to call when action is triggered
            enabled (bool): Whether the action is enabled by default
            category (str): Optional category for grouping actions
            description (str): Optional description of the action
        """
        # Check if action already exists
        for existing_action in self.actions:
            if existing_action['id'] == action_id:
                # Update existing action
                existing_action.update({
                    'name': name,
                    'callback': callback,
                    'category': category,
                    'description': description
                })
                return
        
        # Add new action
        action = {
            'id': action_id,
            'name': name,
            'callback': callback,
            'enabled': enabled,
            'category': category,
            'description': description
        }
        
        # Load saved setting
        enabled = self.settings.value(f"RightClickUtilities/{action_id}", enabled, type=bool)
        action['enabled'] = enabled
        
        self.actions.append(action)
    
    def get_enabled_actions(self):
        """
        Get list of enabled actions.
        
        Returns:
            list: List of enabled BaseAction instances
        """
        return [action for action in action_loader.get_all_actions() if action.enabled]
    
    def get_actions_by_category(self):
        """
        Get actions grouped by category.
        
        Returns:
            dict: Dictionary with categories as keys and action lists as values
        """
        return action_loader.get_actions_by_category()
    
    def set_action_enabled(self, action_id, enabled):
        """
        Enable or disable an action.
        
        Args:
            action_id (str): ID of the action to modify
            enabled (bool): Whether to enable the action
        """
        action = action_loader.get_action_by_id(action_id)
        if action:
            action.enabled = enabled
            # Save setting
            self.settings.setValue(f"RightClickUtilities/{action_id}", enabled)
    
    def get_action(self, action_id):
        """
        Get an action by its ID.
        
        Args:
            action_id (str): ID of the action
            
        Returns:
            BaseAction or None: Action instance or None if not found
        """
        return action_loader.get_action_by_id(action_id)
    
    def get_all_actions(self):
        """
        Get all registered actions.
        
        Returns:
            list: List of all BaseAction instances
        """
        return action_loader.get_all_actions()
    
