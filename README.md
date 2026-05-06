# FreeCAD Finger Joint Generator

Generates finger joints between adjacent 3D parts in FreeCAD and produces 2D laser-cut layouts with proper kerf compensation.

## What It Does

1. Takes a Part container with adjacent solids
2. Detects contact faces and generates interlocking finger joints
3. Creates a jointed copy of each part with alternating fingers
4. Generates a flattened 2D layout grouped by material thickness, ready for laser cutting

## Features

- **Automatic finger count** — based on contact surface length and specified finger width
- **Kerf compensation** — configurable kerf value for precise laser-cut fits
- **Global grid alignment** — ensures symmetric finger placement across all parts
- **Part parity lock** — deterministic finger assignment regardless of selection order
- **2D layout generation** — automatic sheet layout grouped by thickness with margin spacing

## Requirements

- FreeCAD 0.21+ (PySide2 or PySide6)

## Installation

1. Copy `finger_joint.py` to your FreeCAD Macro directory:
   - Linux: `~/.FreeCAD/Macro/`
   - macOS: `~/Library/Preferences/FreeCAD/Macro/`
   - Windows: `%APPDATA%\FreeCAD\Macro\`
2. Restart FreeCAD
3. Run via `Macros` → `finger_joint` (or assign a toolbar button)

## Usage

1. Design your parts so adjacent faces touch (zero gap)
2. Group them inside a Part container
3. Select the Part container
4. Run the macro
5. Enter **Tab Width** (finger width in mm) and **Kerf** (laser kerf in mm)
6. A new Part folder is created with jointed parts and a 2D layout

## Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| Tab Width | 30 mm | 2–500 | Finger/joint width |
| Kerf | 0.13 mm | 0–2 | Laser cut compensation |

## Output

- **`{Original}_Jointed`** — Part container with modified parts
- **`Layout_{thickness}mm`** — 2D flattened layout for each unique material thickness

## License

LGPL v3 — see [LICENSE](LICENSE).
