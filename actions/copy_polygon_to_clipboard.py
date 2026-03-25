"""
Copy Polygon to Clipboard Action

Copies the clicked polygon's coordinates to the system clipboard in a
GeoJSON-like structure. The coordinates are transformed to EPSG:4326
(longitude, latitude) before being serialized. This action is informational
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


class CopyPolygonToClipboardAction(BaseAction):
    def __init__(self):
        super().__init__()
        self.action_id = "copy_polygon_to_clipboard"
        self.name = "Copy Coordinates to Clipboard"
        self.category = "Utilities"
        self.description = "Copy polygon geometry (WGS84 coordinates) to clipboard as GeoJSON-like object."
        self.enabled = True

        self.set_action_scope('feature')
        self.set_supported_scopes(['feature'])

        # Only polygon features
        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

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
            self.show_error("Error", "No polygon feature found at this location")
            return

        detected = detected_features[0]
        feature = detected.feature
        layer = detected.layer

        # Validate geometry type
        try:
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                self.show_error("Error", "This action only works with polygon features")
                return
        except Exception:
            # Fallback check
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
                multipolys = geom.asMultiPolygon()
            else:
                # asPolygon() returns list of rings; make it a single polygon inside list
                polygon = geom.asPolygon()
                multipolys = [polygon]

            # Build coordinate arrays
            for polygon in multipolys:
                # polygon is a list of rings; each ring is list of points
                rings = []
                for ring in polygon:
                    ring_coords = []
                    for pt in ring:
                        try:
                            if transform is not None:
                                p = transform.transform(pt)
                                ring_coords.append([round(p.x(), 7), round(p.y(), 7)])
                            else:
                                ring_coords.append([round(pt.x(), 7), round(pt.y(), 7)])
                        except Exception:
                            # Fallback to raw coords
                            ring_coords.append([round(pt.x(), 7), round(pt.y(), 7)])
                    rings.append(ring_coords)
                coords.append(rings)

            # If there's only one polygon, produce a Polygon; otherwise MultiPolygon
            if len(coords) == 1:
                payload = {
                    "type": "Polygon",
                    "coordinates": coords[0]
                }
            else:
                payload = {
                    "type": "MultiPolygon",
                    "coordinates": coords
                }

            # Format output according to user setting
            fmt = str(self.get_setting('output_format', 'geojson'))

            if fmt == 'geojson':
                text = json.dumps(payload, indent=2)
            elif fmt == 'lat_lon_per_line':
                # lat, lon per line for each vertex; separate rings by blank line
                lines = []
                for poly in coords:
                    for ring in poly:
                        for xy in ring:
                            # xy is [lon, lat]
                            lines.append(f"{xy[1]}, {xy[0]}")
                        lines.append("")
                text = "\n".join(lines).strip()
            elif fmt == 'lon_lat_comma_separated':
                # single line of lon,lat pairs separated by semicolons
                pairs = []
                for poly in coords:
                    for ring in poly:
                        for xy in ring:
                            pairs.append(f"{xy[0]},{xy[1]}")
                text = ";".join(pairs)
            else:
                text = json.dumps(payload, indent=2)

            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Record informational history (non-undoable)
            try:
                self.record_informational(
                    description=f"Copied polygon geometry for feature {feature.id()} to clipboard",
                    meta={
                        'feature_id': int(feature.id()),
                        'layer_id': layer.id()
                    }
                )
            except Exception:
                pass

        except Exception as e:
            self.show_error("Error", f"Failed to extract polygon geometry: {str(e)}")
            return


# REQUIRED: Create global instance for automatic discovery by action_loader
copy_polygon_to_clipboard = CopyPolygonToClipboardAction()
