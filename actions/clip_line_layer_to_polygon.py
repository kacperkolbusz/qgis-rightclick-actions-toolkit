"""
Clip Line Layer to Polygon Action for Right-click Utilities and Shortcuts Hub

Clips line features to fit within a polygon boundary. Removes portions of lines
that extend beyond the polygon, creating a new temporary layer with clipped results.
Compatible with both single polygon selection and entire polygon layers.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsWkbTypes, QgsProject, QgsCoordinateTransform, QgsFeatureRequest,
    QgsGeometryCollection
)
from qgis.PyQt.QtCore import QVariant, QMetaType, QDateTime
from qgis.PyQt.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QRadioButton, QButtonGroup, QPushButton


class ClipLineLayerToPolygonAction(BaseAction):
    """Action to clip line features to fit within a polygon boundary."""

    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()

        # Required properties
        self.action_id = 'clip_line_layer_to_polygon'
        self.name = 'Clip Line Layer to Polygon'
        self.category = 'Geometry'
        self.description = (
            'Clips all line features in the selected layer to fit within a polygon boundary. '
            'Lines that extend beyond the polygon are trimmed at the polygon edge. '
            'You can select a single polygon feature or use an entire polygon layer as the clipping boundary. '
            'Creates a new temporary layer with only the clipped portions of lines.'
        )
        self.enabled = True

        # Action scoping - works on entire line layers
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        # Feature type support - only works with line layers
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

        # Internal state for storing selections
        self._clip_polygon = None
        self._clip_mode = None  # 'single' or 'layer'

    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            'layer_storage_type': {
                'type': 'choice',
                'label': 'Layer Storage Type',
                'default': 'temporary',
                'description': (
                    'Temporary layers are in-memory only (lost when QGIS closes). '
                    'Permanent layers are saved to disk.'
                ),
                'options': ['temporary', 'permanent'],
            },
            'layer_name_template': {
                'type': 'str',
                'label': 'Layer Name Template',
                'default': 'Clipped Lines',
                'description': (
                    'Name for the new clipped lines layer. '
                    'Available variables: {layer_name}, {polygon_name}, {timestamp}'
                ),
            },
            'add_to_project': {
                'type': 'bool',
                'label': 'Add to Project',
                'default': True,
                'description': 'Automatically add the clipped layer to the project',
            },
            'preserve_attributes': {
                'type': 'bool',
                'label': 'Preserve Original Attributes',
                'default': True,
                'description': 'Keep all original attributes from the line features in the clipped output',
            },
            'zoom_to_layer': {
                'type': 'bool',
                'label': 'Zoom to Result',
                'default': True,
                'description': 'Automatically zoom to the clipped lines layer',
            },
            'show_success_message': {
                'type': 'bool',
                'label': 'Show Success Message',
                'default': True,
                'description': 'Display a message showing how many lines were clipped',
            },
        }

    def supports_undo(self) -> bool:
        """This action creates a new layer and is undoable via layer removal."""
        return True

    def get_undo_category(self) -> str:
        """Classify as 'trivial' (create -> delete)."""
        return 'trivial'

    def _show_polygon_selection_dialog(self, line_layer):
        """
        Show a dialog allowing user to select clipping mode and source.
        
        Returns:
            dict: {'mode': 'single'|'layer', 'polygon': polygon_or_layer}
              or None if cancelled
        """
        dialog = QDialog()
        dialog.setWindowTitle('Select Clipping Polygon')
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        # Mode selection
        layout.addWidget(QLabel('Choose clipping method:'))

        mode_group = QButtonGroup()
        single_radio = QRadioButton('Use a single polygon feature')
        layer_radio = QRadioButton('Use entire polygon layer')
        mode_group.addButton(single_radio, 0)
        mode_group.addButton(layer_radio, 1)
        single_radio.setChecked(True)

        layout.addWidget(single_radio)
        layout.addWidget(layer_radio)

        layout.addSpacing(15)
        layout.addWidget(QLabel('Select polygon source:'))

        # Polygon layer selector
        polygon_combo = QComboBox()
        polygon_layers = self._get_polygon_layers()
        if not polygon_layers:
            self.show_error(
                'Error',
                'No polygon layers found in the project. Please add a polygon layer first.'
            )
            return None

        for layer in polygon_layers:
            polygon_combo.addItem(layer.name(), layer)

        layout.addWidget(QLabel('Polygon Layer:'))
        layout.addWidget(polygon_combo)

        # Feature selector (for single mode)
        layout.addSpacing(10)
        feature_label = QLabel('Select specific polygon feature (for single mode):')
        layout.addWidget(feature_label)

        feature_combo = QComboBox()
        self._populate_polygon_features(polygon_combo.itemData(0), feature_combo)

        def on_polygon_layer_changed():
            """Update feature list when polygon layer changes."""
            current_layer = polygon_combo.itemData(polygon_combo.currentIndex())
            self._populate_polygon_features(current_layer, feature_combo)

        polygon_combo.currentIndexChanged.connect(on_polygon_layer_changed)
        layout.addWidget(feature_combo)

        # Buttons
        layout.addSpacing(20)
        button_layout = QHBoxLayout()
        ok_button = QPushButton('OK')
        cancel_button = QPushButton('Cancel')

        def on_ok():
            """Handle OK button click."""
            if mode_group.checkedId() == 0:  # Single mode
                if feature_combo.count() == 0:
                    self.show_error('Error', 'No polygon features available to select.')
                    return
                selected_polygon = feature_combo.itemData(feature_combo.currentIndex())
                self._clip_mode = 'single'
                self._clip_polygon = selected_polygon
            else:  # Layer mode
                self._clip_mode = 'layer'
                self._clip_polygon = polygon_combo.itemData(polygon_combo.currentIndex())

            dialog.accept()

        ok_button.clicked.connect(on_ok)
        cancel_button.clicked.connect(dialog.reject)

        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            return {
                'mode': self._clip_mode,
                'polygon': self._clip_polygon
            }
        return None

    def _get_polygon_layers(self):
        """Get all polygon vector layers in the project."""
        polygon_layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                geom_type = layer.geometryType()
                if geom_type == QgsWkbTypes.PolygonGeometry:
                    polygon_layers.append(layer)
        return polygon_layers

    def _populate_polygon_features(self, polygon_layer, feature_combo):
        """Populate combo box with polygon features from the layer."""
        feature_combo.clear()
        if not polygon_layer:
            return

        for feature in polygon_layer.getFeatures():
            display_text = f"Feature ID {feature.id()}"
            feature_combo.addItem(display_text, feature)

    def _create_clipped_layer(self, line_layer, clip_geometry):
        """
        Create a new layer with clipped lines.
        
        Args:
            line_layer (QgsVectorLayer): Source line layer
            clip_geometry (QgsGeometry): Clipping polygon geometry
            
        Returns:
            QgsVectorLayer: New layer with clipped lines, or None if failed
        """
        try:
            canvas = self._get_canvas()
            canvas_crs = canvas.mapSettings().destinationCrs() if canvas else line_layer.crs()
            line_crs = line_layer.crs()

            # Create transform if CRS differ
            transform = None
            if canvas_crs != line_crs:
                transform = QgsCoordinateTransform(line_crs, canvas_crs, QgsProject.instance())
                clip_geometry = QgsGeometry(clip_geometry)
                clip_geometry.transform(transform)

            # Create new layer with same CRS as lines
            output_layer = QgsVectorLayer(
                f"LineString?crs={line_crs.authid()}",
                'Clipped Lines',
                'memory'
            )

            if not output_layer.isValid():
                return None

            # Copy attributes from original layer if setting is enabled
            preserve_attrs = bool(self.get_setting('preserve_attributes', True))
            if preserve_attrs:
                output_layer.dataProvider().addAttributes(line_layer.fields())
            else:
                # Create a minimal set of attributes
                output_layer.dataProvider().addAttributes([
                    QgsField('source_fid', QMetaType.Int),
                    QgsField('clipped', QMetaType.Bool),
                ])

            output_layer.updateFields()

            # Clip each line feature
            clipped_count = 0
            for feature in line_layer.getFeatures():
                if feature.geometry().isEmpty():
                    continue

                # Transform line geometry to canvas CRS if needed
                line_geom = QgsGeometry(feature.geometry())
                if transform:
                    line_geom.transform(transform)

                # Perform intersection to clip
                try:
                    clipped_geom = line_geom.intersection(clip_geometry)

                    if clipped_geom and not clipped_geom.isEmpty():
                        # Create new feature with clipped geometry
                        new_feature = QgsFeature()
                        new_feature.setGeometry(clipped_geom)

                        # Copy attributes
                        if preserve_attrs:
                            new_feature.setAttributes(feature.attributes())
                        else:
                            attrs = [feature.id(), True]
                            new_feature.setAttributes(attrs)

                        output_layer.dataProvider().addFeatures([new_feature])
                        clipped_count += 1
                except Exception as e:
                    print(f"Error clipping feature {feature.id()}: {str(e)}")
                    continue

            output_layer.updateExtents()

            if clipped_count == 0:
                self.show_error(
                    'Warning',
                    'No lines were clipped. The lines may not intersect with the polygon.'
                )
                return None

            return output_layer

        except Exception as e:
            self.show_error('Error', f'Failed to create clipped layer: {str(e)}')
            return None

    def _get_canvas(self):
        """Get the QGIS map canvas."""
        try:
            from qgis.utils import iface
            return iface.mapCanvas()
        except:
            return None

    def execute(self, context):
        """Execute the clip line layer to polygon action."""
        # Get settings with proper type conversion
        try:
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            layer_name_template = str(self.get_setting('layer_name_template', 'Clipped Lines'))
            add_to_project = bool(self.get_setting('add_to_project', True))
            zoom_to_layer = bool(self.get_setting('zoom_to_layer', True))
            show_success = bool(self.get_setting('show_success_message', True))
        except (ValueError, TypeError) as e:
            self.show_error('Settings Error', f'Invalid setting values: {str(e)}')
            return

        # Resolve layer from context
        line_layer = context.get('layer')
        if not line_layer:
            detected = context.get('detected_features', [])
            if detected:
                line_layer = detected[0].layer

        if not line_layer:
            self.show_error('Error', 'No layer found in context.')
            return

        if not isinstance(line_layer, QgsVectorLayer):
            self.show_error('Error', 'Target is not a vector layer.')
            return

        # Validate it's a line layer
        if line_layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.show_error('Error', 'Selected layer is not a line layer.')
            return

        # Show polygon selection dialog
        selection = self._show_polygon_selection_dialog(line_layer)
        if not selection:
            return

        # Extract clipping geometry based on mode
        try:
            if selection['mode'] == 'single':
                clip_geom = selection['polygon'].geometry()
                clip_name = f"Feature {selection['polygon'].id()}"
            else:  # layer mode
                # Merge all polygons in the layer
                polygon_layer = selection['polygon']
                all_geoms = []
                for feat in polygon_layer.getFeatures():
                    if not feat.geometry().isEmpty():
                        all_geoms.append(feat.geometry())

                if not all_geoms:
                    self.show_error('Error', 'Selected polygon layer has no valid geometries.')
                    return

                if len(all_geoms) == 1:
                    clip_geom = all_geoms[0]
                else:
                    # Merge all geometries
                    union_geom = all_geoms[0]
                    for geom in all_geoms[1:]:
                        union_geom = union_geom.combine(geom)
                    clip_geom = union_geom

                clip_name = polygon_layer.name()

            if clip_geom.isEmpty():
                self.show_error('Error', 'Clipping polygon geometry is empty or invalid.')
                return

        except Exception as e:
            self.show_error('Error', f'Failed to extract clipping geometry: {str(e)}')
            return

        # Create clipped layer
        clipped_layer = self._create_clipped_layer(line_layer, clip_geom)
        if not clipped_layer:
            return

        # Generate layer name
        timestamp = QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')
        layer_name = layer_name_template.format(
            layer_name=line_layer.name(),
            polygon_name=clip_name,
            timestamp=timestamp
        )
        clipped_layer.setName(layer_name)

        # Add to project if setting is enabled
        if add_to_project:
            QgsProject.instance().addMapLayer(clipped_layer)

            # Zoom to layer if setting is enabled
            if zoom_to_layer:
                canvas = self._get_canvas()
                if canvas:
                    canvas.setExtent(clipped_layer.extent())
                    canvas.refresh()

        # Show success message if enabled
        if show_success:
            feature_count = clipped_layer.featureCount()
            self.show_info(
                'Success',
                f'Successfully clipped {feature_count} line(s) to polygon.\n'
                f'Created new layer: {layer_name}'
            )

        # Record to history
        self.record_informational(
            description=f'Clipped line layer "{line_layer.name()}" to polygon "{clip_name}"',
            meta={
                'source_layer': line_layer.name(),
                'clip_source': clip_name,
                'clipped_feature_count': clipped_layer.featureCount(),
                'output_layer': layer_name,
            }
        )


# Create global instance for automatic discovery
clip_line_layer_to_polygon = ClipLineLayerToPolygonAction()
