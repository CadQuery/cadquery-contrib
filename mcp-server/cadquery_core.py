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

CAD operations for the MCP server, independent of MCP response types.
This module handles script execution via CQGI, SVG/PNG rendering, geometry inspection,
parameter extraction, and file export.
"""

import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
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
    images: list[bytes] = field(default_factory=list)
    mime_type: str = ""
    view_names: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class TextResult:
    """Result of a geometry inspection or parameter query."""
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

def _opacity(value):
    """Validate opacity before passing it to OCCT or VTK."""
    if not 0 <= value <= 1:
        raise ValueError("Opacity must be between 0 (transparent) and 1 (opaque).")
    return value


def _display_color(options) -> cq.Color | None:
    """Read CQ-editor display options, with rgba taking precedence."""
    if "rgba" in options:
        r, g, b, alpha = options["rgba"]
        options = {"color": (r, g, b), "alpha": alpha}

    color = options.get("color")
    if isinstance(color, str):
        color = cq.Color(color)
    elif color is not None and not isinstance(color, cq.Color):
        components = tuple(color)
        if len(components) not in (3, 4):
            raise ValueError("Display colors must contain RGB or RGBA components.")
        # CQ-editor selects the RGB scale from the first component's type.
        byte_rgb = isinstance(components[0], int)
        rgb = tuple(value / 255 for value in components[:3]) if byte_rgb else components[:3]
        alpha = components[3] if len(components) == 4 else 1.0
        if byte_rgb and isinstance(alpha, int):
            alpha /= 255
        color = cq.Color(*rgb, _opacity(alpha))

    if color is None and "alpha" not in options:
        return None
    r, g, b, alpha = color.toTuple() if color is not None else (0.8, 0.8, 0.8, 1.0)
    return cq.Color(r, g, b, _opacity(options.get("alpha", alpha)))


def _extract_shape(build_result):
    """Preserve all show_object outputs and their display colors."""
    displayed = build_result.results
    if len(displayed) == 1 and not displayed[0].options:
        return displayed[0].shape
    if displayed:
        assembly = cq.Assembly(name="displayed")
        for index, item in enumerate(displayed):
            opts = item.options or {}
            assembly.add(item.shape, name=f"object_{index}", color=_display_color(opts))
        return assembly
    return build_result.env.get("result")


def _to_occ_shape(shape):
    """Flatten geometry only when needed, retaining every part and location."""
    if isinstance(shape, cq.Assembly):
        return shape.toCompound()
    if isinstance(shape, cq.Workplane):
        return cq.Compound.makeCompound(
            item for item in shape.vals() if isinstance(item, cq.Shape)
        )
    return shape


def _execute_code(code: str):
    """Execute CQGI code, retaining assembly metadata and reporting CAD errors."""
    try:
        model = cqgi.parse(code)
        result = model.build()
        if result.exception:
            tb = traceback.format_exception(
                type(result.exception),
                result.exception,
                result.exception.__traceback__,
            )
            return None, f"Execution error:\n{''.join(tb)}"

        shape = _extract_shape(result)
        if shape is None:
            return None, "No shape produced. Use show_object(shape) or assign to 'result' variable."
        return shape, None
    except SyntaxError as e:
        return None, f"Syntax error: {e}"
    except Exception as e:
        return None, f"Execution error: {type(e).__name__}: {e}"


def render_svg(shape, view_name: str, width: int, height: int,
               show_hidden: bool = True) -> str:
    """Render an OCC shape to an SVG string from a specific view angle."""
    opts = {
        "width": width,
        "height": height,
        "projectionDir": VIEWS[view_name],
        "showAxes": view_name in ("isometric", "isometric_back"),
        "showHidden": show_hidden,
    }

    return getSVG(_to_occ_shape(shape), opts=opts)


def render_png(shape, view_name: str, width: int, height: int) -> bytes:
    """Render a shaded PNG offscreen, preserving assembly colors and locations."""
    from cadquery.occ_impl.assembly import toVTKAssy
    from vtkmodules.vtkRenderingCore import (
        vtkRenderer, vtkRenderWindow, vtkWindowToImageFilter,
    )
    from vtkmodules.vtkIOImage import vtkPNGWriter
    import vtkmodules.vtkRenderingOpenGL2  # noqa: F401 - registers the rendering backend

    assembly = shape if isinstance(shape, cq.Assembly) else cq.Assembly(
        shape, color=cq.Color(0.7, 0.75, 0.8)
    )
    renderer = vtkRenderer()
    renderer.SetBackground(0.95, 0.96, 0.98)
    for actor in toVTKAssy(assembly, edges=False, tolerance=0.1):
        renderer.AddActor(actor)
    window = vtkRenderWindow()
    try:
        window.SetOffScreenRendering(1)
        window.SetSize(width, height)
        window.SetMultiSamples(0)
        window.AddRenderer(renderer)
        camera = renderer.GetActiveCamera()
        camera.SetPosition(*VIEWS[view_name])
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(*((0, 1, 0) if view_name in ("top", "bottom") else (0, 0, 1)))
        camera.ParallelProjectionOn()
        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        window.Render()
        capture = vtkWindowToImageFilter()
        capture.SetInput(window)
        capture.ReadFrontBufferOff()
        capture.Update()
        writer = vtkPNGWriter()
        writer.SetWriteToMemory(True)
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()
        return bytes(memoryview(writer.GetResult()))
    finally:
        window.Finalize()


# ---------------------------------------------------------------------------
# CAD operations — return failures before MCP response handling
# ---------------------------------------------------------------------------

def handle_render(code: str, *, view: str = "isometric",
                  multi_view: bool = False, width: int = 800,
                  height: int = 600, show_hidden: bool = True,
                  image_format: str = "svg") -> RenderResult:
    """Execute CadQuery code and return SVGs or colored PNGs."""
    try:
        if image_format not in ("svg", "png"):
            return RenderResult(error="Render error: image_format must be 'svg' or 'png'.")
        if view not in VIEWS:
            return RenderResult(error=f"Render error: unknown view '{view}'.")
        # Reject boolean dimensions.
        if not all(type(size) is int and 16 <= size <= 4096 for size in (width, height)):
            return RenderResult(error="Render error: width and height must be integers from 16 to 4096.")
        shape, err = _execute_code(code)
        if err:
            return RenderResult(error=err)

        names = list(MULTI_VIEW_ANGLES) if multi_view else [view]
        if image_format == "png":
            images = [render_png(shape, name, width, height) for name in names]
            mime_type = "image/png"
        else:
            images = [
                render_svg(shape, name, width, height, show_hidden).encode("utf-8")
                for name in names
            ]
            mime_type = "image/svg+xml"
        return RenderResult(images=images, mime_type=mime_type, view_names=names)
    except Exception as e:
        return RenderResult(error=f"Render error: {type(e).__name__}: {e}")


def handle_inspect(code: str) -> TextResult:
    """Execute CadQuery code and return geometry information."""
    try:
        shape, err = _execute_code(code)
        if err:
            return TextResult(error=err)

        shape = _to_occ_shape(shape)
        bb = shape.BoundingBox()
        lines = [
            "Geometry Information:",
            "  Bounding Box:",
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
            lines.extend([
                "  Topology:",
                f"    Solids: {len(shape.Solids())}",
                f"    Faces: {len(shape.Faces())}",
                f"    Edges: {len(shape.Edges())}",
                f"    Vertices: {len(shape.Vertices())}",
            ])
        except Exception:
            pass

        return TextResult(text="\n".join(lines))
    except Exception as e:
        return TextResult(error=f"Inspect error: {type(e).__name__}: {e}")


def handle_get_parameters(code: str) -> TextResult:
    """Parse CadQuery code and extract parameters."""
    try:
        model = cqgi.parse(code)
        params = model.metadata.parameters
        if not params:
            return TextResult(text="No parameters found in the script.")

        lines = ["Parameters found:"]
        for name, param in params.items():
            type_name = param.varType.__name__ if param.varType else "unknown"
            lines.append(f"  {name}: {type_name} = {param.default_value}")
            if param.desc:
                lines.append(f"    Description: {param.desc}")
            if param.valid_values:
                lines.append(f"    Valid values: {param.valid_values}")

        return TextResult(text="\n".join(lines))
    except SyntaxError as e:
        return TextResult(error=f"Syntax error: {e}")
    except Exception as e:
        return TextResult(error=f"Parameter error: {type(e).__name__}: {e}")


def handle_export(code: str, filename: str,
                  export_format: str | None = None) -> ExportResult:
    """Export a model, replacing an existing file only after a successful write."""
    try:
        shape, err = _execute_code(code)
        if err:
            return ExportResult(error=err)

        destination = Path(filename).expanduser().absolute()
        fmt = (export_format or destination.suffix.lstrip(".")).upper()
        fmt = {"STP": "STEP"}.get(fmt, fmt)
        if not destination.parent.is_dir():
            return ExportResult(error=(
                f"Export error: parent directory '{destination.parent}' "
                "does not exist or is not a directory."
            ))
        if not fmt:
            return ExportResult(error=(
                f"Export error: cannot infer format from '{filename}'; pass format explicitly."
            ))
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}.", dir=destination.parent,
        ) as directory:
            temporary = Path(directory) / f"model.{fmt.lower()}"
            if isinstance(shape, cq.Assembly) and fmt == "STEP":
                shape.export(str(temporary), exportType=fmt)
            else:
                export(_to_occ_shape(shape), str(temporary), exportType=fmt)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("Exporter did not write a non-empty file.")
            temporary.replace(destination)
        return ExportResult(filename=str(destination))
    except Exception as e:
        return ExportResult(error=f"Export error: {type(e).__name__}: {e}")
