"""
Count Lines in Polygon Action for Right-click Utilities and Shortcuts Hub

Counts how many line features intersect with the selected polygon feature.
Distinguishes between lines fully contained inside the polygon and lines that
only partially overlap (cross the polygon boundary). Shows results per layer.
"""

from .base_action import BaseAction
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes, QgsCoordinateTransform
from ..history_manager import get_history_manager


class CountLinesInPolygonAction(BaseAction):
    """Action to count line features within or intersecting a polygon feature."""

    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()

        # Required properties
        self.action_id = "count_lines_in_polygon"
        self.name = "Count Lines in Polygon"
        self.category = "Analysis"
        self.description = (
            "Count how many line features are inside or intersect the selected polygon feature. "
            "Distinguishes between lines fully contained within the polygon and lines that only "
            "partially overlap. Shows results per layer with CRS transformation handled automatically."
        )
        self.enabled = True

        # Action scoping - works on individual polygon features
        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Feature type support - only works with polygons
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # DISPLAY SETTINGS
            'show_feature_id': {
                'type': 'bool',
                'default': True,
                'label': 'Show Feature ID',
                'description': 'Display the polygon feature ID in the result dialog',
            },
            'show_layer_name': {
                'type': 'bool',
                'default': True,
                'label': 'Show Layer Name',
                'description': 'Display the polygon layer name in the result dialog',
            },
            'show_empty_layers': {
                'type': 'bool',
                'default': False,
                'label': 'Show Empty Layers',
                'description': 'Display line layers that have no lines within or intersecting the polygon',
            },
            'sort_by_count': {
                'type': 'bool',
                'default': True,
                'label': 'Sort by Count',
                'description': 'Sort line layers by total count (highest first) in the result',
            },
            'show_total_count': {
                'type': 'bool',
                'default': True,
                'label': 'Show Total Count',
                'description': 'Display the total number of lines across all layers',
            },
            'show_partial_detail': {
                'type': 'bool',
                'default': True,
                'label': 'Show Fully/Partially Split',
                'description': 'Show how many lines are fully inside vs. partially intersecting the polygon',
            },

            # BEHAVIOR SETTINGS
            'include_visible_only': {
                'type': 'bool',
                'default': False,
                'label': 'Visible Layers Only',
                'description': 'Only count lines from visible line layers',
            },
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a brief success message after counting',
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

    def _get_line_layers(self, include_visible_only=False):
        """
        Get all line layers from the project.

        Args:
            include_visible_only (bool): If True, only return visible layers

        Returns:
            list: List of QgsVectorLayer objects that are line layers
        """
        project = QgsProject.instance()
        line_layers = []

        for layer_id, layer in project.mapLayers().items():
            if not isinstance(layer, QgsVectorLayer):
                continue

            if layer.geometryType() != QgsWkbTypes.LineGeometry:
                continue

            if not layer.isValid():
                continue

            if include_visible_only:
                root = project.layerTreeRoot()
                layer_tree_layer = root.findLayer(layer_id)
                if not layer_tree_layer or not layer_tree_layer.isVisible():
                    continue

            line_layers.append(layer)

        return line_layers

    def execute(self, context):
        """Execute the count lines in polygon action."""
        # Get settings with proper type conversion
        try:
            schema = self.get_settings_schema()
            show_feature_id = bool(self.get_setting('show_feature_id', schema['show_feature_id']['default']))
            show_layer_name = bool(self.get_setting('show_layer_name', schema['show_layer_name']['default']))
            show_empty_layers = bool(self.get_setting('show_empty_layers', schema['show_empty_layers']['default']))
            sort_by_count = bool(self.get_setting('sort_by_count', schema['sort_by_count']['default']))
            show_total_count = bool(self.get_setting('show_total_count', schema['show_total_count']['default']))
            show_partial_detail = bool(self.get_setting('show_partial_detail', schema['show_partial_detail']['default']))
            include_visible_only = bool(self.get_setting('include_visible_only', schema['include_visible_only']['default']))
            show_success_message = bool(self.get_setting('show_success_message', schema['show_success_message']['default']))
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

        try:
            # Get feature geometry
            polygon_geometry = feature.geometry()
            if not polygon_geometry:
                self.show_error("Error", "Feature has no geometry")
                return

            if polygon_geometry.isEmpty():
                self.show_error("Error", "Feature has empty geometry")
                return

            polygon_crs = layer.crs()

            # Get all line layers
            line_layers = self._get_line_layers(include_visible_only)

            if not line_layers:
                self.show_warning("No Line Layers", "No line layers found in the project.")
                return

            # Structure: {layer_name: {'fully': int, 'partially': int}}
            layer_results = {}
            total_fully = 0
            total_partially = 0

            for line_layer in line_layers:
                layer_name = line_layer.name()
                line_crs = line_layer.crs()
                needs_transformation = polygon_crs != line_crs

                if needs_transformation:
                    try:
                        transform = QgsCoordinateTransform(line_crs, polygon_crs, QgsProject.instance())
                    except Exception as e:
                        self.show_warning(
                            "CRS Warning",
                            f"Could not create CRS transformation for layer '{layer_name}': {str(e)}. Skipping this layer."
                        )
                        continue

                fully_inside = 0
                partially_inside = 0

                for line_feature in line_layer.getFeatures():
                    line_geometry = line_feature.geometry()
                    if not line_geometry or line_geometry.isEmpty():
                        continue

                    # Work on a copy so we don't mutate the original
                    geom = line_geometry.__class__(line_geometry)

                    if needs_transformation:
                        try:
                            geom.transform(transform)
                        except Exception:
                            continue

                    if polygon_geometry.contains(geom):
                        fully_inside += 1
                    elif polygon_geometry.intersects(geom):
                        partially_inside += 1

                total_in_layer = fully_inside + partially_inside

                if total_in_layer > 0 or show_empty_layers:
                    layer_results[layer_name] = {
                        'fully': fully_inside,
                        'partially': partially_inside,
                        'total': total_in_layer,
                    }

                total_fully += fully_inside
                total_partially += partially_inside

            total_count = total_fully + total_partially

            # Build result message
            result_lines = []

            if show_feature_id:
                result_lines.append(f"Polygon Feature ID: {feature.id()}")

            if show_layer_name:
                result_lines.append(f"Polygon Layer: {layer.name()}")

            result_lines.append("")

            if show_total_count:
                result_lines.append(f"Total Lines: {total_count}")
                if show_partial_detail and total_count > 0:
                    result_lines.append(f"  Fully inside:    {total_fully}")
                    result_lines.append(f"  Partially inside: {total_partially}")
                result_lines.append("")

            if not layer_results:
                result_lines.append("No lines found within or intersecting this polygon.")
            else:
                result_lines.append("Lines by Layer:")
                result_lines.append("")

                if sort_by_count:
                    sorted_layers = sorted(layer_results.items(), key=lambda x: x[1]['total'], reverse=True)
                else:
                    sorted_layers = sorted(layer_results.items(), key=lambda x: x[0])

                for lname, counts in sorted_layers:
                    total_lyr = counts['total']
                    line_word = 'line' if total_lyr == 1 else 'lines'
                    result_lines.append(f"  • {lname}: {total_lyr} {line_word}")
                    if show_partial_detail:
                        result_lines.append(f"      Fully inside:    {counts['fully']}")
                        result_lines.append(f"      Partially inside: {counts['partially']}")

            result_text = "\n".join(result_lines)

            self.show_info("Lines in Polygon", result_text)

            if show_success_message and total_count > 0:
                line_word = 'line' if total_count == 1 else 'lines'
                self.show_info("Success", f"Found {total_count} {line_word} within or intersecting the polygon.")

            # Record informational history entry (read-only operation)
            try:
                hm = get_history_manager()
                try:
                    layer_desc = hm.create_layer_descriptor(layer)
                except Exception:
                    layer_desc = {
                        'layer_id': getattr(layer, 'id', lambda: None)(),
                        'layer_name': getattr(layer, 'name', lambda: '')(),
                    }

                meta = {
                    'feature_id': feature.id(),
                    'polygon_layer': layer_desc,
                    'total_count': int(total_count),
                    'fully_inside': int(total_fully),
                    'partially_inside': int(total_partially),
                    'counts_by_layer': {
                        name: {'fully': v['fully'], 'partially': v['partially'], 'total': v['total']}
                        for name, v in layer_results.items()
                    },
                    'settings': {
                        'show_empty_layers': bool(show_empty_layers),
                        'sort_by_count': bool(sort_by_count),
                        'include_visible_only': bool(include_visible_only),
                    },
                }

                hm.record_informational(
                    action_id=self.action_id,
                    action_name=self.name,
                    description=(
                        f"Counted lines within polygon feature {feature.id()} on layer {layer.name()} "
                        f"({total_fully} fully inside, {total_partially} partially inside)"
                    ),
                    meta=meta
                )
            except Exception:
                # History recording must not break the main action
                pass

        except Exception as e:
            self.show_error("Error", f"Failed to count lines: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
count_lines_in_polygon_action = CountLinesInPolygonAction()
