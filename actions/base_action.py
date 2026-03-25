"""
Base Action Class for Right-click Utilities and Shortcuts Hub

This module provides a base class that all right-click actions should inherit from.
It provides common functionality and ensures consistent behavior across all actions.
"""

from abc import ABC, abstractmethod
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsFeature, QgsVectorLayer, QgsPointXY
from qgis.gui import QgsMapCanvas


class BaseAction(ABC):
    """
    Base class for all right-click actions.
    
    All actions should inherit from this class and implement the execute method.
    This ensures consistent behavior and provides common functionality.
    
    Undo System Integration:
        Actions can optionally implement undo functionality by overriding:
        - supports_undo() -> bool: Return True if action supports undo
        - get_undo_payload(context, execute_result) -> dict: Return undo data
        - apply_undo(payload) -> Tuple[bool, str]: Custom undo implementation
        - apply_redo(payload) -> Tuple[bool, str]: Custom redo implementation
        
        See ACTION_DEVELOPMENT_GUIDE.md for detailed undo implementation guide.
    """
    
    def __init__(self):
        """Initialize the base action."""
        self.action_id = None
        self.name = None
        self.category = None
        self.description = None
        self.enabled = True
        
        # Feature type support metadata
        self.supported_geometry_types = []  # List of supported geometry types: 'point', 'line', 'polygon', 'canvas'
        self.supported_click_types = []     # List of supported click types: 'point', 'line', 'polygon', 'canvas', 'mixed'
        
        # Action scope metadata - NEW
        self.action_scope = 'feature'  # 'feature', 'layer', 'universal'
        self.supported_scopes = ['feature']  # List of supported scopes
        
        # Valid scope options - enforced by the system
        self.VALID_SCOPES = ['feature', 'layer', 'universal']
        
        # Undo system metadata
        # Valid undo categories for classifying actions
        self.UNDO_CATEGORIES = [
            'none',           # No undo needed (informational actions)
            'trivial',        # Simple undo (create -> delete)
            'payload',        # Requires stored data (delete -> restore)
            'complex',        # Complex undo with external dependencies
            'informational'   # Display-only, logged but no undo
        ]
        
        # Internal storage for undo data (populated during execute)
        self._last_undo_payload = None
        self._last_context = None
        
    @abstractmethod
    def execute(self, context):
        """
        Execute the action.
        
        Args:
            context (dict): Context containing:
                - feature (QgsFeature): The clicked feature
                - layer (QgsVectorLayer): The active layer
                - canvas (QgsMapCanvas): The map canvas
                - map_point (QgsPointXY): The clicked point
        """
        pass
    
    def get_action_info(self):
        """
        Get action information for registration.
        
        Returns:
            dict: Action information dictionary
        """
        return {
            'id': self.action_id,
            'name': self.name,
            'callback': self.execute,
            'enabled': self.enabled,
            'category': self.category,
            'description': self.description,
            'supported_geometry_types': self.supported_geometry_types,
            'supported_click_types': self.supported_click_types
        }
    
    def supports_geometry_type(self, geometry_type: str) -> bool:
        """
        Check if this action supports a specific geometry type.
        
        Args:
            geometry_type: Geometry type to check ('point', 'line', 'polygon', 'canvas')
            
        Returns:
            True if the action supports this geometry type
        """
        return geometry_type in self.supported_geometry_types
    
    def supports_click_type(self, click_type: str) -> bool:
        """
        Check if this action supports a specific click type.
        
        Args:
            click_type: Click type to check ('point', 'line', 'polygon', 'canvas', 'mixed')
            
        Returns:
            True if the action supports this click type
        """
        return click_type in self.supported_click_types
    
    def is_available_for_context(self, context: dict) -> bool:
        """
        Check if this action is available for the given context.
        
        Args:
            context: Context dictionary containing click information
            
        Returns:
            True if the action is available for this context
        """
        click_type = context.get('click_type', 'canvas')
        
        # Universal actions are available for any context
        if self.supports_click_type('universal'):
            return True
        
        # Check if action supports the specific click type
        return self.supports_click_type(click_type)
    
    def set_supported_geometry_types(self, geometry_types: list):
        """
        Set the supported geometry types for this action.
        
        Args:
            geometry_types: List of supported geometry types
        """
        self.supported_geometry_types = geometry_types
    
    def set_supported_click_types(self, click_types: list):
        """
        Set the supported click types for this action.
        
        Args:
            click_types: List of supported click types
        """
        self.supported_click_types = click_types
    
    def set_action_scope(self, scope: str):
        """
        Set the primary action scope for this action.
        
        Args:
            scope: Action scope ('feature', 'layer', 'universal')
            
        Raises:
            ValueError: If scope is not valid
        """
        if scope not in self.VALID_SCOPES:
            raise ValueError(f"Invalid action scope '{scope}'. Must be one of: {self.VALID_SCOPES}")
        self.action_scope = scope
    
    def set_supported_scopes(self, scopes: list):
        """
        Set the supported scopes for this action.
        
        Args:
            scopes: List of supported scopes ('feature', 'layer', 'universal')
            
        Raises:
            ValueError: If any scope is not valid
        """
        for scope in scopes:
            if scope not in self.VALID_SCOPES:
                raise ValueError(f"Invalid supported scope '{scope}'. Must be one of: {self.VALID_SCOPES}")
        self.supported_scopes = scopes
    
    def supports_scope(self, scope: str) -> bool:
        """
        Check if this action supports a specific scope.
        
        Args:
            scope: Scope to check ('feature', 'layer', 'universal')
            
        Returns:
            True if the action supports this scope
        """
        return scope in self.supported_scopes
    
    def validate_action_configuration(self) -> bool:
        """
        Validate that the action is properly configured.
        
        Returns:
            True if action is properly configured
            
        Raises:
            ValueError: If action configuration is invalid
        """
        # Check required properties
        if not self.action_id:
            raise ValueError("Action ID is required")
        if not self.name:
            raise ValueError("Action name is required")
        
        # Check scope configuration
        if self.action_scope not in self.VALID_SCOPES:
            raise ValueError(f"Invalid action scope '{self.action_scope}'. Must be one of: {self.VALID_SCOPES}")
        
        if not self.supported_scopes:
            raise ValueError("At least one supported scope must be specified")
        
        for scope in self.supported_scopes:
            if scope not in self.VALID_SCOPES:
                raise ValueError(f"Invalid supported scope '{scope}'. Must be one of: {self.VALID_SCOPES}")
        
        # Check that action_scope is in supported_scopes
        if self.action_scope not in self.supported_scopes:
            raise ValueError(f"Action scope '{self.action_scope}' must be included in supported_scopes: {self.supported_scopes}")
        
        # Check click types and geometry types
        if not self.supported_click_types:
            raise ValueError("At least one supported click type must be specified")
        
        if not self.supported_geometry_types:
            raise ValueError("At least one supported geometry type must be specified")
        
        return True
    
    def show_error(self, title, message):
        """
        Show an error message dialog.
        
        Args:
            title (str): Dialog title
            message (str): Error message
        """
        QMessageBox.critical(None, title, message)
    
    def show_info(self, title, message):
        """
        Show an information message dialog.
        
        Args:
            title (str): Dialog title
            message (str): Information message
        """
        QMessageBox.information(None, title, message)
    
    def show_warning(self, title, message):
        """
        Show a warning message dialog.
        
        Args:
            title (str): Dialog title
            message (str): Warning message
        """
        QMessageBox.warning(None, title, message)
    
    def confirm_action(self, title, message):
        """
        Show a confirmation dialog.
        
        Args:
            title (str): Dialog title
            message (str): Confirmation message
            
        Returns:
            bool: True if user confirmed, False otherwise
        """
        reply = QMessageBox.question(
            None,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes
    
    def handle_edit_mode(self, layer, operation_name="operation"):
        """
        Handle edit mode for the layer.
        
        Args:
            layer (QgsVectorLayer): The layer to handle edit mode for
            operation_name (str): Name of the operation for error messages
            
        Returns:
            tuple: (was_in_edit_mode, edit_mode_entered)
        """
        was_in_edit_mode = layer.isEditable()
        edit_mode_entered = False
        
        if not was_in_edit_mode:
            if not layer.startEditing():
                self.show_error(
                    "Error",
                    f"Failed to start editing the layer for {operation_name}. "
                    "The layer may be read-only or locked."
                )
                return None, None
            edit_mode_entered = True
        
        return was_in_edit_mode, edit_mode_entered
    
    def commit_changes(self, layer, operation_name="operation"):
        """
        Commit changes to the layer.
        
        Args:
            layer (QgsVectorLayer): The layer to commit changes for
            operation_name (str): Name of the operation for error messages
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not layer.commitChanges():
            self.show_error(
                "Error",
                f"Failed to commit changes for {operation_name}. "
                "The changes may not have been saved."
            )
            layer.rollBack()
            return False
        return True
    
    def rollback_changes(self, layer):
        """
        Rollback changes to the layer.
        
        Args:
            layer (QgsVectorLayer): The layer to rollback changes for
        """
        try:
            if layer.isEditable():
                layer.rollBack()
        except Exception:
            pass  # Ignore rollback errors
    
    def exit_edit_mode(self, layer, edit_mode_entered):
        """
        Exit edit mode if we entered it.
        
        Args:
            layer (QgsVectorLayer): The layer to exit edit mode for
            edit_mode_entered (bool): Whether we entered edit mode
        """
        if edit_mode_entered and layer.isEditable():
            try:
                layer.commitChanges()
                layer.stopEditing()
            except Exception:
                pass  # Ignore errors when stopping edit mode
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        This method should be overridden by subclasses to define their customizable settings.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {}
    
    def get_setting(self, setting_name, default_value=None):
        """
        Get a setting value for this action.
        
        Args:
            setting_name (str): Name of the setting to retrieve
            default_value: Default value if setting not found
            
        Returns:
            Setting value or default_value
        """
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def set_setting(self, setting_name, value):
        """
        Set a setting value for this action.
        
        Args:
            setting_name (str): Name of the setting to set
            value: Value to set
        """
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        settings.setValue(key, value)
    
    def reset_settings_to_defaults(self):
        """
        Reset all settings for this action to their default values.
        """
        schema = self.get_settings_schema()
        for setting_name, setting_def in schema.items():
            default_value = setting_def.get('default')
            if default_value is not None:
                self.set_setting(setting_name, default_value)
    
    def get_all_settings(self):
        """
        Get all current settings for this action.
        
        Returns:
            dict: Dictionary of all current settings
        """
        schema = self.get_settings_schema()
        settings = {}
        for setting_name, setting_def in schema.items():
            default_value = setting_def.get('default')
            settings[setting_name] = self.get_setting(setting_name, default_value)
        return settings
    
    def validate_setting(self, setting_name, value):
        """
        Validate a setting value.
        
        Args:
            setting_name (str): Name of the setting to validate
            value: Value to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        schema = self.get_settings_schema()
        if setting_name not in schema:
            return False, f"Unknown setting: {setting_name}"
        
        setting_def = schema[setting_name]
        setting_type = setting_def.get('type')
        
        # Type validation
        if setting_type == 'bool':
            if not isinstance(value, bool):
                return False, "Value must be True or False"
        elif setting_type in ['int', 'float']:
            try:
                if setting_type == 'int':
                    int(value)
                else:
                    float(value)
            except (ValueError, TypeError):
                return False, f"Value must be a valid {setting_type}"
            
            # Range validation
            min_val = setting_def.get('min')
            max_val = setting_def.get('max')
            if min_val is not None and value < min_val:
                return False, f"Value must be at least {min_val}"
            if max_val is not None and value > max_val:
                return False, f"Value must be at most {max_val}"
        elif setting_type == 'str':
            if not isinstance(value, str):
                return False, "Value must be a string"
        elif setting_type == 'choice':
            options = setting_def.get('options', [])
            if value not in options:
                return False, f"Value must be one of: {', '.join(options)}"
        
        # Custom validation
        validation_func = setting_def.get('validation')
        if validation_func and callable(validation_func):
            return validation_func(value)
        
        return True, ""
    
    # =========================================================================
    # Undo System Methods
    # =========================================================================
    
    def supports_undo(self) -> bool:
        """
        Check if this action supports undo functionality.
        
        Override this method in your action class and return True if your
        action implements undo. Actions that return True must also implement
        get_undo_payload() to provide the data needed for undo operations.
        
        Returns:
            bool: True if this action supports undo, False otherwise
            
        Example:
            def supports_undo(self) -> bool:
                return True  # This action can be undone
        """
        return False
    
    def get_undo_category(self) -> str:
        """
        Get the undo category for this action.
        
        Returns one of:
        - 'none': No undo needed (informational actions like "Check CRS")
        - 'trivial': Simple undo where undo is inverse of action (create -> delete)
        - 'payload': Undo requires stored backup data (delete -> restore from backup)
        - 'complex': Complex undo with external dependencies or multi-step process
        - 'informational': Display-only, logged in history but no undo capability
        
        Returns:
            str: The undo category for this action
        """
        return 'none'
    
    def get_undo_payload(self, context: dict, execute_result=None) -> dict:
        """
        Get the undo payload for this action after successful execution.
        
        This method is called by the History Manager AFTER the action has been
        successfully executed and committed. It should return a dictionary
        containing all data needed to undo the action.
        
        IMPORTANT:
        - Only called after successful commit - do not return payload before changes are committed
        - Payload must be JSON-serializable
        - Payload must be self-contained (no references to live objects)
        - For large payloads, the History Manager will externalize to files
        
        Args:
            context (dict): The original context passed to execute()
            execute_result: Optional result returned by execute() (if any)
        
        Returns:
            dict: Undo payload with the following structure:
                {
                    'undo_type': str,      # Type of undo operation (see HistoryManager constants)
                    'layers': list,         # List of layer descriptors
                    'features': list,       # List of feature backups
                    'description': str,     # Human-readable description
                    'meta': dict            # Optional additional metadata
                }
                
            Return None or empty dict to skip recording (for failed or cancelled actions)
            
        Example for create_point action:
            def get_undo_payload(self, context, execute_result=None):
                if not self._created_feature_id:
                    return None  # Action was cancelled or failed
                    
                return {
                    'undo_type': 'create_feature',
                    'layers': [self.create_layer_descriptor(self._target_layer)],
                    'features': [{'fid': self._created_feature_id}],
                    'description': f"Created point at {self._click_coords}"
                }
        """
        return {}
    
    def apply_undo(self, payload: dict) -> tuple:
        """
        Apply undo operation using the provided payload.
        
        Override this method to implement custom undo logic for your action.
        If not overridden, the History Manager will use generic undo handlers
        based on the 'undo_type' in the payload.
        
        Args:
            payload (dict): The undo payload returned by get_undo_payload()
        
        Returns:
            tuple: (success: bool, message: str)
                   success=True and message describes what was undone
                   success=False and message describes why undo failed
                   
        Example:
            def apply_undo(self, payload):
                try:
                    layer_id = payload['layers'][0]['layer_id']
                    fid = payload['features'][0]['fid']
                    
                    layer = QgsProject.instance().mapLayer(layer_id)
                    if not layer:
                        return False, "Layer no longer exists"
                    
                    layer.startEditing()
                    layer.deleteFeature(fid)
                    layer.commitChanges()
                    
                    return True, "Point deleted successfully"
                except Exception as e:
                    return False, f"Undo failed: {str(e)}"
        """
        # Default: let History Manager handle with generic undo
        return False, "Custom undo not implemented, using generic handler"
    
    def apply_redo(self, payload: dict) -> tuple:
        """
        Apply redo operation using the provided payload.
        
        Override this method to implement custom redo logic. Redo essentially
        re-applies the original action after it has been undone.
        
        Args:
            payload (dict): The undo/redo payload
        
        Returns:
            tuple: (success: bool, message: str)
        """
        # Default: let History Manager handle
        return False, "Custom redo not implemented, using generic handler"
    
    def record_to_history(
        self,
        description: str,
        undo_type: str = 'none',
        can_undo: bool = False,
        undo_payload: dict = None,
        layers: list = None,
        features: list = None,
        meta: dict = None
    ) -> str:
        """
        Record this action to the History Manager.
        
        Call this method at the end of your execute() method to record
        the action in the history. For undoable actions, provide the
        necessary undo payload.
        
        Args:
            description: Human-readable description of what was done
            undo_type: Type of undo operation (see HistoryManager constants)
            can_undo: Whether this action can be undone
            undo_payload: Data needed to undo the action
            layers: List of layer descriptors (use create_layer_descriptor())
            features: List of feature backups (use create_feature_backup())
            meta: Additional metadata
        
        Returns:
            str: The entry_id of the created history entry, or None if failed
            
        Example for informational action:
            self.record_to_history(
                description=f"Checked CRS for {layer_count} layers",
                undo_type='informational',
                can_undo=False
            )
            
        Example for undoable action:
            self.record_to_history(
                description=f"Created point at ({x}, {y})",
                undo_type='create_feature',
                can_undo=True,
                undo_payload={'created_fid': new_feature.id()},
                layers=[self.create_layer_descriptor(layer)],
                features=[{'fid': new_feature.id()}]
            )
        """
        try:
            from ..history_manager import get_history_manager
            
            history_manager = get_history_manager()
            
            return history_manager.record(
                action_id=self.action_id,
                action_name=self.name,
                description=description,
                undo_type=undo_type,
                can_undo=can_undo,
                undo_payload=undo_payload,
                layers=layers,
                features=features,
                meta=meta
            )
        except Exception as e:
            print(f"BaseAction: Failed to record to history: {e}")
            return None
    
    def record_informational(self, description: str, meta: dict = None) -> str:
        """
        Record an informational-only action to history (no undo capability).
        
        Use this for actions that only display information, change views,
        or perform read-only operations.
        
        Args:
            description: Description of what was done
            meta: Optional additional metadata
        
        Returns:
            str: The entry_id, or None if failed
            
        Example:
            self.record_informational(
                description="Displayed CRS information for 5 layers",
                meta={'layer_count': 5}
            )
        """
        return self.record_to_history(
            description=description,
            undo_type='informational',
            can_undo=False,
            meta=meta
        )
    
    @staticmethod
    def create_layer_descriptor(layer: QgsVectorLayer) -> dict:
        """
        Create a layer descriptor dictionary for history recording.
        
        Use this helper to create standardized layer descriptors for
        the undo payload.
        
        Args:
            layer: The QgsVectorLayer to describe
        
        Returns:
            dict: Layer descriptor with id, name, source, and type info
            
        Example:
            layers = [self.create_layer_descriptor(target_layer)]
        """
        from qgis.core import QgsWkbTypes
        
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
    ) -> dict:
        """
        Create a feature backup dictionary for undo operations.
        
        Use this helper to create a complete backup of a feature
        that can be used to restore it during undo.
        
        Args:
            feature: The QgsFeature to backup
            layer: The layer the feature belongs to
            include_geometry: Whether to include geometry (default True)
            include_attributes: Whether to include attributes (default True)
        
        Returns:
            dict: Feature backup with fid, geometry (WKB), and attributes
            
        Example:
            # Before deleting a feature
            backup = self.create_feature_backup(feature, layer)
            
            # In get_undo_payload()
            return {
                'undo_type': 'delete_feature',
                'features': [backup],
                ...
            }
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