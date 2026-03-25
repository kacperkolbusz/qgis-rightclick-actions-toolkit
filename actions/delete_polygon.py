"""
Delete Polygon Action for Right-click Utilities and Shortcuts Hub

Deletes the selected polygon feature after user confirmation by entering edit mode,
deleting the feature, and exiting edit mode. Works with polygon and multipolygon features.
"""

from .base_action import BaseAction


class DeletePolygonAction(BaseAction):
    """Action to delete polygon features with confirmation and edit mode handling."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "delete_polygon"
        self.name = "Delete Polygon"
        self.category = "Editing"
        self.description = "Delete the selected polygon feature after confirmation. Removes the feature from the layer permanently. Automatically handles edit mode and provides user confirmation."
        self.enabled = True
        
        # Action scoping - this works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with polygon features
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # DELETION SETTINGS - Easy to customize confirmation and behavior
            'confirm_deletion': {
                'type': 'bool',
                'default': True,
                'label': 'Confirm Before Deletion',
                'description': 'Show confirmation dialog before deleting features',
            },
            'confirmation_message_template': {
                'type': 'str',
                'default': 'Are you sure you want to delete polygon feature ID {feature_id} from layer \'{layer_name}\'?',
                'label': 'Confirmation Message Template',
                'description': 'Template for confirmation message. Available variables: {feature_id}, {layer_name}, {geometry_type}',
            },
            'auto_commit_changes': {
                'type': 'bool',
                'default': True,
                'label': 'Auto-commit Changes',
                'description': 'Automatically commit changes after deletion (recommended)',
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_success_message': {
                'type': 'bool',
                'default': True,
                'label': 'Show Success Message',
                'description': 'Display a message when feature is deleted successfully',
            },
            'success_message_template': {
                'type': 'str',
                'default': 'Polygon feature ID {feature_id} deleted successfully from layer \'{layer_name}\'',
                'label': 'Success Message Template',
                'description': 'Template for success message. Available variables: {feature_id}, {layer_name}',
            },
            'handle_edit_mode_automatically': {
                'type': 'bool',
                'default': True,
                'label': 'Handle Edit Mode Automatically',
                'description': 'Automatically enter/exit edit mode as needed',
            },
            'rollback_on_error': {
                'type': 'bool',
                'default': True,
                'label': 'Rollback on Error',
                'description': 'Rollback changes if deletion fails',
            },
            'show_polygon_area_info': {
                'type': 'bool',
                'default': False,
                'label': 'Show Polygon Area Info',
                'description': 'Display polygon area information in confirmation and success messages',
            },
        }

    # Undo support: deleting features must create backups for undo
    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'payload'
    
    def execute(self, context):
        """
        Execute the delete polygon action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings (with proper type conversion)
        try:
            confirm_deletion = bool(self.get_setting('confirm_deletion', True))
            confirmation_template = str(self.get_setting('confirmation_message_template', 'Are you sure you want to delete polygon feature ID {feature_id} from layer \'{layer_name}\'?'))
            auto_commit = bool(self.get_setting('auto_commit_changes', True))
            show_success = bool(self.get_setting('show_success_message', True))
            success_template = str(self.get_setting('success_message_template', 'Polygon feature ID {feature_id} deleted successfully from layer \'{layer_name}\''))
            handle_edit_mode = bool(self.get_setting('handle_edit_mode_automatically', True))
            rollback_on_error = bool(self.get_setting('rollback_on_error', True))
            show_polygon_area = bool(self.get_setting('show_polygon_area_info', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location")
            return
        
        # Get the first (closest) detected feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        # Calculate polygon area if requested
        polygon_area = None
        if show_polygon_area:
            try:
                geometry = feature.geometry()
                if geometry:
                    polygon_area = geometry.area()
            except Exception:
                pass
        
        # Ask for user confirmation before deletion if enabled
        if confirm_deletion:
            # Prepare confirmation message
            confirmation_message = self.format_message_template(
                confirmation_template,
                feature_id=feature.id(),
                layer_name=layer.name(),
                geometry_type=detected_feature.geometry_type
            )
            
            # Add polygon area info if requested
            if show_polygon_area and polygon_area is not None:
                confirmation_message += f"\n\nPolygon area: {polygon_area:.2f} square map units"
            
            if not self.confirm_action("Delete Polygon", confirmation_message):
                return
        
        # Handle edit mode if enabled
        edit_result = None
        was_in_edit_mode = False
        edit_mode_entered = False
        
        if handle_edit_mode:
            edit_result = self.handle_edit_mode(layer, "polygon deletion")
            if edit_result[0] is None:  # Error occurred
                return
            was_in_edit_mode, edit_mode_entered = edit_result
        
        # Backup feature before deletion for undo/redo
        feature_backup = None
        try:
            feature_backup = self.create_feature_backup(feature, layer)
        except Exception:
            feature_backup = None

        try:
            # Delete the feature (use integer fid)
            fid = int(feature.id())
            if not layer.deleteFeature(fid):
                self.show_error("Error", "Failed to delete polygon feature")
                if rollback_on_error and handle_edit_mode:
                    self.rollback_changes(layer)
                return

            # Commit changes if enabled
            if auto_commit and handle_edit_mode:
                if not self.commit_changes(layer, "polygon deletion"):
                    # Do not record history if commit failed
                    return

            # Record delete to history so undo can restore the feature
            try:
                if feature_backup is not None:
                    layers = [self.create_layer_descriptor(layer)]
                    self.record_to_history(
                        description=f"Deleted polygon feature {fid} from layer '{layer.name()}'",
                        undo_type='delete_feature',
                        can_undo=True,
                        undo_payload=None,
                        layers=layers,
                        features=[feature_backup],
                        meta={'feature_id': fid}
                    )
            except Exception:
                # History recording should not prevent successful deletion
                pass

            # Show success message if enabled
            if show_success:
                success_message = self.format_message_template(
                    success_template,
                    feature_id=fid,
                    layer_name=layer.name()
                )
                
                # Add polygon area info if requested
                if show_polygon_area and polygon_area is not None:
                    success_message += f"\n\nPolygon area was: {polygon_area:.2f} square map units"
                
                self.show_info("Success", success_message)

        except Exception as e:
            self.show_error("Error", f"Failed to delete polygon feature: {str(e)}")
            if rollback_on_error and handle_edit_mode:
                self.rollback_changes(layer)
            
        finally:
            # Exit edit mode if we entered it
            if handle_edit_mode:
                self.exit_edit_mode(layer, edit_mode_entered)
    
    def format_message_template(self, template, **kwargs):
        """
        Format a message template with provided variables.
        
        Args:
            template (str): Message template with {variable} placeholders
            **kwargs: Variables to substitute in the template
            
        Returns:
            str: Formatted message
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            # If a variable is missing, return the template as-is
            return template


# REQUIRED: Create global instance for automatic discovery
delete_polygon_action = DeletePolygonAction()