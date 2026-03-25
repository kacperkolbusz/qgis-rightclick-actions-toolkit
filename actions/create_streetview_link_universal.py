"""
Create Street View Link (Universal)

Generates a Google Street View link for the clicked location (or detected feature)
and copies it to the clipboard for easy pasting. Optionally opens the link in the
default browser.
"""

from .base_action import BaseAction


class CreateStreetViewLinkUniversalAction(BaseAction):
    """Generate a Street View link and copy it to clipboard."""

    def __init__(self):
        super().__init__()

        # Required properties
        self.action_id = "create_streetview_link"
        self.name = "Create Street View Link"
        self.category = "Navigation"
        self.description = "Generate a Google Street View link for the clicked location and copy it to the clipboard."
        self.enabled = True

        # Action scoping - universal action
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])

        # Feature / click support
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['universal'])

    def get_settings_schema(self):
        return {
            'open_in_browser': {
                'type': 'bool',
                'default': False,
                'label': 'Open in browser',
                'description': 'Open the generated link in the default browser after copying it to the clipboard.',
            },
            'include_heading': {
                'type': 'bool',
                'default': False,
                'label': 'Include heading',
                'description': 'Include a heading (direction) parameter in the Street View link.',
            },
            'heading': {
                'type': 'float',
                'default': 0.0,
                'label': 'Heading',
                'description': 'Heading (degrees clockwise from north) used when including heading. Valid range: -360..360.',
                'min': -360.0,
                'max': 360.0,
                'step': 1.0,
            },
            'include_pitch': {
                'type': 'bool',
                'default': False,
                'label': 'Include pitch',
                'description': 'Include a pitch (up/down) parameter in the Street View link.',
            },
            'pitch': {
                'type': 'float',
                'default': 0.0,
                'label': 'Pitch',
                'description': 'Pitch (degrees) used when including pitch. Positive looks up, negative looks down. Valid range: -90..90.',
                'min': -90.0,
                'max': 90.0,
                'step': 1.0,
            },
            'fov': {
                'type': 'int',
                'default': 90,
                'label': 'Field of view',
                'description': 'Field of view for Street View in degrees. Valid range: 10..120.',
                'min': 10,
                'max': 120,
                'step': 1,
            },
            'show_popup': {
                'type': 'bool',
                'default': True,
                'label': 'Show popup',
                'description': 'Show a popup notification after the link is copied to the clipboard.',
            },
        }

    def supports_undo(self) -> bool:
        """This action is informational only and does not support undo."""
        return False

    def get_undo_category(self) -> str:
        """Return the undo category for documentation/audit purposes."""
        return 'informational'

    def execute(self, context):
        try:
            open_in_browser = bool(self.get_setting('open_in_browser', False))
            include_heading = bool(self.get_setting('include_heading', False))
            heading = float(self.get_setting('heading', 0.0))
            include_pitch = bool(self.get_setting('include_pitch', False))
            pitch = float(self.get_setting('pitch', 0.0))
            fov = int(self.get_setting('fov', 90))
            show_popup = bool(self.get_setting('show_popup', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        # Extract click point and canvas
        click_point = context.get('click_point') or context.get('map_point')
        canvas = context.get('canvas')
        layer = context.get('layer')

        if not click_point:
            # Try to extract from detected feature geometry if available
            detected = context.get('detected_features', [])
            if detected:
                try:
                    geom = detected[0].geometry()
                    if geom is None:
                        self.show_error("Error", "No geometry available for detected feature")
                        return
                    # Prefer asPoint for point geometries, otherwise use centroid
                    try:
                        click_point = geom.asPoint()
                    except Exception:
                        click_point = geom.centroid().asPoint()
                except Exception:
                    click_point = None

        if not click_point:
            self.show_error("Error", "No click point available")
            return

        # Determine source CRS
        try:
            from qgis.core import QgsCoordinateTransform, QgsProject, QgsCoordinateReferenceSystem

            src_crs = None
            if canvas:
                try:
                    src_crs = canvas.mapSettings().destinationCrs()
                except Exception:
                    src_crs = None
            if src_crs is None and layer is not None:
                try:
                    src_crs = layer.crs()
                except Exception:
                    src_crs = None

            # Default to canvas CRS if still None
            if src_crs is None and canvas is None:
                # Try project CRS
                src_crs = QgsProject.instance().crs()

            # Target CRS: WGS84
            tgt_crs = QgsCoordinateReferenceSystem('EPSG:4326')

            # Transform point to WGS84 if needed
            if src_crs is not None and src_crs != tgt_crs:
                transform = QgsCoordinateTransform(src_crs, tgt_crs, QgsProject.instance())
                try:
                    pt = transform.transform(click_point)
                except Exception:
                    # Some versions return tuple-like; attempt manual conversion
                    pt = transform.transform(click_point)
            else:
                pt = click_point

            lat = float(pt.y())
            lon = float(pt.x())

            # Build Google Street View URL
            # Base params
            params = [f"viewpoint={lat},{lon}"]

            # Add optional params when requested
            if include_heading:
                # Normalize heading to [-360,360]
                try:
                    h = float(heading)
                except Exception:
                    h = 0.0
                params.append(f"heading={h}")

            if include_pitch:
                try:
                    p = float(pitch)
                except Exception:
                    p = 0.0
                params.append(f"pitch={p}")

            # Clamp FOV
            try:
                fov_val = int(fov)
            except Exception:
                fov_val = 90
            if fov_val < 10:
                fov_val = 10
            if fov_val > 120:
                fov_val = 120
            params.append(f"fov={fov_val}")

            param_str = "&".join(params)
            link = f"https://www.google.com/maps/@?api=1&map_action=pano&{param_str}"

            # Copy to clipboard
            try:
                from qgis.PyQt.QtWidgets import QApplication
                QApplication.clipboard().setText(link)
            except Exception:
                # Fallback: try QtGui clipboard
                try:
                    from qgis.PyQt.QtGui import QGuiApplication
                    QGuiApplication.clipboard().setText(link)
                except Exception:
                    self.show_warning("Warning", "Could not copy link to clipboard, but the link was generated")

            # Optionally open in browser
            if open_in_browser:
                try:
                    from qgis.PyQt.QtGui import QDesktopServices
                    from qgis.PyQt.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl(link))
                except Exception:
                    # Best-effort; ignore failures
                    pass

            # Inform the user (controlled by setting)
            if show_popup:
                self.show_info("Street View Link", "Link copied to clipboard")

            # Record as informational in the History Manager (no undo)
            try:
                self.record_informational(
                    description=f"Generated Street View link at ({lat:.6f}, {lon:.6f})",
                    meta={'lat': lat, 'lon': lon, 'link': link, 'open_in_browser': open_in_browser}
                )
            except Exception:
                # History recording is non-fatal; ignore failures
                pass

        except Exception as e:
            self.show_error("Error", f"Failed to generate Street View link: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
create_streetview_link_universal_action = CreateStreetViewLinkUniversalAction()
