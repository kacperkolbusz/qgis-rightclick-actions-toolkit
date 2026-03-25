"""
Create Rectangle Around Line Layer Action

Creates a rectangular polygon layer that fully encloses the target line layer's
extent. The user can configure a `padding` value (in layer map units) to add extra
space around the line layer when creating the rectangle. The new layer can be
created as a temporary (memory) layer or saved to disk.
"""

from .base_action import BaseAction
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsFillSymbol,
)


class CreateRectangleAroundLineLayerAction(BaseAction):
    """Create a rectangular polygon layer enclosing a line layer."""

    def __init__(self):
        super().__init__()
        self.action_id = "create_rectangle_around_line_layer"
        self.name = "Create Rectangle Around Line Layer"
        self.category = "Line RAT"
        self.description = (
            "Creates a rectangular polygon layer that fully contains the target "
            "line layer. Padding (in map units) can be configured in settings."
        )
        self.enabled = True

        # This is a layer-level action
        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        # Support line geometries
        self.set_supported_geometry_types(['line', 'multiline'])
        # Make the action available when working with layers/universal contexts
        self.set_supported_click_types(['universal', 'canvas', 'line'])

    def get_settings_schema(self):
        return {
            'padding': {
                'type': 'float',
                'default': 500.0,
                'min': 0.0,
                'label': 'Padding (map units)',
                'description': 'Padding to add around the layer extent when creating the rectangle (in layer map units).'
            },
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'options': ['temporary', 'permanent'],
                'label': 'Layer Storage',
                'description': 'Create the rectangle as a temporary memory layer or save it permanently to disk.'
            }
        }

    def execute(self, context):
        layer = context.get('layer')
        if layer is None:
            self.show_error("Error", "No target layer found in context.")
            return

        # Ensure layer is a vector line layer
        try:
            geom_type = layer.geometryType()
        except Exception:
            self.show_error("Error", "Invalid layer provided.")
            return

        # geometryType(): 0 = Point, 1 = Line, 2 = Polygon
        if geom_type != 1:
            self.show_error("Error", "This action only supports line layers.")
            return

        # Get padding setting (convert to float)
        try:
            padding = float(self.get_setting('padding', 500.0))
            if padding < 0:
                padding = 0.0
        except (TypeError, ValueError):
            self.show_error("Error", "Invalid padding setting. Please provide a numeric value.")
            return

        storage_type = str(self.get_setting('layer_storage_type', 'temporary'))

        # Get layer extent (in layer CRS)
        extent: QgsRectangle = layer.extent()
        if extent is None or extent.isNull():
            self.show_error("Error", "Layer extent is empty or invalid.")
            return

        # Expand extent by padding
        rect = QgsRectangle(extent.xMinimum() - padding,
                            extent.yMinimum() - padding,
                            extent.xMaximum() + padding,
                            extent.yMaximum() + padding)

        # Create polygon geometry from rectangle
        rect_geom = QgsGeometry.fromRect(rect)

        # Create a new memory polygon layer with same CRS as source
        crs_authid = layer.crs().authid() if layer.crs().isValid() else ''
        uri = "Polygon"
        if crs_authid:
            uri = f"Polygon?crs={crs_authid}"

        new_layer_name = f"Rectangle for {layer.name()}"
        new_layer = QgsVectorLayer(uri, new_layer_name, "memory")
        if not new_layer.isValid():
            self.show_error("Error", "Failed to create polygon layer.")
            return

        # Style the new layer: no fill, thick outline
        try:
            sym = QgsFillSymbol.createSimple({
                'color': '0,0,0,0',
                'outline_color': '0,0,0,0',
                'outline_width': '0'
            })
            new_layer.renderer().setSymbol(sym)
        except Exception:
            sym = None

        # Add feature
        feat = QgsFeature()
        feat.setGeometry(rect_geom)

        prov = new_layer.dataProvider()
        ok, added_feats = prov.addFeatures([feat])
        if not ok:
            self.show_error("Error", "Failed to add rectangle feature to the new layer.")
            return

        # Add layer to project
        QgsProject.instance().addMapLayer(new_layer)

        # If user chose permanent storage, prompt for filename and save
        if storage_type == 'permanent':
            save_path, _ = QFileDialog.getSaveFileName(None, "Save rectangle layer", "", "ESRI Shapefile (*.shp);;GeoPackage (*.gpkg)")
            if save_path:
                # Determine format from extension
                if save_path.lower().endswith('.gpkg'):
                    driver_name = 'GPKG'
                else:
                    driver_name = 'ESRI Shapefile'

                res, err = QgsVectorFileWriter.writeAsVectorFormat(new_layer, save_path, 'utf-8', new_layer.crs(), driver_name)
                if res != QgsVectorFileWriter.NoError:
                    self.show_error("Error", f"Failed to save layer: {res}")
                else:
                    # Remove the memory layer and load saved layer instead
                    QgsProject.instance().removeMapLayer(new_layer.id())
                    saved_layer = QgsVectorLayer(save_path, new_layer_name, 'ogr')
                    if saved_layer.isValid():
                        # Apply same invisible symbol to saved layer if symbol was created
                        try:
                            if sym is not None:
                                saved_layer.renderer().setSymbol(sym)
                        except Exception:
                            pass
                        QgsProject.instance().addMapLayer(saved_layer)
                        new_layer = saved_layer
                    else:
                        self.show_warning("Warning", "Layer saved but failed to load into project. You can add it manually.")

        # Record to history as a create_layer action (undoable)
        try:
            layers_desc = [self.create_layer_descriptor(new_layer)]
            description = f"Created rectangle layer for '{layer.name()}'"
            self.record_to_history(
                description=description,
                undo_type='create_layer',
                can_undo=True,
                undo_payload={'layers': layers_desc},
                layers=layers_desc,
                meta={'padding': padding}
            )
        except Exception:
            # History recording should not block the action
            pass

        self.show_info("Done", f"Rectangle layer created: {new_layer.name()}")


# Global instance for automatic discovery
create_rectangle_around_line_layer = CreateRectangleAroundLineLayerAction()
