"""
Calculate Point to Nearest Point Distance Action for Right-click Utilities and Shortcuts Hub

Calculates the distance from the selected point feature to the nearest point feature in the same layer.
"""

from .base_action import BaseAction
from qgis.core import QgsGeometry, QgsPointXY


class CalculatePointToNearestPointAction(BaseAction):
    """
    Action to calculate distance from selected point to nearest point in same layer.
    
    This action finds the nearest point feature in the same layer and calculates
    the distance between them, displaying the result in appropriate units.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "calculate_point_to_nearest_point"
        self.name = "Calculate Distance to Nearest Point"
        self.category = "Analysis"
        self.description = "Calculate the distance from the selected point feature to the nearest point feature in the same layer. Shows distance in appropriate units based on layer CRS."
        self.enabled = True
        
        # Action scoping configuration - works on individual features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])
        
        # Feature type support - only works with points
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            'nearest_features_count': {
                'type': 'int',
                'default': 5,
                'label': 'Number of Nearest Features',
                'description': 'Number of nearest features to find and display',
                'min': 1,
                'max': 50,
                'step': 1,
            },
            'decimal_places': {
                'type': 'int',
                'default': 2,
                'label': 'Decimal Places',
                'description': 'Number of decimal places to show in distance calculation',
                'min': 0,
                'max': 10,
                'step': 1,
            },
            'show_nearest_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature IDs',
                'description': 'Display the IDs of the nearest features in the result',
            },
            'show_crs_info': {
                'type': 'bool',
                'default': True,
                'label': 'Show CRS Information',
                'description': 'Display coordinate reference system information in the result',
            },
            'exclude_self': {
                'type': 'bool',
                'default': True,
                'label': 'Exclude Self',
                'description': 'Exclude the clicked feature from nearest feature search',
            },
        }
    
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
    
    def execute(self, context):
        """
        Execute the calculate distance to nearest point action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            nearest_features_count = int(self.get_setting('nearest_features_count', 5))
            decimal_places = int(self.get_setting('decimal_places', 2))
            show_nearest_feature_id = bool(self.get_setting('show_nearest_feature_id', True))
            show_crs_info = bool(self.get_setting('show_crs_info', True))
            exclude_self = bool(self.get_setting('exclude_self', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        detected_features = context.get('detected_features', [])
        
        if not detected_features:
            self.show_error("Error", "No features found at this location")
            return
        
        # Get the clicked feature
        detected_feature = detected_features[0]
        feature = detected_feature.feature
        layer = detected_feature.layer
        
        try:
            # Get clicked feature geometry
            clicked_geometry = feature.geometry()
            if not clicked_geometry:
                self.show_error("Error", "Clicked feature has no geometry")
                return
            
            # Get clicked feature centroid for distance calculation
            clicked_point = clicked_geometry.centroid().asPoint()
            
            # Find nearest point features in the same layer
            feature_distances = []
            
            # Iterate through all features in the layer
            for other_feature in layer.getFeatures():
                # Skip self if exclude_self is enabled
                if exclude_self and other_feature.id() == feature.id():
                    continue
                
                other_geometry = other_feature.geometry()
                if not other_geometry:
                    continue
                
                # Get other feature centroid
                other_point = other_geometry.centroid().asPoint()
                
                # Calculate distance
                distance = clicked_point.distance(other_point)
                
                # Store feature and distance
                feature_distances.append((other_feature, distance))
            
            if not feature_distances:
                self.show_warning("No Other Features", "No other point features found in this layer.")
                return
            
            # Sort by distance and take the requested number of nearest features
            feature_distances.sort(key=lambda x: x[1])
            nearest_features = feature_distances[:nearest_features_count]
            
            # Get layer CRS for units
            crs = layer.crs()
            unit_name = "units"
            if crs.isGeographic():
                unit_name = "degrees"
            elif crs.isValid() and crs.mapUnits() != 0:  # 0 = Unknown units
                unit_name = crs.mapUnits().name().lower()
            
            # Build result message
            result_parts = []
            result_parts.append(f"From Feature ID: {feature.id()}")
            result_parts.append(f"Found {len(nearest_features)} nearest point features:")
            result_parts.append("")
            
            for i, (nearest_feature, distance) in enumerate(nearest_features, 1):
                if show_nearest_feature_id:
                    result_parts.append(f"{i}. Feature ID {nearest_feature.id()}: {distance:.{decimal_places}f} {unit_name}")
                else:
                    result_parts.append(f"{i}. {distance:.{decimal_places}f} {unit_name}")
            
            if show_crs_info:
                result_parts.append("")
                result_parts.append(f"CRS: {crs.description()}")
            
            result_text = "\n".join(result_parts)
            
            # Show result
            self.show_info("Distances to Nearest Points", result_text)
            
            # Record informational history entry (JSON-serializable metadata)
            try:
                from ..history_manager import get_history_manager
                hm = get_history_manager()

                nearest_meta = []
                for nf, dist in nearest_features:
                    try:
                        nearest_meta.append({'fid': int(nf.id()), 'distance': float(dist)})
                    except Exception:
                        nearest_meta.append({'fid': getattr(nf, 'id', None), 'distance': dist})

                meta_info = {
                    'from_fid': int(feature.id()),
                    'layer': hm.create_layer_descriptor(layer),
                    'nearest': nearest_meta,
                    'parameters': {
                        'nearest_features_count': int(nearest_features_count),
                        'exclude_self': bool(exclude_self)
                    }
                }

                description = f"Calculated distances from feature {feature.id()} to {len(nearest_meta)} nearest points on layer {layer.name()}"
                hm.record_informational(self.action_id, self.name, description, meta=meta_info)
            except Exception:
                pass
            
        except Exception as e:
            self.show_error("Error", f"Failed to calculate distance: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
calculate_point_to_nearest_point_action = CalculatePointToNearestPointAction()
