"""
Copy Point to Clipboard Action

Copies the clicked point's coordinates to the system clipboard in a
GeoJSON-like structure. Coordinates are transformed to EPSG:4326
(longitude, latitude) before serialization. This action is informational
only and does not support undo.
"""

from .base_action import BaseAction
from qgis.core import (
    QgsWkbTypes,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsProject
)
from qgis.PyQt.QtWidgets import QApplication
import json


class CopyPointToClipboardAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = "copy_point_to_clipboard"
        self.name = "Copy Coordinates to Clipboard"
        self.category = "Utilities"
        self.description = "Copy point geometry (WGS84 coordinates) to clipboard as GeoJSON-like object."
        self.enabled = True

        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Only point features
        self.set_supported_click_types(['point', 'multipoint'])
        self.set_supported_geometry_types(['point', 'multipoint'])

    def get_settings_schema(self):
        return {
            'output_format': {
                'type': 'choice',
                'default': 'geojson',
                'label': 'Output Format',
                'description': 'Choose how coordinates are copied to the clipboard',
                'options': ['geojson', 'lat_lon', 'lon_lat_comma']
            }
        }

    def execute(self, context):
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No point feature found at this location")
            return

        detected = detected_features[0]
        feature = detected.feature
        layer = detected.layer

        try:
            if layer.geometryType() != QgsWkbTypes.PointGeometry:
                self.show_error("Error", "This action only works with point features")
                return
        except Exception:
            pass

        geom = feature.geometry()
        if not geom or geom.isEmpty():
            self.show_error("Error", "Feature has no geometry")
            return

        # Prepare coordinate transform to WGS84
        try:
            src_crs = layer.crs()
            dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())
        except Exception:
            transform = None

        try:
            if geom.isMultipart():
                multipoints = geom.asMultiPoint()
                pt = multipoints[0] if multipoints else None
            else:
                pt = geom.asPoint()

            if pt is None:
                self.show_error("Error", "Could not read point geometry")
                return

            try:
                if transform is not None:
                    p = transform.transform(pt)
                    coords = [round(p.x(), 7), round(p.y(), 7)]
                else:
                    coords = [round(pt.x(), 7), round(pt.y(), 7)]
            except Exception:
                coords = [round(pt.x(), 7), round(pt.y(), 7)]

            fmt = str(self.get_setting('output_format', 'geojson'))

            if fmt == 'geojson':
                payload = {
                    "type": "Point",
                    "coordinates": coords
                }
                text = json.dumps(payload, indent=2)
            elif fmt == 'lat_lon':
                # lat, lon simple string
                text = f"{coords[1]}, {coords[0]}"
            elif fmt == 'lon_lat_comma':
                text = f"{coords[0]},{coords[1]}"
            else:
                payload = {
                    "type": "Point",
                    "coordinates": coords
                }
                text = json.dumps(payload, indent=2)

            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            try:
                self.record_informational(
                    description=f"Copied point geometry for feature {feature.id()} to clipboard",
                    meta={
                        'feature_id': int(feature.id()),
                        'layer_id': layer.id()
                    }
                )
            except Exception:
                pass

        except Exception as e:
            self.show_error("Error", f"Failed to extract point geometry: {str(e)}")
            return


# REQUIRED: Create global instance for automatic discovery by action_loader
copy_point_to_clipboard = CopyPointToClipboardAction()
