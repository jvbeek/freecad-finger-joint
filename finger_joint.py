"""
Finger Joint Generator for FreeCAD
V-FINAL-MOD: High-Precision Logic with Optional Tabbing Toggle.
"""

import FreeCAD
import Part
import FreeCADGui
import math
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

# Geometric constants
FUZZY_DISTANCE = 0.01 
GEOM_EPS = 1e-7  # Tightened precision
PROJECTION_MARGIN = 2.0 
LAYOUT_GAP = 50.0        

@dataclass
class GlobalSettings:
    kerf: float
    finger_length: float

class FingerJointProcessor:
    def __init__(self, p1, p2, settings: GlobalSettings):
        self.p1, self.p2, self.settings = p1, p2, settings

    def execute(self):
        try:
            # Step 1: Detect the intersection
            common = self.p1.Shape.common(self.p2.Shape, FUZZY_DISTANCE)
        except:
            common = self.p1.Shape.common(self.p2.Shape)

        if not common or common.Volume < 1e-6:
            return

        bbox = common.BoundBox
        lengths = [bbox.XLength, bbox.YLength, bbox.ZLength]
        axis_idx = lengths.index(max(lengths))
        main_len = lengths[axis_idx]

        # Step 2: Calculate symmetrical finger count
        num_fingers = int(max(3, round(main_len / self.settings.finger_length)))
        if num_fingers % 2 == 0: num_fingers += 1
            
        segment_len = main_len / num_fingers
        half_kerf = self.settings.kerf / 2.0

        cutters_p1, cutters_p2 = [], []
        global_min = [bbox.XMin, bbox.YMin, bbox.ZMin][axis_idx]
        
        # Grid and Part parity to ensure opposite-side symmetry
        grid_parity = int(math.floor((global_min + 0.001) / segment_len)) % 2 == 0
        part_order_parity = self.p1.Label < self.p2.Label

        for i in range(num_fingers):
            start = i * segment_len
            size = segment_len
            
            # Apply kerf only if user requested it
            if self.settings.kerf > 1e-5:
                if i > 0: start += half_kerf; size -= half_kerf
                if i < num_fingers - 1: size -= half_kerf

            # Step 3: Create the cutting box
            # We strictly match the segment length on the primary axis
            box = self._make_precision_box(bbox, axis_idx, start, size)
            
            if (i % 2 == 0) == (grid_parity == part_order_parity):
                cutters_p1.append(box)
            else:
                cutters_p2.append(box)

        # Step 4: Apply Booleans
        if cutters_p1:
            comp1 = Part.Compound(cutters_p1)
            self.p1.Shape = self.p1.Shape.cut(comp1)
        if cutters_p2:
            comp2 = Part.Compound(cutters_p2)
            self.p2.Shape = self.p2.Shape.cut(comp2)

    def _make_precision_box(self, bbox, axis, start, length):
        """Creates a box that is EXACTLY the finger width with ZERO width-overhang."""
        x, y, z = bbox.XMin, bbox.YMin, bbox.ZMin
        dx, dy, dz = bbox.XLength, bbox.YLength, bbox.ZLength
        
        # We only overhang in the 'pierce' (depth) directions
        o = 0.05 
        if axis == 0: # X-Axis
            return Part.makeBox(length, dy + o*2, dz + o*2, FreeCAD.Vector(x + start, y - o, z - o))
        elif axis == 1: # Y-Axis
            return Part.makeBox(dx + o*2, length, dz + o*2, FreeCAD.Vector(x - o, y + start, z - o))
        else: # Z-Axis
            return Part.makeBox(dx + o*2, dy + o*2, length, FreeCAD.Vector(x - o, y - o, z + start))

class LayoutOrchestrator:
    def __init__(self, container, parts):
        self.container, self.parts, self.doc = container, parts, container.Document

    def generate(self):
        groups = {}
        overall_bb = FreeCAD.BoundBox()
        for p in self.parts:
            bb = p.Shape.BoundBox
            t = round(min(bb.XLength, bb.YLength, bb.ZLength), 2)
            groups.setdefault(t, []).append(p)
            overall_bb.add(bb)

        curr_y, start_x = overall_bb.YMin, overall_bb.XMax + LAYOUT_GAP
        for t in sorted(groups.keys()):
            projections = []
            for p in groups[t]:
                face = max(p.Shape.Faces, key=lambda f: f.Area)
                norm = face.normalAt(0.5, 0.5)
                # Ensure we project to a flat XY plane
                rot = FreeCAD.Rotation(norm, FreeCAD.Vector(0, 0, 1))
                flat = face.copy()
                flat.transformShape(p.Placement.toMatrix())
                flat.transformShape(FreeCAD.Placement(FreeCAD.Vector(), rot).toMatrix())
                fbb = flat.BoundBox
                flat.translate(FreeCAD.Vector(-fbb.XMin, -fbb.YMin, -fbb.ZMin))
                projections.append({'shape': flat, 'w': flat.BoundBox.XLength, 'h': flat.BoundBox.YLength})

            # Layout packing logic
            projections.sort(key=lambda x: x['h'], reverse=True)
            cx, cy, mh, sw = 0.0, 0.0, 0.0, math.sqrt(sum(p['w']*p['h'] for p in projections)) * 1.5
            placed = []
            for p in projections:
                if cx + p['w'] > sw: cx = 0; cy += mh + PROJECTION_MARGIN; mh = 0
                sh = p['shape'].copy(); sh.translate(FreeCAD.Vector(cx, cy, 0)); placed.append(sh)
                cx += p['w'] + PROJECTION_MARGIN; mh = max(mh, p['h'])

            lo = self.doc.addObject("Part::Feature", f"Layout_{t}mm")
            lo.Shape = Part.Compound(placed)
            lo.Placement.Base = FreeCAD.Vector(start_x, curr_y, 0)
            self.container.addObject(lo)
            curr_y += lo.Shape.BoundBox.YLength + LAYOUT_GAP

class Orchestrator:
    def run(self):
        sel = FreeCADGui.Selection.getSelection()
        if not sel or sel[0].TypeId not in ["App::Part", "Part::Part"]:
            print("Select an App::Part container.")
            return
        
        container = sel[0]
        doc = container.Document

        # Prompt to see if we should skip tabbing
        reply = QtWidgets.QMessageBox.question(None, "Finger Joint Generator", 
                                             "Apply Finger Joints (Tabbing)?\n\nSelect 'No' to just flatten parts for SVG.",
                                             QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
        
        if reply == QtWidgets.QMessageBox.Cancel: return
        apply_tabs = (reply == QtWidgets.QMessageBox.Yes)

        val, kerf = 30.0, 0.0
        if apply_tabs:
            val, ok = QtWidgets.QInputDialog().getDouble(None, "Joints", "Tab Width (mm):", 30.0, 2.0, 500.0, 2)
            if not ok: return
            kerf, ok = QtWidgets.QInputDialog().getDouble(None, "Joints", "Laser Kerf (mm):", 0.0, 0.0, 2.0, 3)
            if not ok: return
        
        # Create processed folder
        label_suffix = "Jointed" if apply_tabs else "Flattened"
        new_folder = doc.addObject("App::Part", f"{container.Label}_{label_suffix}")
        clones = []
        for obj in container.Group:
            if hasattr(obj, "Shape") and obj.ViewObject.Visibility:
                c = doc.addObject("Part::Feature", obj.Label + "_Final")
                c.Shape, c.Placement = obj.Shape.copy(), obj.Placement
                new_folder.addObject(c); clones.append(c)
        
        container.ViewObject.Visibility = False 
        
        # Run Joint Cutting only if requested
        if apply_tabs:
            for i in range(len(clones)):
                for j in range(i + 1, len(clones)):
                    FingerJointProcessor(clones[i], clones[j], GlobalSettings(kerf, val)).execute()
        
        # Run 2D Layout (Always)
        LayoutOrchestrator(new_folder, clones).generate()
        doc.recompute()

if __name__ == "__main__": 
    Orchestrator().run()