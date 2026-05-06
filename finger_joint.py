"""
Finger Joint Generator for FreeCAD (2026 Edition)
Final Version: Global Grid Alignment & Part Parity Lock for Perfect Symmetry
"""

import FreeCAD
import Part
import FreeCADGui
import math
import re
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

# =============================================================================
# Configuration
# =============================================================================
FUZZY_DISTANCE = 0.05 
CUTTER_OVERHANG = 0.2 
GEOM_EPS = 1e-6
PROJECTION_MARGIN = 2.0 
LAYOUT_GAP = 50.0        

@dataclass
class GlobalSettings:
    kerf: float
    finger_length: float

# =============================================================================
# Geometry Engine
# =============================================================================

class FingerJointProcessor:
    def __init__(self, p1, p2, settings: GlobalSettings):
        self.p1 = p1
        self.p2 = p2
        self.settings = settings

    def execute(self):
        try:
            common = self.p1.Shape.common(self.p2.Shape, FUZZY_DISTANCE)
        except:
            common = self.p1.Shape.common(self.p2.Shape)

        if not common or common.Volume < GEOM_EPS:
            return

        bbox = common.BoundBox
        lengths = [bbox.XLength, bbox.YLength, bbox.ZLength]
        axis_idx = lengths.index(max(lengths))
        main_len = lengths[axis_idx]

        num_fingers = int(max(3, round(main_len / self.settings.finger_length)))
        if num_fingers % 2 == 0:
            num_fingers += 1
            
        segment_len = main_len / num_fingers
        half_kerf = self.settings.kerf / 2.0

        cutters_p1 = []
        cutters_p2 = []

        # SYMMETRY LOCK: 
        # 1. Start on a fixed global grid (multiple of segment_len)
        global_min = [bbox.XMin, bbox.YMin, bbox.ZMin][axis_idx]
        grid_parity = int(math.floor((global_min + GEOM_EPS) / segment_len)) % 2 == 0
        
        # 2. Determine which part "wins" index 0 based on a stable ID (Label)
        # This ensures that even if part order is swapped, the same part gets the slot.
        p1_id = self.p1.Label
        p2_id = self.p2.Label
        part_order_parity = p1_id < p2_id

        for i in range(num_fingers):
            start = i * segment_len
            size = segment_len
            
            if i > 0: 
                start += half_kerf
                size -= half_kerf
            if i < num_fingers - 1:
                size -= half_kerf

            box = self._make_overhang_box(bbox, axis_idx, start, size)
            
            # Combine grid parity and part identity for a deterministic result
            if (i % 2 == 0) == (grid_parity == part_order_parity):
                cutters_p1.append(box)
            else:
                cutters_p2.append(box)

        if cutters_p1:
            self.p1.Shape = self.p1.Shape.cut(Part.Compound(cutters_p1))
        if cutters_p2:
            self.p2.Shape = self.p2.Shape.cut(Part.Compound(cutters_p2))

    def _make_overhang_box(self, bbox, axis, start, length):
        x, y, z = bbox.XMin, bbox.YMin, bbox.ZMin
        dx, dy, dz = bbox.XLength, bbox.YLength, bbox.ZLength
        o = CUTTER_OVERHANG
        if axis == 0:
            return Part.makeBox(length, dy+o*2, dz+o*2, FreeCAD.Vector(x+start, y-o, z-o))
        elif axis == 1:
            return Part.makeBox(dx+o*2, length, dz+o*2, FreeCAD.Vector(x-o, y+start, z-o))
        else:
            return Part.makeBox(dx+o*2, dy+o*2, length, FreeCAD.Vector(x-o, y-o, z+start))

# =============================================================================
# Layout Engine
# =============================================================================

class LayoutOrchestrator:
    def __init__(self, container, parts: List[Any]):
        self.container = container
        self.parts = parts
        self.doc = container.Document

    def generate(self):
        groups: Dict[float, List[Any]] = {}
        overall_bb = FreeCAD.BoundBox()
        for p in self.parts:
            bb = p.Shape.BoundBox
            thickness = round(min(bb.XLength, bb.YLength, bb.ZLength), 2)
            groups.setdefault(thickness, []).append(p)
            overall_bb.add(bb)

        current_y = overall_bb.YMin
        start_x = overall_bb.XMax + LAYOUT_GAP

        for thickness in sorted(groups.keys()):
            h_used = self._build_sheet(thickness, groups[thickness], start_x, current_y)
            current_y += h_used + LAYOUT_GAP

    def _build_sheet(self, thickness, parts, x_offset, y_offset) -> float:
        projections = []
        for p in parts:
            face = max(p.Shape.Faces, key=lambda f: f.Area)
            norm = face.normalAt(0.5, 0.5)
            rot = FreeCAD.Rotation(norm, FreeCAD.Vector(0, 0, 1))
            flat_face = face.copy()
            flat_face.transformShape(p.Placement.toMatrix())
            flat_face.transformShape(FreeCAD.Placement(FreeCAD.Vector(), rot).toMatrix())
            fbb = flat_face.BoundBox
            flat_face.translate(FreeCAD.Vector(-fbb.XMin, -fbb.YMin, -fbb.ZMin))
            projections.append({'shape': flat_face, 'w': flat_face.BoundBox.XLength, 'h': flat_face.BoundBox.YLength, 'label': p.Label})

        projections.sort(key=lambda x: x['h'], reverse=True)
        cursor_x, cursor_y, max_h = 0.0, 0.0, 0.0
        sheet_width = math.sqrt(sum(p['w']*p['h'] for p in projections)) * 1.5
        placed_shapes = []
        for p in projections:
            if cursor_x + p['w'] > sheet_width:
                cursor_x = 0; cursor_y += max_h + PROJECTION_MARGIN; max_h = 0
            shape = p['shape'].copy()
            shape.translate(FreeCAD.Vector(cursor_x, cursor_y, 0))
            placed_shapes.append(shape)
            cursor_x += p['w'] + PROJECTION_MARGIN
            max_h = max(max_h, p['h'])

        compound = Part.Compound(placed_shapes)
        layout_obj = self.doc.addObject("Part::Feature", f"Layout_{thickness}mm")
        layout_obj.Shape = compound
        layout_obj.Placement.Base = FreeCAD.Vector(x_offset, y_offset, 0)
        self.container.addObject(layout_obj)
        return compound.BoundBox.YLength

# =============================================================================
# Main
# =============================================================================

class Orchestrator:
    def run(self):
        sel = FreeCADGui.Selection.getSelection()
        if not sel or sel[0].TypeId not in ["App::Part", "Part::Part"]:
            QtWidgets.QMessageBox.critical(None, "Error", "Select a Part container.")
            return

        container = sel[0]
        doc = container.Document
        dialog = QtWidgets.QInputDialog()
        val, ok = dialog.getDouble(None, "Joints", "Tab Width (mm):", 30.0, 2.0, 500.0, 2)
        if not ok: return
        kerf, ok = dialog.getDouble(None, "Joints", "Kerf (mm):", 0.13, 0.0, 2.0, 3)
        if not ok: return
        settings = GlobalSettings(kerf=kerf, finger_length=val)
        
        new_folder = doc.addObject("App::Part", f"{container.Label}_Jointed")
        clones = []
        for obj in container.Group:
            if hasattr(obj, "Shape") and obj.ViewObject.Visibility:
                c = doc.addObject("Part::Feature", obj.Label + "_Final")
                c.Shape = obj.Shape.copy()
                c.Placement = obj.Placement
                new_folder.addObject(c)
                clones.append(c)
        
        container.ViewObject.Visibility = False 
        for i in range(len(clones)):
            for j in range(i + 1, len(clones)):
                FingerJointProcessor(clones[i], clones[j], settings).execute()
        
        LayoutOrchestrator(new_folder, clones).generate()
        doc.recompute()

if __name__ == "__main__":
    Orchestrator().run()

