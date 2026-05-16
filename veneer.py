"""
Veneer Sheet Generator for FreeCAD (2026 Edition)
==================================================
Takes a 3D solid (painting box, arbitrary shape), generates flat veneer
sheets for every face, flattens them, applies laser kerf compensation,
handles corner overlaps, and exports to SVG.

Workflow:
  1. Select a solid in FreeCAD
  2. Run this script
  3. Enter veneer thickness, kerf width, corner overlap
  4. Gets a flat 2D layout + SVG export with laser-ready cut lines

Each face produces a sheet named: <body>_<face>_<thickness>
Faces are identified by their outward normal direction (Top, Front, etc.)
"""

import FreeCAD
import Part
import math
from typing import List, Optional, Tuple, Dict, Any, NamedTuple

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

# ===========================================================================
# Configuration
# ===========================================================================
GEOM_EPS = 1e-6
SVG_FONT_SIZE = 3.0  # mm
SVG_LINE_WIDTH = 0.15  # mm
SVG_CUT_WIDTH = 0.25  # mm
LAYOUT_MARGIN = 10.0  # mm around pieces
LABEL_OFFSET = 4.0  # mm label above cut line

# ===========================================================================
# Data Structures
# ===========================================================================
class VeneerSheet(NamedTuple):
    """A flattened veneer piece ready for laser cutting."""
    name: str                    # e.g. "Box_Front_0.6"
    face_label: str              # human readable: "Front", "Bottom"
    thickness: float             # veneer thickness in mm
    outer_wire: Part.Wire        # cut line (with kerf)
    inner_wire: Part.Wire        # face boundary (reference)
    overlap_wire: Part.Wire      # overlap region indicator
    area: float                  # mm² of cut area
    placement: FreeCAD.Placement # position on layout sheet


# ===========================================================================
# Geometry Engine
# ===========================================================================

class VeneerProcessor:
    """Generate flat veneer sheets from a 3D solid's faces."""

    def __init__(self, veneer_thickness: float, kerf: float,
                 corner_overlap: float = 1.0):
        self.thickness = veneer_thickness
        self.kerf = kerf
        self.corner_overlap = corner_overlap

    def process_solid(self, solid: Part.Solid, body_name: str) -> List[VeneerSheet]:
        """Extract a veneer sheet for each face of the solid."""
        sheets: List[VeneerSheet] = []

        for i, face in enumerate(solid.Faces):
            face_label = self._identify_face(face, i)
            sheet = self._make_sheet(face, face_label, body_name)
            if sheet:
                sheets.append(sheet)

        return sheets

    def _identify_face(self, face: Part.Face, idx: int) -> str:
        """Label a face by its dominant normal direction."""
        normal = face.normalAt(0, 0)
        bbox = face.BoundBox

        # Dominant plane
        extents = [bbox.XLength, bbox.YLength, bbox.ZLength]
        min_extent = min(extents)
        axis = extents.index(min_extent)  # which axis is the normal

        labels = ["Left/Right", "Front/Back", "Top/Bottom"]
        directions = ["Left" if normal.x < 0 else "Right",
                      "Back" if normal.y < 0 else "Front",
                      "Bottom" if normal.z < 0 else "Top"]

        # Check if it's a clearly-aligned face
        if abs(normal[axis]) > 0.8:
            return directions[axis]

        # For angled faces, use index
        return f"Face_{idx + 1}"

    def _make_sheet(self, face: Part.Face, face_label: str,
                    body_name: str) -> Optional[VeneerSheet]:
        """Create a flat 2D veneer sheet from a 3D face."""
        # Project face to XY plane
        flat_face = self._project_to_xy(face)
        if not flat_face:
            return None

        # Get the outer wire of the flat face
        outer_boundary = flat_face.OuterWire
        if not outer_boundary:
            return None

        # Face dimensions (mm)
        bbox = outer_boundary.BoundBox
        face_w = bbox.XLength
        face_h = bbox.YLength

        # === Geometry: face → flat veneer sheet ===
        #
        # Face boundary: the actual face outline on the 3D solid
        # Wrap margin: how far the veneer extends past the face to cover edges
        #   = thickness + corner_overlap (so adjacent pieces overlap nicely)
        # Kerf compensation: cut line is offset outward by kerf/2 so pieces
        #   are slightly oversized and fit snugly after laser removes material
        #
        # Corner treatment: we cut each edge with a small miter/overlap so
        #   the veneer pieces interlock cleanly.

        wrap_margin = self.thickness + self.corner_overlap
        kerf_half = self.kerf / 2.0
        cut_offset = wrap_margin + kerf_half

        # Cut line (red in SVG): the laser follows this
        cut_wire_list = self._offset_wire(outer_boundary, cut_offset)
        if not cut_wire_list:
            return None
        cut_wire = max(cut_wire_list, key=lambda w: abs(w.Area))

        # Face boundary (blue in SVG): where the face actually ends
        ref_wire = outer_boundary.copy()

        # Wrap line (green in SVG): where veneer bends around the edge
        wrap_wire_list = self._offset_wire(outer_boundary, wrap_margin)
        wrap_wire = wrap_wire_list[0] if wrap_wire_list else cut_wire

        # Center the piece at origin for clean layout placement
        cut_bb = cut_wire.BoundBox
        center = FreeCAD.Vector(
            (cut_bb.XMin + cut_bb.XMax) / 2.0,
            (cut_bb.YMin + cut_bb.YMax) / 2.0,
            0
        )

        cut_wire = cut_wire.copy(); cut_wire.translate(-center)
        ref_wire = ref_wire.copy(); ref_wire.translate(-center)
        wrap_wire = wrap_wire.copy(); wrap_wire.translate(-center)

        name = f"{body_name}_{face_label}_{self.thickness}"

        return VeneerSheet(
            name=name,
            face_label=face_label,
            thickness=self.thickness,
            outer_wire=cut_wire,
            inner_wire=ref_wire,
            overlap_wire=overlap_wire,
            area=abs(cut_wire.Area),
            placement=FreeCAD.Placement()
        )

    def _project_to_xy(self, face: Part.Face) -> Optional[Part.Face]:
        """Project a 3D face to the XY plane."""
        normal = face.normalAt(0, 0)

        # Already in XY plane?
        if abs(normal.z - 1.0) < GEOM_EPS or abs(normal.z + 1.0) < GEOM_EPS:
            projected = face.copy()
            if abs(normal.z + 1.0) < GEOM_EPS:
                # Flip to make normal +Z
                projected.transformShape(
                    FreeCAD.Placement(
                        FreeCAD.Vector(),
                        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)
                    ).toMatrix()
                )
            return projected

        # Find rotation to align normal with Z
        target = FreeCAD.Vector(0, 0, 1)
        rot_axis = normal.cross(target)
        if rot_axis.Length < GEOM_EPS:
            return None
        rot_axis.normalize()
        angle = math.degrees(math.acos(max(-1, min(1, normal.dot(target)))))

        projected = face.copy()
        projected.transformShape(
            FreeCAD.Placement(
                FreeCAD.Vector(),
                FreeCAD.Rotation(rot_axis, angle)
            ).toMatrix()
        )

        return projected

    def _offset_wire(self, wire: Part.Wire, distance: float) -> List[Part.Wire]:
        """Offset a 2D wire outward by distance, handling corners nicely.

        Tries multiple offset strategies for compatibility across FreeCAD versions.
        Uses arc joins to prevent laser-tip burn at sharp outer corners.
        """
        strategies = [
            # FreeCAD >= 1.0 with offset2D
            lambda: wire.offset2D(distance, 0.01, mode="normal", join="arc"),
            # offset2D with fillet parameter
            lambda: wire.offset2D(distance, 0.01, mode="normal", join="round", fillet=0.5),
            # Legacy Part.Wire.offset (returns list of wires)
            lambda: wire.offset(distance, 0.01, join="arc"),
            # Legacy without join param
            lambda: wire.offset(distance, 0.01),
        ]
        for strategy in strategies:
            try:
                result = strategy()
                if result is None:
                    continue
                if isinstance(result, list) and result:
                    return result
                if hasattr(result, 'Edges'):
                    return [result]
            except (AttributeError, TypeError):
                continue
            except Exception:
                continue
        return []


# ===========================================================================
# Layout Engine
# ===========================================================================

class SheetLayout:
    """Arrange veneer sheets on a flat cutting sheet."""

    def __init__(self, sheets: List[VeneerSheet], margin: float = LAYOUT_MARGIN):
        self.sheets = sheets
        self.margin = margin
        self.sheet_width = 0.0
        self.sheet_height = 0.0

    def arrange(self, max_width: float = 800.0) -> Tuple[float, float]:
        """Pack sheets into rows. Returns (width, height) of layout."""
        # Sort by height (tallest first) for better packing
        sorted_sheets = sorted(
            enumerate(self.sheets),
            key=lambda x: x[1].outer_wire.BoundBox.YLength,
            reverse=True
        )

        cursor_x = 0.0
        cursor_y = 0.0
        row_height = 0.0
        max_x = 0.0

        for idx, sheet in sorted_sheets:
            bb = sheet.outer_wire.BoundBox
            piece_w = bb.XLength + 2 * self.margin
            piece_h = bb.YLength + 2 * self.margin

            # New row?
            if cursor_x + piece_w > max_width and cursor_x > 0:
                cursor_x = 0.0
                cursor_y += row_height + self.margin
                row_height = 0.0

            # Place piece (centered in its slot)
            bb_center = FreeCAD.Vector(
                (bb.XMin + bb.XMax) / 2,
                (bb.YMin + bb.YMax) / 2,
                0
            )
            place_x = cursor_x + self.margin - bb.XMin - bb_center.x
            place_y = cursor_y + self.margin - bb.YMin - bb_center.y

            placement = FreeCAD.Placement(
                FreeCAD.Vector(place_x, place_y, 0)
            )

            # Update sheet with placement
            self.sheets[idx] = sheet._replace(placement=placement)

            cursor_x += piece_w
            row_height = max(row_height, piece_h)
            max_x = max(max_x, cursor_x)

        self.sheet_width = max_x
        self.sheet_height = cursor_y + row_height

        return self.sheet_width, self.sheet_height


# ===========================================================================
# SVG Export
# ===========================================================================

class SvgExporter:
    """Export veneer layout to SVG with laser-ready layers."""

    def __init__(self, output_path: str):
        self.output_path = output_path
        self._elements: List[str] = []

    def export(self, sheets: List[VeneerSheet], width: float, height: float):
        """Generate the complete SVG."""
        svg_header = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{width:.1f}mm" height="{height:.1f}mm"
     viewBox="0 0 {width:.1f} {height:.1f}">
  <style>
    .cut-line {{ stroke: #e00; stroke-width: {SVG_CUT_WIDTH}mm; fill: none; stroke-linejoin: round; }}
    .face-line {{ stroke: #44f; stroke-width: {SVG_LINE_WIDTH}mm; fill: none; stroke-dasharray: 2,1; }}
    .overlap-line {{ stroke: #0a0; stroke-width: {SVG_LINE_WIDTH}mm; fill: none; opacity: 0.5; }}
    .label {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: {SVG_FONT_SIZE}mm; fill: #333; }}
    .sheet-border {{ stroke: #ccc; stroke-width: 0.1mm; fill: none; }}
  </style>
  <!-- Sheet boundary -->
  <rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" class="sheet-border"/>
  <g id="veneers">'''

        self._elements.append(svg_header)

        for sheet in sheets:
            self._add_sheet(sheet)

        self._elements.append('  </g>\n</svg>')

        with open(self.output_path, 'w') as f:
            f.write('\n'.join(self._elements))

    def _add_sheet(self, sheet: VeneerSheet):
        """Add a veneer sheet as SVG elements."""
        mat = sheet.placement.toMatrix()

        # Cut line (laser path)
        cut_path = self._wire_to_svg_path(sheet.outer_wire, mat, 'cut-line')
        ref_path = self._wire_to_svg_path(sheet.inner_wire, mat, 'face-line')

        # Label position: center of cut wire, slightly above
        bb = sheet.outer_wire.BoundBox
        center = FreeCAD.Vector(
            (bb.XMin + bb.XMax) / 2,
            (bb.YMin + bb.YMax) / 2,
            0
        )
        center = mat.multVec(center)
        label_y = center.y - LABEL_OFFSET

        label = f'''    <g id="sheet-{sheet.name}">
      {cut_path}
      {ref_path}
      <text x="{center.x:.2f}" y="{label_y:.2f}" text-anchor="middle" class="label">{sheet.name}</text>
    </g>'''

        self._elements.append(label)

    def _wire_to_svg_path(self, wire: Part.Wire, mat: FreeCAD.Matrix,
                          css_class: str) -> str:
        """Convert a FreeCAD wire to an SVG path element."""
        edges = wire.Edges
        segments = []

        for edge in edges:
            curve = edge.Curve

            if isinstance(curve, Part.Line):
                start = mat.multVec(edge.valueAt(edge.FirstParameter))
                end = mat.multVec(edge.valueAt(edge.LastParameter))
                if not segments:
                    segments.append(f'M {start.x:.3f} {start.y:.3f}')
                segments.append(f'L {end.x:.3f} {end.y:.3f}')

            elif isinstance(curve, Part.Circle):
                # Approximate arc with segments
                pts = edge.discretize(NumNodes=24)
                for pt in pts:
                    transformed = mat.multVec(pt)
                    if not segments:
                        segments.append(f'M {transformed.x:.3f} {transformed.y:.3f}')
                    else:
                        segments.append(f'L {transformed.x:.3f} {transformed.y:.3f}')

            else:
                # General curve: discretize
                pts = edge.discretize(NumNodes=20)
                for pt in pts:
                    transformed = mat.multVec(pt)
                    if not segments:
                        segments.append(f'M {transformed.x:.3f} {transformed.y:.3f}')
                    else:
                        segments.append(f'L {transformed.x:.3f} {transformed.y:.3f}')

        segments.append('Z')
        d = ' '.join(segments)
        return f'      <path d="{d}" class="{css_class}"/>'


# ===========================================================================
# FreeCAD Integration
# ===========================================================================

class VeneerOrchestrator:
    """GUI-driven veneer sheet generator."""

    def run(self):
        sel = FreeCADGui.Selection.getSelection()
        if not sel:
            QtWidgets.QMessageBox.critical(
                None, "Veneer Generator",
                "Please select a solid object first.")
            return

        # Collect solids
        solids = self._collect_solids(sel)
        if not solids:
            QtWidgets.QMessageBox.critical(
                None, "Veneer Generator",
                "No valid solids found in selection.")
            return

        # Dialog
        params = self._show_dialog()
        if not params:
            return

        veneer_thickness, kerf, corner_overlap, svg_path = params

        # Generate sheets
        processor = VeneerProcessor(veneer_thickness, kerf, corner_overlap)
        all_sheets: List[VeneerSheet] = []

        for solid_obj in solids:
            solid = solid_obj.Shape if hasattr(solid_obj, 'Shape') else solid_obj
            name = getattr(solid_obj, 'Label', 'Box')
            sheets = processor.process_solid(solid, name)
            all_sheets.extend(sheets)

        if not all_sheets:
            QtWidgets.QMessageBox.warning(
                None, "Veneer Generator",
                "No veneer sheets could be generated.")
            return

        # Layout
        layout = SheetLayout(all_sheets)
        width, height = layout.arrange()

        # Create FreeCAD object
        doc = FreeCAD.ActiveDocument
        compound = self._create_compound(all_sheets)
        layout_obj = doc.addObject(
            "Part::Feature",
            f"VeneerLayout_{veneer_thickness}mm"
        )
        layout_obj.Shape = compound

        # Export SVG
        exporter = SvgExporter(svg_path)
        exporter.export(all_sheets, width, height)

        doc.recompute()

        # Summary
        total_area = sum(s.area for s in all_sheets)
        msg = (
            f"Generated {len(all_sheets)} veneer sheets\n\n"
            f"Veneer thickness: {veneer_thickness:.2f} mm\n"
            f"Laser kerf: {kerf:.3f} mm\n"
            f"Corner overlap: {corner_overlap:.1f} mm\n\n"
            f"Sheet size: {width:.0f} × {height:.0f} mm\n"
            f"Total area: {total_area:.0f} mm²\n\n"
            f"SVG: {svg_path}"
        )
        QtWidgets.QMessageBox.information(None, "Veneer Generator", msg)

    def _collect_solids(self, objects) -> List[Any]:
        """Extract solids from selected objects."""
        solids = []
        for obj in objects:
            shape = getattr(obj, 'Shape', None)
            if not shape:
                continue
            if hasattr(shape, 'isSolid') and shape.isSolid():
                solids.append(obj)
            elif hasattr(shape, 'Solids') and shape.Solids:
                # Compound or shell: add each solid
                for i, s in enumerate(shape.Solids):
                    temp = FreeCAD.ActiveDocument.addObject(
                        "Part::Feature", f"_temp_{i}"
                    )
                    temp.Shape = s
                    solids.append(temp)
        return solids

    def _show_dialog(self) -> Optional[Tuple[float, float, float, str]]:
        """Show parameter dialog. Returns (thickness, kerf, overlap, svg_path)."""
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Veneer Sheet Generator")
        dialog.setFixedSize(350, 250)

        form = QtWidgets.QFormLayout(dialog)

        thickness_spin = QtWidgets.QDoubleSpinBox()
        thickness_spin.setRange(0.1, 5.0)
        thickness_spin.setValue(0.6)
        thickness_spin.setSuffix(" mm")
        thickness_spin.setDecimals(2)

        kerf_spin = QtWidgets.QDoubleSpinBox()
        kerf_spin.setRange(0.01, 2.0)
        kerf_spin.setValue(0.13)
        kerf_spin.setSuffix(" mm")
        kerf_spin.setDecimals(3)

        overlap_spin = QtWidgets.QDoubleSpinBox()
        overlap_spin.setRange(0.1, 10.0)
        overlap_spin.setValue(1.0)
        overlap_spin.setSuffix(" mm")
        overlap_spin.setDecimals(1)

        svg_edit = QtWidgets.QLineEdit("veneers.svg")

        form.addRow("Veneer thickness:", thickness_spin)
        form.addRow("Laser kerf:", kerf_spin)
        form.addRow("Corner overlap:", overlap_spin)
        form.addRow("SVG output:", svg_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None

        return (
            thickness_spin.value(),
            kerf_spin.value(),
            overlap_spin.value(),
            svg_edit.text()
        )

    def _create_compound(self, sheets: List[VeneerSheet]) -> Part.Compound:
        """Create a FreeCAD compound from all sheets."""
        shapes = []
        for sheet in sheets:
            face = Part.Face(sheet.outer_wire)
            face.transformShape(sheet.placement.toMatrix())
            shapes.append(face)
        return Part.Compound(shapes)


# ===========================================================================
# Main
# ===========================================================================
if __name__ == "__main__":
    VeneerOrchestrator().run()
