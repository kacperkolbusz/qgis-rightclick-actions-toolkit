"""
Fill Polygon Gaps Layer Action for Right-click Utilities and Shortcuts Hub

Analyzes a polygon layer for gaps between features and fills them to create
a seamless polygon coverage. Each gap is assigned to the adjacent polygon
with the longest shared boundary. Creates a new polygon layer with all gaps
filled.
"""

import os
from .base_action import BaseAction
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsWkbTypes, QgsProject,
    QgsCoordinateTransform
)
from qgis.PyQt.QtCore import QVariant


class FillPolygonGapsLayerAction(BaseAction):
    """
    Action to fill gaps in a polygon layer and create a seamless coverage.

    Detects gaps between polygon features (either enclosed holes, gaps within
    the convex hull, or gaps within the bounding box) and fills each gap by
    extending the polygon with the longest shared boundary. Outputs a new
    polygon layer.
    """

    def __init__(self):
        super().__init__()

        self.action_id = 'fill_polygon_gaps_layer'
        self.name = 'Fill Polygon Gaps (Make Seamless)'
        self.category = 'Geometry'
        self.description = (
            'Analyzes a polygon layer for gaps between features and fills them, '
            'creating a seamless polygon coverage. Each gap is assigned to the '
            'adjacent polygon with the longest shared boundary. Outputs a new '
            'polygon layer with all gaps filled.'
        )
        self.enabled = True

        self.set_action_scope('layer')
        self.set_supported_scopes(['layer'])

        self.set_supported_click_types(['polygon', 'multipolygon'])
        self.set_supported_geometry_types(['polygon', 'multipolygon'])

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings_schema(self):
        return {
            'gap_mode': {
                'type': 'choice',
                'label': 'Gap Detection Mode',
                'default': 'bounding box',
                'description': (
                    '"Bounding box" (recommended) — finds every gap anywhere in the layer '
                    'and automatically discards areas at the outer edge, so the overall '
                    'layer boundary is unchanged. Catches interior holes AND all edge '
                    'gaps between adjacent polygons. '
                    '"Convex hull" — same filtered approach limited to within the convex hull. '
                    '"Enclosed only" — fills only holes that are completely surrounded '
                    'by polygons (interior rings in the union).'
                ),
                'options': ['bounding box', 'convex hull', 'enclosed only'],
            },
            'min_gap_area': {
                'type': 'float',
                'label': 'Minimum Gap Area',
                'default': 0.0,
                'description': (
                    'Minimum area (in layer CRS square units) a gap must have to be filled. '
                    'Set to 0 to fill all gaps regardless of size.'
                ),
                'min': 0.0,
                'max': 1e12,
                'step': 0.1,
            },
            'max_gap_area': {
                'type': 'float',
                'label': 'Maximum Gap Area',
                'default': 0.0,
                'description': (
                    'Maximum area (in layer CRS square units) a gap may have to be filled. '
                    'Set to 0 for no upper limit.'
                ),
                'min': 0.0,
                'max': 1e12,
                'step': 1.0,
            },
            'output_layer_name': {
                'type': 'str',
                'label': 'Output Layer Name',
                'default': '{layer_name} (Seamless)',
                'description': (
                    'Name for the output layer. '
                    'Use {layer_name} as a placeholder for the source layer name.'
                ),
            },
            'layer_storage_type': {
                'type': 'choice',
                'label': 'Layer Storage Type',
                'default': 'temporary',
                'description': (
                    'Temporary layers exist in memory only and are lost when QGIS closes. '
                    'Permanent layers are saved to disk.'
                ),
                'options': ['temporary', 'permanent'],
            },
            'preserve_attributes': {
                'type': 'bool',
                'label': 'Preserve Original Attributes',
                'default': True,
                'description': 'Copy original feature attributes to the output layer.',
            },
            'zoom_to_result': {
                'type': 'bool',
                'label': 'Zoom to Result',
                'default': True,
                'description': 'Automatically zoom to the output layer after creation.',
            },
            'show_success_message': {
                'type': 'bool',
                'label': 'Show Success Message',
                'default': True,
                'description': 'Show a summary with the number of gaps found and filled.',
            },
        }

    def get_setting(self, setting_name, default_value=None):
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)

    # ------------------------------------------------------------------
    # Undo support
    # ------------------------------------------------------------------

    def supports_undo(self) -> bool:
        return True

    def get_undo_category(self) -> str:
        return 'trivial'

    # ------------------------------------------------------------------
    # Gap-detection helpers
    # ------------------------------------------------------------------

    def _extract_enclosed_holes(self, total_union):
        """
        Return each interior hole of a (multi-)polygon union as an individual
        QgsGeometry polygon. These represent fully-enclosed gaps.
        """
        holes = []
        try:
            if total_union.isMultipart():
                for part in total_union.asMultiPolygon():
                    for ring in part[1:]:          # skip exterior ring (index 0)
                        hole = QgsGeometry.fromPolygonXY([ring])
                        if not hole.isEmpty() and hole.area() > 0:
                            holes.append(hole)
            else:
                poly = total_union.asPolygon()
                if poly:
                    for ring in poly[1:]:          # skip exterior ring (index 0)
                        hole = QgsGeometry.fromPolygonXY([ring])
                        if not hole.isEmpty() and hole.area() > 0:
                            holes.append(hole)
        except Exception:
            pass
        return holes

    def _extract_gap_polygons(self, gaps_geom, min_area, max_area):
        """
        Split a gap geometry into individual polygon parts and apply area
        filters. Handles Polygon, MultiPolygon, and GeometryCollection types.
        Returns a list of QgsGeometry polygons.
        """
        parts = []

        def _accept(geom):
            if geom.isEmpty():
                return False
            area = geom.area()
            if area <= 0:
                return False
            if min_area > 0 and area < min_area:
                return False
            if max_area > 0 and area > max_area:
                return False
            return True

        try:
            if gaps_geom.isMultipart():
                # Try asMultiPolygon first (works for true MultiPolygon)
                multi = gaps_geom.asMultiPolygon()
                if multi:
                    for part in multi:
                        geom = QgsGeometry.fromPolygonXY(part)
                        if _accept(geom):
                            parts.append(geom)
                else:
                    # GeometryCollection fallback: iterate constituent geometries
                    try:
                        coll = gaps_geom.constGet()
                        for i in range(coll.numGeometries()):
                            part_geom = QgsGeometry(coll.geometryN(i).clone())
                            if part_geom.type() != QgsWkbTypes.PolygonGeometry:
                                continue
                            if _accept(part_geom):
                                parts.append(part_geom)
                    except Exception:
                        pass
            else:
                if _accept(gaps_geom):
                    parts.append(QgsGeometry(gaps_geom))
        except Exception:
            pass
        return parts

    def _filter_external_gaps(self, gap_parts, coverage_geom):
        """
        Remove gap candidates that touch the boundary of the coverage envelope
        (bounding box or convex hull). Such candidates are external fill areas
        outside the polygon cluster, not true inter-polygon gaps.

        True gaps between adjacent polygons are fully bounded by polygon edges
        and never intersect the coverage envelope boundary.
        """
        try:
            env_poly = coverage_geom.asPolygon()
            if not env_poly:
                return gap_parts
            envelope_boundary = QgsGeometry.fromPolylineXY(env_poly[0])
            if not envelope_boundary or envelope_boundary.isEmpty():
                return gap_parts
        except Exception:
            return gap_parts

        # Tolerance: tiny fraction of the envelope size to bridge float imprecision
        bbox = coverage_geom.boundingBox()
        scale = max(bbox.width(), bbox.height())
        tol = max(scale * 1e-6, 1e-10)

        interior_gaps = []
        for gap in gap_parts:
            try:
                gap_expanded = gap.buffer(tol, 4)
                if gap_expanded and not gap_expanded.isEmpty():
                    if gap_expanded.intersects(envelope_boundary):
                        continue   # touches the envelope edge → external area
                interior_gaps.append(gap)
            except Exception:
                interior_gaps.append(gap)  # include when check cannot run

        return interior_gaps

    def _find_best_polygon_for_gap(self, gap_geom, valid_features):
        """
        Find which original polygon should absorb this gap.

        Pass 1 : longest shared boundary via direct intersection/touch.
        Pass 2 : same check but with a small buffer around the gap to catch
                 near-touching cases caused by floating-point imprecision.
        Pass 3 : nearest polygon by distance (final fallback).

        Returns the feature ID of the winning polygon, or None.
        """
        best_fid = None
        best_shared_len = -1.0

        # Pass 1 – direct boundary check
        for feature, feat_geom in valid_features:
            try:
                shared = gap_geom.intersection(feat_geom)
                if shared and not shared.isEmpty():
                    shared_len = shared.length()
                    if shared_len > best_shared_len:
                        best_shared_len = shared_len
                        best_fid = feature.id()
            except Exception:
                continue

        if best_fid is not None:
            return best_fid

        # Pass 2 – buffered check for near-touching geometries
        try:
            bbox = gap_geom.boundingBox()
            tolerance = max(bbox.width(), bbox.height()) * 0.005
            tolerance = max(tolerance, 1e-8)
            gap_buffered = gap_geom.buffer(tolerance, 3)
        except Exception:
            gap_buffered = None

        if gap_buffered and not gap_buffered.isEmpty():
            for feature, feat_geom in valid_features:
                try:
                    shared = gap_buffered.intersection(feat_geom)
                    if shared and not shared.isEmpty():
                        shared_len = shared.length()
                        if shared_len > best_shared_len:
                            best_shared_len = shared_len
                            best_fid = feature.id()
                except Exception:
                    continue

        if best_fid is not None:
            return best_fid

        # Pass 3 – nearest distance fallback
        best_dist = float('inf')
        for feature, feat_geom in valid_features:
            try:
                dist = gap_geom.distance(feat_geom)
                if dist < best_dist:
                    best_dist = dist
                    best_fid = feature.id()
            except Exception:
                continue

        return best_fid

    # ------------------------------------------------------------------
    # Main execute
    # ------------------------------------------------------------------

    def execute(self, context):
        """Execute the fill polygon gaps action."""

        # ── Settings ─────────────────────────────────────────────────
        try:
            gap_mode = str(self.get_setting('gap_mode', 'bounding box'))
            min_gap_area = float(self.get_setting('min_gap_area', 0.0))
            max_gap_area = float(self.get_setting('max_gap_area', 0.0))
            output_name_template = str(
                self.get_setting('output_layer_name', '{layer_name} (Seamless)')
            )
            layer_storage = str(self.get_setting('layer_storage_type', 'temporary'))
            preserve_attributes = bool(self.get_setting('preserve_attributes', True))
            zoom_to_result = bool(self.get_setting('zoom_to_result', True))
            show_success = bool(self.get_setting('show_success_message', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return

        # ── Resolve layer ─────────────────────────────────────────────
        detected_features = context.get('detected_features', [])
        if not detected_features:
            self.show_error("Error", "No polygon features found at this location.")
            return

        layer = detected_features[0].layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.show_error("Error", "This action only works with polygon layers.")
            return

        # ── Collect valid features ────────────────────────────────────
        all_features = list(layer.getFeatures())
        if len(all_features) < 2:
            self.show_info(
                "Info",
                "The layer must contain at least 2 polygon features to detect gaps."
            )
            return

        valid_features = []
        for f in all_features:
            geom = f.geometry()
            if not geom or geom.isEmpty():
                continue
            if not geom.isGeosValid():
                fixed = geom.makeValid()
                if fixed and not fixed.isEmpty():
                    valid_features.append((f, fixed))
            else:
                valid_features.append((f, geom))

        if len(valid_features) < 2:
            self.show_error(
                "Error",
                "The layer must contain at least 2 valid (non-empty) polygon geometries."
            )
            return

        all_geoms = [geom for _, geom in valid_features]

        # ── Union all polygons ────────────────────────────────────────
        try:
            total_union = QgsGeometry.unaryUnion(all_geoms)
            if not total_union or total_union.isEmpty():
                self.show_error("Error", "Failed to compute the union of all polygons.")
                return
        except Exception as e:
            self.show_error("Error", f"Failed to compute polygon union: {str(e)}")
            return

        # ── Find gap polygons based on selected mode ──────────────────
        gap_polygons = []
        no_gaps_msg = ""
        try:
            if gap_mode == 'enclosed only':
                raw_holes = self._extract_enclosed_holes(total_union)
                if min_gap_area > 0 or max_gap_area > 0:
                    gap_polygons = [
                        g for g in raw_holes
                        if (min_gap_area <= 0 or g.area() >= min_gap_area) and
                           (max_gap_area <= 0 or g.area() <= max_gap_area)
                    ]
                else:
                    gap_polygons = raw_holes
                no_gaps_msg = (
                    "No enclosed gaps were found.\n\n"
                    "Enclosed gaps are interior holes completely surrounded by polygons.\n"
                    "Switch to 'Bounding box' mode to also fill edge gaps between "
                    "polygons that don't quite meet at the outer boundary of the layer."
                )
            else:
                # Both 'bounding box' and 'convex hull' use the same approach:
                # compute envelope − union, then strip any parts that touch the
                # envelope boundary (those are external areas, not real gaps).
                if gap_mode == 'convex hull':
                    coverage_geom = total_union.convexHull()
                    no_gaps_msg = (
                        "No inter-polygon gaps were found within the convex hull. "
                        "The layer already forms a seamless coverage."
                    )
                else:  # bounding box (default)
                    coverage_geom = QgsGeometry.fromRect(total_union.boundingBox())
                    no_gaps_msg = (
                        "No inter-polygon gaps were found. "
                        "The layer already forms a seamless coverage."
                    )

                if not coverage_geom or coverage_geom.isEmpty():
                    self.show_error("Error", "Failed to compute coverage envelope.")
                    return

                gaps_raw = coverage_geom.difference(total_union)
                if not gaps_raw or gaps_raw.isEmpty():
                    if show_success:
                        self.show_info("No Gaps Found", no_gaps_msg)
                    return

                # Extract all candidate gap parts
                all_candidates = self._extract_gap_polygons(
                    gaps_raw, min_gap_area, max_gap_area
                )

                # KEY FIX: remove parts that touch the envelope boundary.
                # External areas always border the envelope edge.
                # True inter-polygon gaps are bounded only by polygon edges.
                gap_polygons = self._filter_external_gaps(all_candidates, coverage_geom)
        except Exception as e:
            self.show_error("Error", f"Failed to compute gaps: {str(e)}")
            return

        if not gap_polygons:
            if show_success:
                self.show_info("No Gaps Found", no_gaps_msg)
            return

        # ── Iterative gap filling (up to MAX_ITER passes) ─────────────
        # After each merge round, re-union the updated geometries and
        # re-detect any remaining gaps. Repeat until the layer is clean
        # or no further progress can be made.
        fid_to_geom = {f.id(): QgsGeometry(geom) for f, geom in valid_features}
        fid_to_feat = {f.id(): f for f, geom in valid_features}

        total_filled = 0
        MAX_ITER = 10

        for _iter in range(MAX_ITER):
            iter_geoms = list(fid_to_geom.values())
            try:
                iter_union = QgsGeometry.unaryUnion(iter_geoms)
                if not iter_union or iter_union.isEmpty():
                    break
            except Exception:
                break

            # Detect remaining gaps in the current geometry state
            try:
                if gap_mode == 'enclosed only':
                    iter_gaps = self._extract_enclosed_holes(iter_union)
                    if min_gap_area > 0 or max_gap_area > 0:
                        iter_gaps = [
                            g for g in iter_gaps
                            if (min_gap_area <= 0 or g.area() >= min_gap_area) and
                               (max_gap_area <= 0 or g.area() <= max_gap_area)
                        ]
                else:
                    if gap_mode == 'convex hull':
                        iter_coverage = iter_union.convexHull()
                    else:  # bounding box
                        iter_coverage = QgsGeometry.fromRect(iter_union.boundingBox())
                    if not iter_coverage or iter_coverage.isEmpty():
                        break
                    iter_raw = iter_coverage.difference(iter_union)
                    if not iter_raw or iter_raw.isEmpty():
                        break
                    iter_candidates = self._extract_gap_polygons(
                        iter_raw, min_gap_area, max_gap_area
                    )
                    iter_gaps = self._filter_external_gaps(iter_candidates, iter_coverage)
            except Exception:
                break

            if not iter_gaps:
                break  # No remaining gaps – done

            # Assign each gap to the best adjacent polygon
            current_valid = [
                (fid_to_feat[fid], fid_to_geom[fid]) for fid in fid_to_geom
            ]
            additions = {}
            for gap_geom in iter_gaps:
                best_fid = self._find_best_polygon_for_gap(gap_geom, current_valid)
                if best_fid is not None:
                    additions.setdefault(best_fid, []).append(gap_geom)

            if not additions:
                # Gaps detected but none assignable – stop to avoid infinite loop
                break

            # Merge each gap into its assigned polygon geometry
            for fid, gaps in additions.items():
                merged = QgsGeometry(fid_to_geom[fid])
                for gap in gaps:
                    try:
                        combined = merged.combine(gap)
                        if combined and not combined.isEmpty():
                            merged = combined
                    except Exception:
                        pass
                fid_to_geom[fid] = merged

            total_filled += sum(len(v) for v in additions.values())

        if total_filled == 0:
            self.show_warning(
                "Warning",
                "Gaps were detected but could not be assigned to any adjacent polygon. "
                "This may happen with degenerate or non-touching geometries."
            )
            return

        # ── Build output layer ────────────────────────────────────────
        output_name = output_name_template.replace('{layer_name}', layer.name())
        crs_auth = layer.crs().authid()
        uri = f"Polygon?crs={crs_auth}" if crs_auth else "Polygon"

        out_layer = QgsVectorLayer(uri, output_name, "memory")
        if not out_layer.isValid():
            self.show_error("Error", "Failed to create output layer.")
            return

        if preserve_attributes:
            out_layer.dataProvider().addAttributes(layer.fields().toList())
        out_layer.updateFields()

        out_features = []
        for fid in fid_to_geom:
            feat = fid_to_feat[fid]
            out_feat = QgsFeature(out_layer.fields())
            out_feat.setGeometry(fid_to_geom[fid])
            if preserve_attributes:
                out_feat.setAttributes(feat.attributes())
            out_features.append(out_feat)

        ok, added = out_layer.dataProvider().addFeatures(out_features)
        if not ok or not added:
            self.show_error("Error", "Failed to write features to output layer.")
            return

        out_layer.updateExtents()

        # ── Optional: save permanently ────────────────────────────────
        if layer_storage == 'permanent':
            from qgis.PyQt.QtWidgets import QFileDialog
            from qgis.core import QgsVectorFileWriter
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                "Save Seamless Layer As",
                "",
                "GeoPackage (*.gpkg);;Shapefile (*.shp);;All Files (*)"
            )
            if file_path:
                ext = os.path.splitext(file_path)[1].lower()
                driver = "GPKG" if ext == '.gpkg' else "ESRI Shapefile"
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    out_layer, file_path, "UTF-8", out_layer.crs(), driver
                )
                if error[0] == QgsVectorFileWriter.NoError:
                    saved = QgsVectorLayer(file_path, output_name, "ogr")
                    if saved.isValid():
                        out_layer = saved

        QgsProject.instance().addMapLayer(out_layer)

        # ── Zoom to result ────────────────────────────────────────────
        if zoom_to_result:
            canvas = context.get('canvas')
            if canvas:
                try:
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = out_layer.crs()
                    extent = out_layer.extent()
                    if canvas_crs != layer_crs:
                        transform = QgsCoordinateTransform(
                            layer_crs, canvas_crs, QgsProject.instance()
                        )
                        extent = transform.transformBoundingBox(extent)
                    canvas.setExtent(extent)
                    canvas.refresh()
                except Exception:
                    pass

        # ── Summary message ───────────────────────────────────────────
        if show_success:
            passes_note = (
                f"\nPasses required : {_iter + 1}"
                if (_iter + 1) > 1 else ""
            )
            self.show_info(
                "Gaps Filled Successfully",
                f"Seamless polygon layer created.\n\n"
                f"Source layer : {layer.name()}\n"
                f"Gaps filled  : {total_filled}"
                f"{passes_note}\n"
                f"Output layer : {out_layer.name()}"
            )

        # ── Record to history ─────────────────────────────────────────
        try:
            created_backups = [
                self.create_feature_backup(f, out_layer)
                for f in out_layer.getFeatures()
            ]
            fields_info = [
                {
                    'name': fld.name(),
                    'qmeta_type': fld.type(),
                    'length': fld.length(),
                    'precision': fld.precision(),
                }
                for fld in out_layer.fields()
            ]
            layer_def = {
                'layer_name': out_layer.name(),
                'crs': out_layer.crs().authid() if out_layer.crs().isValid() else '',
                'geometry_type': QgsWkbTypes.displayString(out_layer.wkbType()),
                'fields': fields_info,
                'features': created_backups,
            }
            self.record_to_history(
                description=(
                    f"Filled {total_filled} gap(s) in '{layer.name()}' "
                    f"to create seamless layer '{out_layer.name()}'"
                ),
                undo_type='create_layer',
                can_undo=True,
                undo_payload={'layer_definitions': [layer_def]},
                layers=[self.create_layer_descriptor(out_layer)],
                features=created_backups,
            )
        except Exception:
            pass  # History failure must not crash the action


# Global instance for automatic discovery
fill_polygon_gaps_layer = FillPolygonGapsLayerAction()
