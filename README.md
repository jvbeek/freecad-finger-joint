# FreeCAD Finger Joint + Veneer Generator

Two FreeCAD macros for laser-cut woodworking:

1. **`finger_joint.py`** — Generates finger joints between adjacent 3D parts
2. **`veneer.py`** — Generates flat veneer sheets for every face of a solid

---

## Finger Joint Generator (`finger_joint.py`)

Generates finger joints between adjacent 3D parts in FreeCAD and produces 2D laser-cut layouts with proper kerf compensation.

### What It Does

1. Takes a Part container with adjacent solids
2. Detects contact faces and generates interlocking finger joints
3. Creates a jointed copy of each part with alternating fingers
4. Generates a flattened 2D layout grouped by material thickness, ready for laser cutting

### Features

- **Automatic finger count** — based on contact surface length and specified finger width
- **Kerf compensation** — configurable kerf value for precise laser-cut fits
- **Global grid alignment** — ensures symmetric finger placement across all parts
- **Part parity lock** — deterministic finger assignment regardless of selection order
- **2D layout generation** — automatic sheet layout grouped by thickness with margin spacing
- **Tabbing toggle** — optional: skip finger joints, just flatten for SVG export

### Requirements

- FreeCAD 0.21+ (PySide2 or PySide6)

### Installation

1. Copy `finger_joint.py` to your FreeCAD Macro directory:
   - Linux: `~/.FreeCAD/Macro/`
   - macOS: `~/Library/Preferences/FreeCAD/Macro/`
   - Windows: `%APPDATA%\FreeCAD\Macro\`
2. Restart FreeCAD
3. Run via `Macros` → `finger_joint` (or assign a toolbar button)

### Usage

1. Design your parts so adjacent faces touch (zero gap)
2. Group them inside a Part container
3. Select the Part container
4. Run the macro
5. Enter **Tab Width** (finger width in mm) and **Kerf** (laser kerf in mm)
6. A new Part folder is created with jointed parts and a 2D layout

### Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| Tab Width | 30 mm | 2–500 | Finger/joint width |
| Kerf | 0.13 mm | 0–2 | Laser cut compensation |

### Output

- **`{Original}_Jointed`** — Part container with modified parts
- **`Layout_{thickness}mm`** — 2D flattened layout for each unique material thickness

---

## Veneer Sheet Generator (`veneer.py`)

Takes a 3D solid (painting box, frame, arbitrary shape), generates flat veneer sheets for every face, and exports laser-ready SVG with kerf compensation and corner chamfering.

### What It Does

1. Select any solid in FreeCAD (box, frame, arbitrary shape)
2. Generates one flat veneer sheet per face
3. Each sheet is offset outward by `thickness + overlap + kerf/2`
4. Optional 45° corner chamfering for clean nesting of adjacent pieces
5. Flattens all sheets into a packed 2D layout
6. Exports multi-layer SVG with color-coded cut lines

### SVG Layers

| Layer | Color | Style | Purpose |
|-------|-------|-------|---------|
| Cut line | 🔴 Red | Solid | Laser follows this path |
| Face boundary | 🔵 Blue | Dashed | Original face outline |
| Wrap line | 🟢 Green | Dotted | Where veneer bends around edge |

### Naming Convention

Each sheet is named: `<body>_<face>_<thickness>`

Examples:
- `Box_Front_0.6` — Front face of "Box", 0.6mm veneer
- `Box_Top_0.6` — Top face of "Box", 0.6mm veneer
- `Frame_Face_1_1.0` — First face of "Frame", 1.0mm veneer

### Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| Veneer thickness | 0.6 mm | 0.1–5 | Sheet thickness |
| Laser kerf | 0.13 mm | 0.01–2 | Cut compensation |
| Corner overlap | 1.0 mm | 0.1–10 | Extra wrap past face edge |
| Corner chamfer | 0 mm | 0–10 | 45° notch at corners (0=off) |
| SVG output | veneers.svg | — | Output file path |

### Installation

1. Copy `veneer.py` to your FreeCAD Macro directory (same as above)
2. Restart FreeCAD
3. Run via `Macros` → `veneer`

### Usage

1. Design a solid (box, frame, any shape)
2. Select it in the 3D view
3. Run the macro
4. Enter veneer thickness, kerf, overlap, and optional chamfer
5. FreeCAD creates a `VeneerLayout_{thickness}mm` compound
6. SVG is exported to the specified path

### Geometry Details

**Cut offset** = `thickness + corner_overlap + kerf/2`

This means each veneer sheet extends past the face by the veneer thickness (to wrap around the edge), plus extra overlap (for glue margin), plus half kerf (so the laser-cut piece is slightly oversized for a snug fit).

**Corner chamfer**: When enabled, creates 45° notches at each corner of the cut outline. This allows adjacent veneer pieces to nest cleanly without double-thickness overlap at corners.

---

## License

LGPL v3 — see [LICENSE](LICENSE).
