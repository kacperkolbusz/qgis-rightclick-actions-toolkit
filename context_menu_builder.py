"""
Context Menu Builder Module for Right-click Utilities and Shortcuts Hub

This module provides dynamic context menu generation based on detected features
and their types, supporting multiple overlapping features and context-aware actions.
"""

from qgis.PyQt.QtWidgets import QMenu, QAction
from qgis.core import QgsFeature, QgsVectorLayer
from typing import List, Dict, Optional
from .feature_detector import DetectedFeature
from .actions.base_action import BaseAction


class ContextMenuBuilder:
    """
    Builder for dynamic context menus based on detected features.
    
    Creates hierarchical menus that allow users to choose between overlapping
    features and shows appropriate actions for each feature type.
    """
    
    def __init__(self, action_registry):
        """
        Initialize the context menu builder.
        
        Args:
            action_registry: ActionRegistry instance for getting available actions
        """
        self.action_registry = action_registry
    
    def build_context_menu(self, menu: QMenu, context: dict) -> bool:
        """
        Build and populate the context menu based on the click context.
        
        Args:
            menu: QGIS context menu to populate
            context: Click context dictionary from FeatureDetector
            
        Returns:
            True if menu items were added, False otherwise
        """
        click_type = context.get('click_type', 'canvas')
        detected_features = context.get('detected_features', [])
        
        print(f"Building context menu for click_type: {click_type}, features: {len(detected_features)}")
        
        if not detected_features:
            # No features detected - show canvas actions
            print("No features detected, showing canvas actions")
            return self._add_canvas_actions(menu, context)
        elif len(detected_features) == 1:
            # Single feature detected - show actions directly in main menu
            print(f"Single feature detected: {detected_features[0].geometry_type}")
            return self._add_single_feature_direct_actions(menu, detected_features[0], context)
        else:
            # Multiple features detected - show hierarchical menu with feature selection
            print(f"Multiple features detected: {len(detected_features)}")
            return self._add_multi_feature_hierarchical_menu(menu, detected_features, context)
    
    def _add_canvas_actions(self, menu: QMenu, context: dict) -> bool:
        """
        Add actions for canvas clicks (no features detected) with universal actions at bottom.
        
        Args:
            menu: Menu to add actions to
            context: Click context
            
        Returns:
            True if actions were added
        """
        # Get canvas-specific actions
        canvas_actions = self._get_actions_for_scope_and_type('universal', 'canvas')
        
        print(f"Canvas actions available: {len(canvas_actions)}")
        
        # Add canvas actions
        for action in canvas_actions:
            action_item = menu.addAction(action.name)
            action_item.triggered.connect(
                lambda checked, action_obj=action: action_obj.execute(context)
            )
        
        # Add separator before universal actions
        menu.addSeparator()
        
        # Add universal actions at the bottom
        self._add_universal_actions(menu, context)
        
        print(f"Added {len(canvas_actions) + 1} canvas actions to menu")
        return True
    
    def _add_single_feature_direct_actions(self, menu: QMenu, feature: DetectedFeature, context: dict) -> bool:
        """
        Add actions for a single detected feature directly to the main menu.
        
        Args:
            menu: Menu to add actions to
            feature: Detected feature
            context: Click context
            
        Returns:
            True if actions were added
        """
        geometry_type = feature.geometry_type
        
        # Create a specific context for this feature that contains only this feature
        # This ensures actions work on the specific selected feature, not the first detected one
        specific_context = context.copy()
        specific_context['feature'] = feature.feature
        specific_context['layer'] = feature.layer
        specific_context['detected_features'] = [feature]  # Only this specific feature
        
        # Add feature-specific actions directly to main menu
        feature_actions = self._get_actions_for_scope_and_type('feature', geometry_type)
        for action in feature_actions:
            action_item = menu.addAction(action.name)
            action_item.triggered.connect(
                lambda checked, action_obj=action: action_obj.execute(specific_context)
            )
        
        # Add layer-specific actions
        layer_actions = self._get_actions_for_scope_and_type('layer', geometry_type)
        if layer_actions:
            menu.addSeparator()
            for action in layer_actions:
                action_item = menu.addAction(action.name)
                action_item.triggered.connect(
                    lambda checked, action_obj=action: action_obj.execute(specific_context)
                )
        
        # Add universal actions at the bottom
        universal_actions = self._get_actions_for_scope_and_type('universal', geometry_type)
        if universal_actions:
            menu.addSeparator()
            for action in universal_actions:
                action_item = menu.addAction(action.name)
                action_item.triggered.connect(
                    lambda checked, action_obj=action: action_obj.execute(specific_context)
                )
        
        # Also add general universal actions (not filtered by geometry type)
        general_universal_actions = self._get_general_universal_actions()
        if general_universal_actions:
            if not universal_actions:  # Only add separator if we didn't already add one
                menu.addSeparator()
            for action in general_universal_actions:
                action_item = menu.addAction(action.name)
                action_item.triggered.connect(
                    lambda checked, action_obj=action: action_obj.execute(specific_context)
                )
        
        return True
    
    def _add_single_feature_hierarchical_menu(self, menu: QMenu, feature: DetectedFeature, context: dict) -> bool:
        """
        Add hierarchical menu for a single detected feature with feature/layer/universal structure.
        
        Args:
            menu: Menu to add actions to
            feature: Detected feature
            context: Click context
            
        Returns:
            True if actions were added
        """
        geometry_type = feature.geometry_type
        layer_name = feature.layer.name()
        
        # Create main feature menu
        feature_menu_text = f"{geometry_type.title()} Feature - {layer_name}"
        feature_menu = menu.addMenu(feature_menu_text)
        
        # Add feature-specific actions
        feature_actions = self._get_actions_for_scope_and_type('feature', geometry_type)
        for action in feature_actions:
            action_item = feature_menu.addAction(action.name)
            action_item.triggered.connect(
                lambda checked, action_obj=action: action_obj.execute(context)
            )
        
        # Add layer-specific actions
        layer_actions = self._get_actions_for_scope_and_type('layer', geometry_type)
        if layer_actions:
            feature_menu.addSeparator()
            for action in layer_actions:
                action_item = feature_menu.addAction(action.name)
                action_item.triggered.connect(
                    lambda checked, action_obj=action: action_obj.execute(context)
                )
        
        
        return True
    
    def _add_multi_feature_hierarchical_menu(self, menu: QMenu, features: List[DetectedFeature], context: dict) -> bool:
        """
        Add hierarchical menu for multiple detected features with feature/layer/universal structure.
        
        Args:
            menu: Menu to add actions to
            features: List of detected features
            context: Click context
            
        Returns:
            True if actions were added
        """
        # Group features by type for better organization
        features_by_type = self._group_features_by_type(features)
        
        # Sort feature types alphabetically
        sorted_types = sorted(features_by_type.keys())
        
        # Add feature selection menus at the top
        for feature_type in sorted_types:
            type_features = features_by_type[feature_type]
            
            if len(type_features) == 1:
                # Single feature of this type - create submenu for this feature
                feature = type_features[0]
                feature_label = f"{feature_type.title()} Feature - {feature.layer.name()}"
                feature_submenu = menu.addMenu(feature_label)
                self._add_feature_hierarchical_submenu(feature_submenu, feature, context)
            else:
                # Multiple features of this type - create submenu for each feature
                # Sort features by distance (closest first)
                sorted_features = sorted(type_features, key=lambda f: f.distance)
                
                for i, feature in enumerate(sorted_features):
                    # Create feature label with distance info
                    feature_label = self._create_feature_label(feature, i + 1)
                    feature_submenu = menu.addMenu(feature_label)
                    self._add_feature_hierarchical_submenu(feature_submenu, feature, context)
        
        # Add universal actions at the bottom
        menu.addSeparator()
        self._add_universal_actions(menu, context)
        
        return True
    
    def _add_feature_hierarchical_submenu(self, submenu: QMenu, feature: DetectedFeature, context: dict):
        """
        Add hierarchical submenu for a specific feature with feature/layer/universal structure.
        
        Args:
            submenu: Submenu to add actions to
            feature: Feature to add actions for
            context: Click context
        """
        geometry_type = feature.geometry_type
        
        # Create a specific context for this feature that contains only this feature
        # This ensures actions work on the specific selected feature, not the first detected one
        specific_context = context.copy()
        specific_context['feature'] = feature.feature
        specific_context['layer'] = feature.layer
        specific_context['detected_features'] = [feature]  # Only this specific feature
        
        # Add feature-specific actions
        feature_actions = self._get_actions_for_scope_and_type('feature', geometry_type)
        for action in feature_actions:
            action_item = submenu.addAction(action.name)
            action_item.triggered.connect(
                lambda checked, action_obj=action: action_obj.execute(specific_context)
            )
        
        # Add layer-specific actions
        layer_actions = self._get_actions_for_scope_and_type('layer', geometry_type)
        if layer_actions:
            submenu.addSeparator()
            for action in layer_actions:
                action_item = submenu.addAction(action.name)
                action_item.triggered.connect(
                    lambda checked, action_obj=action: action_obj.execute(specific_context)
                )
        
    
    
    
    
    def _add_universal_actions(self, menu: QMenu, context: dict):
        """
        Add universal actions to the menu.
        
        Args:
            menu: Menu to add universal actions to
            context: Click context
        """
        # Get universal actions (actions that support 'universal' scope and click type)
        universal_actions = self._get_general_universal_actions()
        
        if universal_actions:
            # Add universal actions
            for action in universal_actions:
                action_item = menu.addAction(action.name)
                action_item.triggered.connect(
                    lambda checked, action_obj=action: action_obj.execute(context)
                )
    
    
    def _group_features_by_type(self, features: List[DetectedFeature]) -> Dict[str, List[DetectedFeature]]:
        """
        Group features by their geometry type.
        
        Args:
            features: List of detected features
            
        Returns:
            Dictionary with geometry types as keys and feature lists as values
        """
        grouped = {}
        for feature in features:
            feature_type = feature.geometry_type
            if feature_type not in grouped:
                grouped[feature_type] = []
            grouped[feature_type].append(feature)
        return grouped
    
    def _create_feature_label(self, feature: DetectedFeature, index: int) -> str:
        """
        Create a descriptive label for a feature in the menu.
        
        Args:
            feature: Feature to create label for
            index: Index of the feature (for numbering)
            
        Returns:
            Descriptive label string
        """
        layer_name = feature.layer.name()
        feature_id = feature.feature.id()
        
        return f"{feature.geometry_type.title()} #{index} - {layer_name} (ID: {feature_id})"
    
    def _get_actions_for_click_type(self, click_type: str) -> List[BaseAction]:
        """
        Get all available actions for a specific click type (excluding universal actions).
        
        Args:
            click_type: Type of click ('point', 'line', 'polygon', 'canvas', etc.)
            
        Returns:
            List of available actions for this click type (excluding universal actions)
        """
        all_actions = self.action_registry.get_enabled_actions()
        available_actions = []
        
        for action in all_actions:
            # Check if action supports this specific click type
            # Exclude universal actions - they should only be added separately
            if (action.is_available_for_context({'click_type': click_type}) and 
                not action.supports_click_type('universal')):
                available_actions.append(action)
        
        return available_actions
    
    def _get_actions_for_scope_and_type(self, scope: str, geometry_type: str) -> List[BaseAction]:
        """
        Get all available actions for a specific scope and geometry type.
        
        Args:
            scope: Action scope ('feature', 'layer', 'universal')
            geometry_type: Geometry type ('point', 'line', 'polygon', etc.)
            
        Returns:
            List of available actions for this scope and geometry type
        """
        all_actions = self.action_registry.get_enabled_actions()
        available_actions = []
        
        for action in all_actions:
            # Check if action supports this scope and geometry type
            if (action.supports_scope(scope) and 
                action.supports_geometry_type(geometry_type)):
                available_actions.append(action)
        
        return available_actions
    
    def _get_general_universal_actions(self) -> List[BaseAction]:
        """
        Get all universal actions that work everywhere (not filtered by geometry type).
        
        Returns:
            List of universal actions
        """
        all_actions = self.action_registry.get_enabled_actions()
        universal_actions = []
        
        for action in all_actions:
            # Check if action supports universal scope and has universal click type
            if (action.supports_scope('universal') and 
                action.supports_click_type('universal')):
                universal_actions.append(action)
        
        return universal_actions
    
