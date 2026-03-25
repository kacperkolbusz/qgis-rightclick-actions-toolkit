"""
Copy Line to Clipboard Action

Copies the clicked line's coordinates to the system clipboard in a
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


class CopyLineToClipboardAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = "copy_line_to_clipboard"
        self.name = "Copy Coordinates to Clipboard"
        self.category = "Utilities"
        self.description = "Copy line geometry (WGS84 coordinates) to clipboard as GeoJSON-like object."
        self.enabled = True

        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Only line features
        self.set_supported_click_types(['line', 'multiline'])
        self.set_supported_geometry_types(['line', 'multiline'])

    def get_settings_schema(self):
        return {
            'output_format': {
                'type': 'choice',
                'default': 'geojson',
                'label': 'Output Format',
                'description': 'Choose how coordinates are copied to the clipboard',
                'options': ['geojson', 'lat_lon_per_line', 'lon_lat_comma_separated']
            }
        }

    def execute(self, context):
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No line feature found at this location")
            return

        detected = detected_features[0]
        feature = detected.feature
        layer = detected.layer

        try:
            if layer.geometryType() != QgsWkbTypes.LineGeometry:
                self.show_error("Error", "This action only works with line features")
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

        coords = []

        try:
            if geom.isMultipart():
                multilines = geom.asMultiPolyline()
            else:
                polyline = geom.asPolyline()
                multilines = [polyline]

            for line in multilines:
                line_coords = []
                for pt in line:
                    try:
                        if transform is not None:
                            p = transform.transform(pt)
                            line_coords.append([round(p.x(), 7), round(p.y(), 7)])
                        else:
                            line_coords.append([round(pt.x(), 7), round(pt.y(), 7)])
                    except Exception:
                        line_coords.append([round(pt.x(), 7), round(pt.y(), 7)])
                coords.append(line_coords)

            if len(coords) == 1:
                payload = {
                    "type": "LineString",
                    "coordinates": coords[0]
                }
            else:
                payload = {
                    "type": "MultiLineString",
                    "coordinates": coords
                }

            fmt = str(self.get_setting('output_format', 'geojson'))
            if fmt == 'geojson':
                text = json.dumps(payload, indent=2)
            elif fmt == 'lat_lon_per_line':
                lines = []
                for line in coords:
                    for xy in line:
                        # xy is [lon, lat]
                        lines.append(f"{xy[1]}, {xy[0]}")
                    lines.append("")
                text = "\n".join(lines).strip()
            elif fmt == 'lon_lat_comma_separated':
                pairs = []
                for line in coords:
                    for xy in line:
                        pairs.append(f"{xy[0]},{xy[1]}")
                text = ";".join(pairs)
            else:
                text = json.dumps(payload, indent=2)

            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            try:
                self.record_informational(
                    description=f"Copied line geometry for feature {feature.id()} to clipboard",
                    meta={
                        'feature_id': int(feature.id()),
                        'layer_id': layer.id()
                    }
                )
            except Exception:
                pass

        except Exception as e:
            self.show_error("Error", f"Failed to extract line geometry: {str(e)}")
            return


# REQUIRED: Create global instance for automatic discovery by action_loader
copy_line_to_clipboard = CopyLineToClipboardAction()
