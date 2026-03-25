"""
Create Line at Location Action for Right-click Utilities and Shortcuts Hub

Creates a line feature by clicking points on the canvas in a temporary layer.
Right-click to start, click to add vertices, right-click again to finish.
Works universally on any canvas location with proper CRS handling.

Undo Category: Trivial / Simple
    - Creates new feature(s) in existing layer or new layer
    - Undo = delete created feature (and optionally remove created layer)
"""

from .base_action import BaseAction
from ..history_manager import get_history_manager, HistoryManager
from qgis.core import QgsWkbTypes


class CreateLineAtLocationAction(BaseAction):
    """Action to create a line by clicking points on the canvas in a temporary layer."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "create_line_at_location"
        self.name = "Create Line at Location"
        self.category = "Editing"
        self.description = "Create a line feature by clicking points on the canvas. Right-click to start, click to add vertices, right-click again to finish. The line is added to a temporary layer that persists until QGIS is closed. Automatically handles CRS and adds the layer to the project."
        self.enabled = True
        
        # Action scoping - this works universally
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - works everywhere
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['universal'])
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # LAYER SETTINGS
            'layer_name': {
                'type': 'str',
                'default': 'Lines',
                'label': 'Layer Name',
                'description': 'Name for the temporary line layer. If layer already exists, lines will be added to it.',
            },
            'add_to_existing_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Existing Layer',
                'description': 'If a layer with the same name exists, add lines to it instead of creating a new layer',
            },
            
            # LINE SETTINGS
            'min_vertices': {
                'type': 'int',
                'default': 2,
                'label': 'Minimum Vertices',
                'description': 'Minimum number of vertices required to create a line',
                'min': 2,
                'max': 100,
                'step': 1,
            },
            'add_timestamp': {
                'type': 'bool',
                'default': False,
                'label': 'Add Timestamp',
                'description': 'Add timestamp field with creation date and time',
            },
            'add_length': {
                'type': 'bool',
                'default': False,
                'label': 'Add Length',
                'description': 'Add length field calculated from line geometry',
            },
            'add_vertex_count': {
                'type': 'bool',
                'default': False,
                'label': 'Add Vertex Count',
                'description': 'Add field with number of vertices in the line',
            },
            'add_id': {
                'type': 'bool',
                'default': True,
                'label': 'Add ID Field',
                'description': 'Add sequential ID field to each line',
            },
            
            # BEHAVIOR SETTINGS
            'auto_zoom': {
                'type': 'bool',
                'default': False,
                'label': 'Auto Zoom to Line',
                'description': 'Automatically zoom to the created line',
            },
            'show_confirmation': {
                'type': 'bool',
                'default': False,
                'label': 'Show Confirmation',
                'description': 'Show confirmation message when line is created',
            },
            'show_instruction_popup': {
                'type': 'bool',
                'default': False,
                'label': 'Show Instruction Popup',
                'description': 'Display initial popup with instructions when starting line creation',
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
        Execute the create line at location action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_name = str(self.get_setting('layer_name', 'Lines'))
            add_to_existing_layer = bool(self.get_setting('add_to_existing_layer', True))
            min_vertices = int(self.get_setting('min_vertices', 2))
            add_timestamp = bool(self.get_setting('add_timestamp', False))
            add_length = bool(self.get_setting('add_length', False))
            add_vertex_count = bool(self.get_setting('add_vertex_count', False))
            add_id = bool(self.get_setting('add_id', True))
            auto_zoom = bool(self.get_setting('auto_zoom', False))
            show_confirmation = bool(self.get_setting('show_confirmation', False))
            show_instruction_popup = bool(self.get_setting('show_instruction_popup', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        click_point = context.get('click_point')
        canvas = context.get('canvas')
        
        if not click_point:
            self.show_error("Error", "No click point available")
            return
        
        if not canvas:
            self.show_error("Error", "Map canvas not available")
            return
        
        try:
            # Get canvas CRS for proper coordinate handling
            canvas_crs = canvas.mapSettings().destinationCrs()
            
            # Show instruction popup if enabled
            if show_instruction_popup:
                self.show_info("Create Line", 
                    f"Right-click to start creating a line.\n"
                    f"Click to add vertices.\n"
                    f"Right-click again to finish (minimum {min_vertices} vertices required).\n"
                    f"Press Escape to cancel.")
            
            # Set up interactive line drawing
            self._setup_line_drawing_mode(canvas, click_point, canvas_crs, {
                'layer_name': layer_name,
                'add_to_existing_layer': add_to_existing_layer,
                'min_vertices': min_vertices,
                'add_timestamp': add_timestamp,
                'add_length': add_length,
                'add_vertex_count': add_vertex_count,
                'add_id': add_id,
                'auto_zoom': auto_zoom,
                'show_confirmation': show_confirmation,
            })
            
        except Exception as e:
            self.show_error("Error", f"Failed to start line creation: {str(e)}")
    
    def _setup_line_drawing_mode(self, canvas, first_point, canvas_crs, settings):
        """Set up the canvas for interactive line drawing."""
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtGui import QPen, QColor, QPainter
        from qgis.gui import QgsMapTool, QgsMapCanvasItem
        from qgis.core import QgsPointXY, QgsGeometry
        
        # Store the current map tool to restore it later
        original_tool = canvas.mapTool()
        
        class LineDrawingTool(QgsMapTool):
            """Interactive tool for drawing lines."""
            
            def __init__(self, canvas, first_point, canvas_crs, settings, parent_action, original_tool):
                super().__init__(canvas)
                self.canvas = canvas
                self.canvas_crs = canvas_crs
                self.settings = settings
                self.parent_action = parent_action
                self.original_tool = original_tool
                self.setCursor(self.parent_action._get_draw_cursor())
                
                # Store vertices
                self.vertices = [first_point]
                self.current_point = None
                
                # Create preview item
                self.preview_item = LinePreviewItem(canvas, self.vertices)
                self.preview_item.show()
            
            def canvasMoveEvent(self, event):
                """Update preview as mouse moves."""
                self.current_point = self.toMapCoordinates(event.pos())
                self.preview_item.update_vertices(self.vertices, self.current_point)
                self.canvas.refresh()
            
            def canvasPressEvent(self, event):
                """Handle canvas press events."""
                if event.button() == 1:  # Left click - add vertex
                    point = self.toMapCoordinates(event.pos())
                    self.vertices.append(point)
                    self.current_point = point
                    self.preview_item.update_vertices(self.vertices, self.current_point)
                    self.canvas.refresh()
                elif event.button() == 2:  # Right click - finish or start
                    if len(self.vertices) < self.settings['min_vertices']:
                        # Need more vertices
                        self.parent_action.show_warning("Insufficient Vertices", 
                            f"Line requires at least {self.settings['min_vertices']} vertices. "
                            f"Current: {len(self.vertices)}")
                        return
                    
                    # Finish the line
                    if len(self.vertices) >= 2:
                        # Remove preview
                        self.preview_item.hide()
                        self.canvas.scene().removeItem(self.preview_item)
                        
                        # Create the line
                        self.parent_action._create_line_from_vertices(
                            self.vertices, self.canvas_crs, self.settings
                        )
                    
                    # Restore original tool
                    if self.original_tool:
                        self.canvas.setMapTool(self.original_tool)
                    else:
                        self.canvas.unsetMapTool(self)
            
            def keyPressEvent(self, event):
                """Handle key press events."""
                from qgis.PyQt.QtCore import Qt
                if event.key() == Qt.Key_Escape:
                    # Cancel drawing
                    self.preview_item.hide()
                    self.canvas.scene().removeItem(self.preview_item)
                    
                    # Restore original tool
                    if self.original_tool:
                        self.canvas.setMapTool(self.original_tool)
                    else:
                        self.canvas.unsetMapTool(self)
                else:
                    super().keyPressEvent(event)
            
            def deactivate(self):
                """Clean up when tool is deactivated."""
                if hasattr(self, 'preview_item'):
                    self.preview_item.hide()
                    self.canvas.scene().removeItem(self.preview_item)
                super().deactivate()
        
        class LinePreviewItem(QgsMapCanvasItem):
            """Preview item for line being drawn."""
            
            def __init__(self, canvas, vertices):
                super().__init__(canvas)
                self.canvas = canvas
                self.vertices = vertices
                self.current_point = None
                self.setZValue(1000)
            
            def update_vertices(self, vertices, current_point):
                """Update vertices and current point."""
                self.vertices = vertices
                self.current_point = current_point
                self.update()
            
            def paint(self, painter, option, widget):
                """Paint the preview line."""
                if len(self.vertices) < 2 and not self.current_point:
                    return
                
                pen = QPen()
                pen.setColor(QColor(255, 0, 0, 200))
                pen.setWidth(2)
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                
                # Draw line segments
                points_to_draw = list(self.vertices)
                if self.current_point and len(points_to_draw) >= 1:
                    points_to_draw.append(self.current_point)
                
                if len(points_to_draw) >= 2:
                    for i in range(len(points_to_draw) - 1):
                        start = self.toCanvasCoordinates(points_to_draw[i])
                        end = self.toCanvasCoordinates(points_to_draw[i + 1])
                        painter.drawLine(start, end)
                
                # Draw vertices
                pen.setStyle(Qt.SolidLine)
                pen.setWidth(3)
                painter.setPen(pen)
                for vertex in self.vertices:
                    screen_point = self.toCanvasCoordinates(vertex)
                    painter.drawEllipse(screen_point, 4, 4)
        
        # Create and set the drawing tool
        drawing_tool = LineDrawingTool(canvas, first_point, canvas_crs, settings, self, original_tool)
        canvas.setMapTool(drawing_tool)
    
    def _get_draw_cursor(self):
        """Get appropriate cursor for drawing mode."""
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtGui import QCursor
        return QCursor(Qt.CrossCursor)
    
    def _create_line_from_vertices(self, vertices, crs, settings):
        """Create a line feature from vertices."""
        try:
            from qgis.core import QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsGeometry, QgsProject
            from qgis.PyQt.QtCore import QVariant
            
            # Create line geometry
            line_geometry = QgsGeometry.fromPolylineXY(vertices)
            
            # Check if layer already exists
            existing_layer = None
            if settings['add_to_existing_layer']:
                project = QgsProject.instance()
                layers = project.mapLayersByName(settings['layer_name'])
                for layer in layers:
                    if layer.geometryType() == 1:  # Line layer
                        existing_layer = layer
                        break
            
            if existing_layer:
                # Add line to existing layer
                created_fid = self._add_line_to_layer(existing_layer, line_geometry, crs, settings)
                
                if created_fid is not None:
                    # Get the created feature for full backup (needed for redo)
                    from qgis.core import QgsFeatureRequest
                    created_feature = None
                    for f in existing_layer.getFeatures(QgsFeatureRequest().setFilterFid(created_fid)):
                        created_feature = f
                        break
                    
                    # Create full feature backup for redo support
                    feature_backup = self.create_feature_backup(created_feature, existing_layer) if created_feature else {'fid': created_fid}
                    
                    # Record to history for undo
                    try:
                        hm = get_history_manager()
                        hm.record(
                            action_id=self.action_id,
                            action_name=self.name,
                            description=f"Created line with {len(vertices)} vertices in layer '{settings['layer_name']}'",
                            undo_type=HistoryManager.UNDO_TYPE_CREATE_FEATURE,
                            can_undo=True,
                            layers=[self.create_layer_descriptor(existing_layer)],
                            features=[feature_backup]
                        )
                    except Exception:
                        # History recording must not prevent successful action
                        pass
                
                existing_layer.triggerRepaint()
                
                if settings['show_confirmation']:
                    self.show_info("Line Added", f"Line added to existing layer '{settings['layer_name']}'")
            else:
                # Create new temporary layer
                line_layer, created_fid = self._create_line_layer(
                    settings['layer_name'], line_geometry, crs, settings
                )
                
                if not line_layer:
                    self.show_error("Error", "Failed to create line layer")
                    return
                
                # Add layer to project
                project = QgsProject.instance()
                project.addMapLayer(line_layer)
                
                if created_fid is not None:
                    # Get the created feature for full backup (needed for redo)
                    from qgis.core import QgsFeatureRequest
                    created_feature = None
                    for f in line_layer.getFeatures(QgsFeatureRequest().setFilterFid(created_fid)):
                        created_feature = f
                        break
                    
                    # Create full feature backup for redo support
                    feature_backup = self.create_feature_backup(created_feature, line_layer) if created_feature else {'fid': created_fid}
                    
                    # Layer definition to allow redo of the layer (structure + backups)
                    layer_def = {
                        'layer_name': line_layer.name(),
                        'crs': line_layer.crs().authid() if line_layer.crs().isValid() else '',
                        'geometry_type': QgsWkbTypes.displayString(line_layer.wkbType()),
                        'fields': [],
                        'features': [feature_backup],
                    }
                    for fld in line_layer.fields():
                        try:
                            layer_def['fields'].append({'name': fld.name(), 'qmeta_type': fld.type()})
                        except Exception:
                            layer_def['fields'].append({'name': fld.name()})
                    
                    # Record to history for undo (using CREATE_LAYER to handle layer + feature creation)
                    try:
                        hm = get_history_manager()
                        hm.record(
                            action_id=self.action_id,
                            action_name=self.name,
                            description=f"Created line with {len(vertices)} vertices in new layer '{line_layer.name()}'",
                            undo_type=HistoryManager.UNDO_TYPE_CREATE_LAYER,
                            can_undo=True,
                            undo_payload={'layer_definition': layer_def},
                            layers=[self.create_layer_descriptor(line_layer)],
                            features=[feature_backup],
                            atomic=True,
                            meta={'layer_was_created': True}
                        )
                    except Exception:
                        # History recording must not prevent successful action
                        pass
                
                if settings['show_confirmation']:
                    self.show_info("Line Created", f"Line created in new layer '{settings['layer_name']}')")
            
            # Auto zoom if requested
            if settings['auto_zoom']:
                from qgis.core import QgsRectangle
                extent = line_geometry.boundingBox()
                buffer_distance = extent.width() * 0.1  # 10% buffer
                extent.grow(buffer_distance)
                canvas = self.canvas if hasattr(self, 'canvas') else None
                if canvas:
                    canvas.setExtent(extent)
                    canvas.refresh()
            
        except Exception as e:
            self.show_error("Error", f"Failed to create line: {str(e)}")
    
    def _create_line_layer(self, layer_name, geometry, crs, settings):
        """
        Create a new temporary line layer with a line feature.
        
        Returns:
            tuple: (QgsVectorLayer, feature_id) or (None, None) if failed
        """
        try:
            from qgis.core import QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsGeometry, QgsProject
            from qgis.PyQt.QtCore import QVariant
            
            # Create memory layer
            crs_string = crs.authid() if crs.authid() else crs.toWkt()
            layer = QgsVectorLayer(f"LineString?crs={crs_string}", layer_name, "memory")
            
            if not layer.isValid():
                self.show_error("Error", f"Failed to create valid temporary layer. CRS: {crs_string}")
                return None, None
            
            # Define fields
            fields = QgsFields()
            
            if settings['add_id']:
                fields.append(QgsField('id', QVariant.Int))
            
            if settings['add_length']:
                fields.append(QgsField('length', QVariant.Double))
            
            if settings['add_vertex_count']:
                fields.append(QgsField('vertex_count', QVariant.Int))
            
            if settings['add_timestamp']:
                fields.append(QgsField('created_at', QVariant.String))
            
            if fields.count() > 0:
                layer.dataProvider().addAttributes(fields.toList())
                layer.updateFields()
            
            # Create line feature
            feature = QgsFeature()
            feature.setGeometry(geometry)
            
            # Set attributes
            attributes = []
            if settings['add_id']:
                attributes.append(1)  # First line gets ID 1
            
            if settings['add_length']:
                attributes.append(float(geometry.length()))
            
            if settings['add_vertex_count']:
                attributes.append(len(geometry.asPolyline()))
            
            if settings['add_timestamp']:
                from datetime import datetime
                attributes.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            feature.setAttributes(attributes)
            
            # Add feature to layer using dataProvider to get the correct FID
            success, added_features = layer.dataProvider().addFeatures([feature])
            
            if not success or not added_features:
                self.show_error("Error", "Failed to add feature to layer")
                return None, None
            
            created_fid = added_features[0].id()
            
            layer.updateExtents()
            
            return layer, created_fid
            
        except Exception as e:
            self.show_error("Error", f"Failed to create line layer: {str(e)}")
            return None, None
    
    def _add_line_to_layer(self, layer, geometry, crs, settings):
        """
        Add a line to an existing layer.
        
        Returns:
            int: Feature ID of created feature, or None if failed
        """
        try:
            from qgis.core import QgsFeature, QgsGeometry, QgsField, QgsCoordinateTransform, QgsProject
            from qgis.PyQt.QtCore import QVariant
            
            # Transform geometry if CRS differs
            if layer.crs() != crs:
                transform = QgsCoordinateTransform(crs, layer.crs(), QgsProject.instance())
                try:
                    geometry.transform(transform)
                except Exception as e:
                    self.show_error("Error", f"CRS transformation failed: {str(e)}")
                    return None
            
            # Get field indices
            field_indices = {}
            fields = layer.fields()
            
            if settings['add_id']:
                id_field_idx = fields.indexOf('id')
                if id_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('id', QVariant.Int)])
                    layer.updateFields()
                    id_field_idx = layer.fields().indexOf('id')
                field_indices['id'] = id_field_idx
            
            if settings['add_length']:
                length_field_idx = fields.indexOf('length')
                if length_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('length', QVariant.Double)])
                    layer.updateFields()
                    length_field_idx = layer.fields().indexOf('length')
                field_indices['length'] = length_field_idx
            
            if settings['add_vertex_count']:
                vertex_count_field_idx = fields.indexOf('vertex_count')
                if vertex_count_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('vertex_count', QVariant.Int)])
                    layer.updateFields()
                    vertex_count_field_idx = layer.fields().indexOf('vertex_count')
                field_indices['vertex_count'] = vertex_count_field_idx
            
            if settings['add_timestamp']:
                timestamp_field_idx = fields.indexOf('created_at')
                if timestamp_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('created_at', QVariant.String)])
                    layer.updateFields()
                    timestamp_field_idx = layer.fields().indexOf('created_at')
                field_indices['timestamp'] = timestamp_field_idx
            
            # Get next ID
            next_id = 1
            if settings['add_id'] and 'id' in field_indices:
                max_id = 0
                for feature in layer.getFeatures():
                    attrs = feature.attributes()
                    if field_indices['id'] < len(attrs):
                        try:
                            feature_id = int(attrs[field_indices['id']])
                            if feature_id > max_id:
                                max_id = feature_id
                        except:
                            pass
                next_id = max_id + 1
            
            # Create feature
            feature = QgsFeature()
            feature.setGeometry(geometry)
            
            # Set attributes
            attributes = [None] * len(layer.fields())
            
            if settings['add_id'] and 'id' in field_indices:
                attributes[field_indices['id']] = next_id
            
            if settings['add_length'] and 'length' in field_indices:
                attributes[field_indices['length']] = float(geometry.length())
            
            if settings['add_vertex_count'] and 'vertex_count' in field_indices:
                attributes[field_indices['vertex_count']] = len(geometry.asPolyline())
            
            if settings['add_timestamp'] and 'timestamp' in field_indices:
                from datetime import datetime
                attributes[field_indices['timestamp']] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            feature.setAttributes(attributes)
            
            # Add feature to layer using dataProvider to get correct FID
            success, added_features = layer.dataProvider().addFeatures([feature])
            
            if not success or not added_features:
                self.show_error("Error", "Failed to add feature to layer")
                return None
            
            created_fid = added_features[0].id()
            return created_fid
            
        except Exception as e:
            self.show_error("Error", f"Failed to add line to layer: {str(e)}")
            return None



# REQUIRED: Create global instance for automatic discovery
create_line_at_location_action = CreateLineAtLocationAction()

