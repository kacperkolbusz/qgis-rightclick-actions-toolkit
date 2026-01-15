"""
Toggle Point Layer Labels Action for Right-click Utilities and Shortcuts Hub

Toggles label visibility for point layers when a point feature is clicked.
Ensures labels can be configured even for new layers.
"""

from .base_action import BaseAction
from qgis.core import QgsVectorLayer, QgsLayerTreeLayer, QgsPalLayerSettings, QgsTextFormat


class TogglePointLabelsAction(BaseAction):
    """Action to toggle label visibility for point layers."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "toggle_point_labels"
        self.name = "Toggle Point Layer Labels"
        self.category = "Editing"
        self.description = "Toggle label visibility for the point layer of the selected point feature. Configures labels if not previously set up."
        self.enabled = True
        
        # Action scoping configuration
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])
        
        # Feature type support
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'label_field': {
                'type': 'str',
                'default': '',
                'label': 'Label Field',
                'description': 'Field to use for labeling. If empty, first text/string field will be used.',
            },
            'label_placement': {
                'type': 'choice',
                'default': 'around',
                'label': 'Label Placement',
                'description': 'Default label placement when toggling labels on',
                'options': ['around', 'over', 'buffer', 'offset'],
            },
            'label_size': {
                'type': 'float',
                'default': 10.0,
                'label': 'Label Size',
                'description': 'Default label text size when toggling labels on',
                'min': 1.0,
                'max': 50.0,
                'step': 0.5,
            },
        }
    
    def _get_label_field(self, layer):
        """
        Determine the best field to use for labeling.
        
        Args:
            layer (QgsVectorLayer): The layer to find a label field for
        
        Returns:
            str: Name of the field to use for labeling, or empty string
        """
        # First, check if a specific label field is set in settings
        label_field = str(self.get_setting('label_field', '')).strip()
        if label_field and label_field in [field.name() for field in layer.fields()]:
            return label_field
        
        # Check for "id" field first (case-insensitive)
        for field in layer.fields():
            if field.name().lower() == 'id':
                return field.name()
        
        # If no "id" field, find the first text/string field
        for field in layer.fields():
            if field.type() in [2, 10]:  # QVariant::String types
                return field.name()
        
        return ''
    
    def execute(self, context):
        """
        Execute the toggle point labels action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        # Get the layer of the first detected feature
        layer = detected_features[0].layer
        
        # Verify it's a point layer
        if not isinstance(layer, QgsVectorLayer) or layer.geometryType() != 0:  # 0 is point geometry type
            self.show_error("Error", "This action works only with point layers")
            return
        
        try:
            # Determine current label state
            labeling_manager = layer.labeling()
            is_labels_enabled = labeling_manager is not None and layer.labelsEnabled()
            
            # Toggle label visibility
            layer.setLabelsEnabled(not is_labels_enabled)
            
            # If enabling labels and no labeling is set up
            if not is_labels_enabled:
                # Get settings with type conversion
                label_placement = str(self.get_setting('label_placement', 'around'))
                label_size = float(self.get_setting('label_size', 10.0))
                
                # Find a suitable label field
                label_field = self._get_label_field(layer)
                
                if label_field:
                    # Create new labeling settings
                    pal_layer_settings = QgsPalLayerSettings()
                    pal_layer_settings.enabled = True
                    pal_layer_settings.fieldName = label_field
                    
                    # Configure text format
                    text_format = QgsTextFormat()
                    text_format.setSize(label_size)
                    pal_layer_settings.setFormat(text_format)
                    
                    # Set placement
                    placement_map = {
                        'around': QgsPalLayerSettings.AroundPoint,
                        'over': QgsPalLayerSettings.OverPoint,
                        'buffer': QgsPalLayerSettings.OverPoint,  # Changed from non-existent PointQuadOffset
                        'offset': QgsPalLayerSettings.OverPoint   # Changed from non-existent OffsetQuadrant
                    }
                    pal_layer_settings.placement = placement_map.get(label_placement, QgsPalLayerSettings.AroundPoint)
                    
                    # Apply labeling settings
                    from qgis.core import QgsVectorLayerSimpleLabeling
                    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal_layer_settings))
                    layer.setLabelsEnabled(True)
                else:
                    # No suitable label field found
                    self.show_warning("No Label Field", 
                        "Could not find a suitable field for labeling. "
                        "Please set a label field in the action settings or add a text field to the layer."
                    )
            
            # Refresh the layer to show changes
            layer.triggerRepaint()
            
            # Show feedback
            status = "enabled" if not is_labels_enabled else "disabled"
            self.show_info("Label Visibility", f"Labels for layer '{layer.name()}' have been {status}.")
        
        except Exception as e:
            self.show_error("Error", f"Failed to toggle labels: {str(e)}")


# Create global instance for automatic discovery
toggle_point_labels_action = TogglePointLabelsAction()
