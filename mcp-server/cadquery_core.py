# Copyright (c) CadQuery Development Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Core CadQuery execution and rendering logic.

Shared by both the MCP server (cadquery_mcp_server.py) and CLI (cadquery_cli.py).
This module handles script execution via CQGI, SVG rendering, geometry inspection,
parameter extraction, and file export.
"""

import traceback
from dataclasses import dataclass, field
from typing import Optional

import cadquery as cq
from cadquery import cqgi
from cadquery.occ_impl.exporters.svg import getSVG
from cadquery.occ_impl.exporters import export


# Standard view projection directions
VIEWS = {
    "isometric": (-1.75, 1.1, 5),      # Default isometric view
    "front": (0, -1, 0),                # Looking at XZ plane from -Y
    "back": (0, 1, 0),                  # Looking at XZ plane from +Y
    "top": (0, 0, 1),                   # Looking at XY plane from +Z
    "bottom": (0, 0, -1),               # Looking at XY plane from -Z
    "left": (-1, 0, 0),                 # Looking at YZ plane from -X
    "right": (1, 0, 0),                 # Looking at YZ plane from +X
    "isometric_back": (1.75, -1.1, 5),  # Isometric from opposite corner
}

MULTI_VIEW_ANGLES = ["isometric", "front", "top", "right"]


# ---------------------------------------------------------------------------
# Result types — plain data, no MCP dependencies
# ---------------------------------------------------------------------------

@dataclass
class RenderResult:
    """Result of a render operation."""
    svg_contents: list[str] = field(default_factory=list)
    view_names: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class InspectResult:
    """Result of an inspect operation."""
    text: str = ""
    error: Optional[str] = None


@dataclass
class ParamsResult:
    """Result of a get_parameters operation."""
    text: str = ""
    error: Optional[str] = None


@dataclass
class ExportResult:
    """Result of an export operation."""
    filename: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_shape(build_result, env):
    """Extract the shape from a build result or environment."""
    # First try to get from show_object() calls
    if build_result.first_result is not None:
        return build_result.first_result.shape

    # Fall back to 'result' variable in environment
    if "result" in env:
        return env["result"]

    return None


def _to_occ_shape(shape):
    """Unwrap a Workplane to its underlying OCC shape if needed."""
    if hasattr(shape, "val"):
        return shape.val()
    return shape


def _execute_code(code: str):
    """Parse and execute CadQuery code via CQGI.

    Returns (shape, error_string).  shape is the unwrapped OCC shape or None.
    """
    try:
        model = cqgi.parse(code)
    except SyntaxError as e:
        return None, f"Syntax error: {e}"

    try:
        result = model.build()
    except Exception as e:
        return None, f"Error: {type(e).__name__}: {e}"

    if result.exception:
        tb = traceback.format_exception(
            type(result.exception),
            result.exception,
            result.exception.__traceback__,
        )
        return None, f"Execution error:\n{''.join(tb)}"

    shape = _extract_shape(result, result.env)
    if shape is None:
        return None, "No shape produced. Use show_object(shape) or assign to 'result' variable."

    return _to_occ_shape(shape), None


def render_svg(shape, view_name: str, width: int, height: int,
               show_hidden: bool = True) -> str:
    """Render an OCC shape to an SVG string from a specific view angle."""
    projection_dir = VIEWS.get(view_name, VIEWS["isometric"])

    opts = {
        "width": width,
        "height": height,
        "projectionDir": projection_dir,
        "showAxes": view_name in ("isometric", "isometric_back"),
        "showHidden": show_hidden,
    }

    return getSVG(shape, opts=opts)


# ---------------------------------------------------------------------------
# Public API — used by both MCP server and CLI
# ---------------------------------------------------------------------------

def handle_render(code: str, *, view: str = "isometric",
                  multi_view: bool = False, width: int = 800,
                  height: int = 600, show_hidden: bool = True) -> RenderResult:
    """Execute CadQuery code and return rendered SVG(s)."""
    shape, err = _execute_code(code)
    if err:
        return RenderResult(error=err)

    if multi_view:
        svgs = []
        for vn in MULTI_VIEW_ANGLES:
            svgs.append(render_svg(shape, vn, width, height, show_hidden))
        return RenderResult(svg_contents=svgs, view_names=list(MULTI_VIEW_ANGLES))
    else:
        svg = render_svg(shape, view, width, height, show_hidden)
        return RenderResult(svg_contents=[svg], view_names=[view])


def handle_inspect(code: str) -> InspectResult:
    """Execute CadQuery code and return geometry information."""
    shape, err = _execute_code(code)
    if err:
        return InspectResult(error=err)

    bb = shape.BoundingBox()
    lines = [
        "Geometry Information:",
        f"  Bounding Box:",
        f"    X: {bb.xmin:.4f} to {bb.xmax:.4f} (size: {bb.xlen:.4f})",
        f"    Y: {bb.ymin:.4f} to {bb.ymax:.4f} (size: {bb.ylen:.4f})",
        f"    Z: {bb.zmin:.4f} to {bb.zmax:.4f} (size: {bb.zlen:.4f})",
    ]

    try:
        lines.append(f"  Volume: {shape.Volume():.4f}")
    except Exception:
        pass

    try:
        lines.append(f"  Surface Area: {shape.Area():.4f}")
    except Exception:
        pass

    try:
        com = shape.Center()
        lines.append(f"  Center of Mass: ({com.x:.4f}, {com.y:.4f}, {com.z:.4f})")
    except Exception:
        pass

    try:
        lines.append("  Topology:")
        lines.append(f"    Solids: {len(shape.Solids())}")
        lines.append(f"    Faces: {len(shape.Faces())}")
        lines.append(f"    Edges: {len(shape.Edges())}")
        lines.append(f"    Vertices: {len(shape.Vertices())}")
    except Exception:
        pass

    return InspectResult(text="\n".join(lines))


def handle_get_parameters(code: str) -> ParamsResult:
    """Parse CadQuery code and extract parameters."""
    try:
        model = cqgi.parse(code)
    except SyntaxError as e:
        return ParamsResult(error=f"Syntax error: {e}")
    except Exception as e:
        return ParamsResult(error=f"Error: {type(e).__name__}: {e}")

    params = model.metadata.parameters
    if not params:
        return ParamsResult(text="No parameters found in the script.")

    lines = ["Parameters found:"]
    for name, param in params.items():
        type_name = param.varType.__name__ if param.varType else "unknown"
        lines.append(f"  {name}: {type_name} = {param.default_value}")
        if param.desc:
            lines.append(f"    Description: {param.desc}")
        if param.valid_values:
            lines.append(f"    Valid values: {param.valid_values}")

    return ParamsResult(text="\n".join(lines))


def handle_export(code: str, filename: str,
                  export_format: str | None = None) -> ExportResult:
    """Execute CadQuery code and export the result to a file."""
    shape, err = _execute_code(code)
    if err:
        return ExportResult(error=err)

    try:
        export(shape, filename, exportType=export_format)
    except Exception as e:
        return ExportResult(error=f"Export error: {type(e).__name__}: {e}")

    return ExportResult(filename=filename)
