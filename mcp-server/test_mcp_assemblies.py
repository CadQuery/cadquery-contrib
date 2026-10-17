"""Regression tests for colored assemblies, PNG output, and MCP error flags."""

import asyncio
import base64
from datetime import timedelta
import os
from pathlib import Path
import struct
import sys

import cadquery as cq
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from cadquery_core import _execute_code, handle_export, handle_inspect, handle_render
from cadquery_mcp_server import call_tool, list_tools


ASSEMBLY_CODE = '''
import cadquery as cq
size = 10.0
result = cq.Assembly(name="color_test", loc=cq.Location((100, 0, 0)))
result.add(cq.Workplane("XY").box(size, size, size), name="red_block",
           loc=cq.Location((-15, 0, 0)), color=cq.Color("red"))
nested = cq.Assembly(name="nested", loc=cq.Location((15, 0, 0)))
nested.add(cq.Workplane("XY").box(size, size, size), name="blue_block",
           loc=cq.Location((0, 0, 5)), color=cq.Color("blue"))
result.add(nested)
'''

DISPLAYED_CODE = '''
import cadquery as cq
show_object(cq.Workplane("XY").box(10, 10, 10).translate((-15, 0, 0)),
            options={"color": "red"})
show_object(cq.Workplane("XY").box(10, 10, 10).translate((15, 0, 0)),
            options={"color": (0.0, 0.0, 1.0), "alpha": 1.0})
'''


def assert_png(data, size=(320, 240)):
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    assert struct.unpack(">II", data[16:24]) == size


def png_pixels(data, tmp_path):
    """Decode a PNG into a (rows, columns, channels) array."""
    from vtkmodules.vtkIOImage import vtkPNGReader
    from vtkmodules.util.numpy_support import vtk_to_numpy

    filename = tmp_path / "decoded.png"
    filename.write_bytes(data)
    reader = vtkPNGReader()
    reader.SetFileName(str(filename))
    reader.Update()
    width, height, _ = reader.GetOutput().GetDimensions()
    pixels = vtk_to_numpy(reader.GetOutput().GetPointData().GetScalars())
    return pixels.reshape(height, width, -1)


def assert_bounds(shape):
    bb = shape.BoundingBox()
    assert (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax) == pytest.approx(
        (80, 120, -5, 5, -5, 10), abs=1e-5,
    )
    assert len(shape.Solids()) == 2
    assert shape.Volume() == pytest.approx(2000)


def test_inspect_nested_assembly_includes_root_and_child_locations():
    result = handle_inspect(ASSEMBLY_CODE)
    assert result.error is None
    assert "X: 80.0000 to 120.0000 (size: 40.0000)" in result.text
    assert "Z: -5.0000 to 10.0000 (size: 15.0000)" in result.text
    assert "Volume: 2000.0000" in result.text
    assert "Solids: 2" in result.text


@pytest.mark.parametrize("code", [
    ASSEMBLY_CODE,
    DISPLAYED_CODE,
    DISPLAYED_CODE.replace('"red"', '(255, 0, 0)').replace('(0.0, 0.0, 1.0)', '(0, 0, 255)'),
])
def test_png_has_both_part_colors(code, tmp_path):
    result = handle_render(code, image_format="png", view="top", width=320, height=240)
    assert result.error is None, result.error
    assert result.mime_type == "image/png"
    data = result.images[0]
    assert_png(data)
    pixels = png_pixels(data, tmp_path).reshape(-1, 3)
    red = (pixels[:, 0] > 80) & (pixels[:, 0] > pixels[:, 2] * 1.5)
    blue = (pixels[:, 2] > 80) & (pixels[:, 2] > pixels[:, 0] * 1.5)
    assert red.sum() > 100
    assert blue.sum() > 100


def test_png_alpha_is_rendered_as_opacity(tmp_path):
    def center_pixel(alpha):
        code = (
            "import cadquery as cq\n"
            "show_object(cq.Workplane('XY').box(10, 10, 10),"
            f" options={{'color': (255, 0, 0), 'alpha': {alpha}}})"
        )
        result = handle_render(code, image_format="png", view="top", width=320, height=240)
        assert result.error is None, result.error
        return png_pixels(result.images[0], tmp_path)[120, 160, :3].astype(int)

    # Fully transparent shows the renderer background; fully opaque is solid red.
    assert center_pixel(0.0).tolist() == pytest.approx([242, 245, 250], abs=2)
    opaque = center_pixel(1.0)
    assert opaque[0] > 200 and opaque[1] < 10 and opaque[2] < 10
    # Higher alpha hides more background behind the red box: green falls monotonically.
    greens = [center_pixel(alpha)[1] for alpha in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert greens == sorted(greens, reverse=True)
    assert len(set(greens)) == len(greens)


def test_svg_assembly_remains_available():
    result = handle_render(ASSEMBLY_CODE, image_format="svg")
    assert result.error is None
    assert b"<svg" in result.images[0]


def test_png_multi_view():
    result = handle_render(ASSEMBLY_CODE, image_format="png", multi_view=True,
                           width=320, height=240)
    assert result.error is None, result.error
    assert result.view_names == ["isometric", "front", "top", "right"]
    assert len(result.images) == 4
    for image in result.images:
        assert_png(image)


def test_show_object_and_workplane_keep_all_shapes():
    workplane = '''import cadquery as cq
result = cq.Workplane("XY").pushPoints([(-15, 0), (15, 0)]).box(10, 10, 10)
'''
    for code in [DISPLAYED_CODE, workplane]:
        result = handle_inspect(code)
        assert result.error is None
        assert "size: 40.0000" in result.text
        assert "Solids: 2" in result.text


@pytest.mark.parametrize("extension", ["step", "stp"])
def test_step_preserves_assembly_names_colors_and_geometry(tmp_path, extension):
    filename = tmp_path / f"assembly.{extension}"
    result = handle_export(ASSEMBLY_CODE, str(filename))
    assert result.error is None, result.error
    text = filename.read_text()
    assert "DRAUGHTING_PRE_DEFINED_COLOUR('red')" in text
    assert "DRAUGHTING_PRE_DEFINED_COLOUR('blue')" in text
    assert "red_block" in text
    assert "blue_block" in text
    assert_bounds(cq.importers.importStep(str(filename)).val())


def test_stl_assembly_is_not_empty(tmp_path):
    filename = tmp_path / "assembly.stl"
    result = handle_export(ASSEMBLY_CODE, str(filename))
    assert result.error is None, result.error
    assert filename.stat().st_size > 100


@pytest.mark.parametrize("kwargs", [
    {"image_format": "jpeg"}, {"view": "unknown"}, {"width": 0},
    {"height": 4097}, {"width": True},
])
def test_bad_render_options_are_errors(kwargs):
    assert handle_render(ASSEMBLY_CODE, **kwargs).error


def test_failed_export_keeps_previous_file(tmp_path):
    filename = tmp_path / "existing.step"
    filename.write_text("previous export")
    result = handle_export(ASSEMBLY_CODE, str(filename), "INVALID")
    assert result.error
    assert filename.read_text() == "previous export"
    assert sorted(p.name for p in tmp_path.iterdir()) == [filename.name]


def test_silent_export_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(cq.Assembly, "export", lambda *args, **kwargs: None)
    filename = tmp_path / "failed.step"
    result = handle_export(ASSEMBLY_CODE, str(filename))
    assert "did not write" in result.error
    assert not filename.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name,args", [
    ("render", {"code": "x = 1"}),
    ("inspect", {"code": "result = 42"}),
    ("get_parameters", {"code": "invalid python !!!"}),
    ("export", {"code": "x = 1", "filename": "unused.step"}),
])
def test_mcp_handlers_flag_errors(name, args):
    result = asyncio.run(call_tool(name, args))
    assert result.isError is True
    assert result.content[0].type == "text"


def test_png_is_mcp_schema_default():
    tools = asyncio.run(list_tools())
    render = next(tool for tool in tools if tool.name == "render")
    assert render.inputSchema["properties"]["image_format"]["default"] == "png"


def test_stdio_round_trip_all_tools_and_error_flags(tmp_path):
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-u", str(Path(__file__).with_name("cadquery_mcp_server.py"))],
            env={**os.environ, "XDG_CACHE_HOME": str(tmp_path / "cache")},
            cwd=str(tmp_path),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write,
                                     read_timeout_seconds=timedelta(seconds=60)) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "render", "inspect", "get_parameters", "export",
                }
                inspected = await client.call_tool("inspect", {"code": ASSEMBLY_CODE})
                assert not inspected.isError
                assert "Solids: 2" in inspected.content[0].text
                params_result = await client.call_tool("get_parameters", {"code": ASSEMBLY_CODE})
                assert not params_result.isError
                assert "size:" in params_result.content[0].text
                assert "10.0" in params_result.content[0].text
                png = await client.call_tool("render", {
                    "code": ASSEMBLY_CODE, "width": 320, "height": 240,
                })
                assert not png.isError
                assert png.content[0].mimeType == "image/png"
                assert_png(base64.b64decode(png.content[0].data))
                svg = await client.call_tool("render", {
                    "code": ASSEMBLY_CODE, "image_format": "svg",
                })
                assert not svg.isError
                assert svg.content[0].mimeType == "image/svg+xml"
                filename = tmp_path / "wire.step"
                exported = await client.call_tool("export", {
                    "code": ASSEMBLY_CODE, "filename": "wire.step",
                })
                assert not exported.isError
                assert exported.content[0].text == f"Exported to: {filename}"
                assert_bounds(cq.importers.importStep(str(filename)).val())
                failed = await client.call_tool("export", {
                    "code": ASSEMBLY_CODE, "filename": str(tmp_path / "missing" / "fail.step"),
                })
                assert failed.isError is True
                assert "Export error" in failed.content[0].text
                bad_format = await client.call_tool("render", {
                    "code": ASSEMBLY_CODE, "image_format": "jpeg",
                })
                assert bad_format.isError is True
                for name in ("render", "inspect", "get_parameters", "export"):
                    invalid = await client.call_tool(name, {
                        "code": ASSEMBLY_CODE, "unexpected": True,
                        **({"filename": "rejected.step"} if name == "export" else {}),
                    })
                    assert invalid.isError is True
                    assert "unexpected" in invalid.content[0].text
                assert not (tmp_path / "rejected.step").exists()
    asyncio.run(check())


@pytest.mark.parametrize("color, expected", [
    ("(64, 164, 223)", (64 / 255, 164 / 255, 223 / 255, 1)),
    ("(0.25, 0.5, 0.75)", (0.25, 0.5, 0.75, 1)),
    ("(1.0, 0, 0)", (1, 0, 0, 1)),
    ("(0, 0, 1)", (0, 0, 1 / 255, 1)),
    ("'red'", (1, 0, 0, 1)),
    ("cq.Color(0.25, 0.5, 0.75, 0.4)", (0.25, 0.5, 0.75, 0.4)),
    ("(64, 164, 223, 0.4)", (64 / 255, 164 / 255, 223 / 255, 0.4)),
    ("(64, 164, 223, 255)", (64 / 255, 164 / 255, 223 / 255, 1)),
    ("(64, 164, 223, 128)", (64 / 255, 164 / 255, 223 / 255, 128 / 255)),
    ("(64, 164, 223, 0)", (64 / 255, 164 / 255, 223 / 255, 0)),
    ("(0.25, 0.5, 0.75, 1)", (0.25, 0.5, 0.75, 1)),
])
def test_display_colors_preserve_scale_and_opacity(color, expected):
    code = (
        "import cadquery as cq\n"
        f"show_object(cq.Workplane('XY').box(1, 1, 1), options={{'color': {color}}})"
    )
    assembly, error = _execute_code(code)
    assert error is None, error
    assert assembly.children[0].color.toTuple() == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("alpha", [0.0, 0.25, 0.5, 0.75, 1.0])
@pytest.mark.parametrize("color", [None, (64, 164, 223)])
def test_display_alpha_is_opacity(alpha, color):
    options = {"alpha": alpha}
    if color is not None:
        options["color"] = color
    code = (
        "import cadquery as cq\n"
        f"show_object(cq.Workplane('XY').box(1, 1, 1), options={options!r})"
    )
    assembly, error = _execute_code(code)
    assert error is None, error
    assert assembly.children[0].color.toTuple()[3] == pytest.approx(alpha)


@pytest.mark.parametrize("options", [
    {"color": (256, 0, 0)}, {"color": (1.1, 0.0, 0.0)},
    {"color": (1, 2)}, {"alpha": -0.1}, {"alpha": 1.1},
    {"color": (64, 164, 223, -1)}, {"color": (64, 164, 223, 256)},
    {"color": (0.25, 0.5, 0.75, -0.1)}, {"color": (0.25, 0.5, 0.75, 1.1)},
    {"rgba": (255, 0, 0, -0.1)}, {"rgba": (255, 0, 0, 255)},
])
def test_invalid_display_options_are_cad_errors(options):
    code = (
        "import cadquery as cq\n"
        f"show_object(cq.Workplane('XY').box(1, 1, 1), options={options!r})"
    )
    result = handle_render(code)
    assert result.error.startswith("Execution error:")
    assert result.images == []


def test_export_expands_tilde(tmp_path):
    filename = tmp_path / "model.step"
    # Exercise ordinary ~ expansion while keeping all output in the temporary directory.
    user_path = "~/" + os.path.relpath(filename, Path.home())
    result = handle_export(ASSEMBLY_CODE, user_path)
    assert result.error is None, result.error
    assert Path(result.filename).is_absolute()
    assert Path(result.filename).resolve() == filename.resolve()
    assert_bounds(cq.importers.importStep(result.filename).val())
    assert list(tmp_path.iterdir()) == [filename]


def test_relative_export_reports_absolute_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = handle_export(ASSEMBLY_CODE, "relative.step")
    assert result.error is None, result.error
    assert result.filename == str(tmp_path / "relative.step")
    assert_bounds(cq.importers.importStep(result.filename).val())


def test_export_replaces_destination_symlink_atomically(tmp_path):
    original = tmp_path / "original.step"
    original.write_text("original data")
    link = tmp_path / "link.step"
    link.symlink_to(original)
    result = handle_export(ASSEMBLY_CODE, str(link))
    assert result.error is None, result.error
    assert result.filename == str(link)
    assert not link.is_symlink()
    assert_bounds(cq.importers.importStep(str(link)).val())
    assert original.read_text() == "original data"


@pytest.mark.parametrize("options, expected", [
    ({"rgba": (255, 0, 0, 0.5)}, (1, 0, 0, 0.5)),
    ({"rgba": (0.25, 0.5, 0.75, 1)}, (0.25, 0.5, 0.75, 1)),
    ({"rgba": (255, 0, 0, 1)}, (1, 0, 0, 1)),
    ({"rgba": (255, 0, 0, 0)}, (1, 0, 0, 0)),
    ({"color": (0, 0, 255, 128), "alpha": 0.75}, (0, 0, 1, 0.75)),
    ({"color": "blue", "alpha": 0.1, "rgba": (255, 0, 0, 0.5)}, (1, 0, 0, 0.5)),
])
def test_display_opacity_sources_and_precedence(options, expected):
    code = (
        "import cadquery as cq\n"
        f"show_object(cq.Workplane('XY').box(1, 1, 1), options={options!r})"
    )
    assembly, error = _execute_code(code)
    assert error is None, error
    assert assembly.children[0].color.toTuple() == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("alpha", [-0.1, 1.1, float("nan"), float("inf")])
def test_existing_color_opacity_is_validated(alpha):
    from cadquery_core import _display_color

    with pytest.raises(ValueError, match="Opacity must be between"):
        _display_color({"color": cq.Color(0.2, 0.4, 0.6, alpha)})


def test_export_reports_missing_parent(tmp_path):
    parent = tmp_path / "missing"
    result = handle_export(ASSEMBLY_CODE, str(parent / "model.step"))
    assert result.error == (
        f"Export error: parent directory '{parent}' does not exist or is not a directory."
    )
    assert list(tmp_path.iterdir()) == []


def test_export_reports_parent_that_is_a_file(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("existing data")
    result = handle_export(ASSEMBLY_CODE, str(parent / "model.step"))
    assert "is not a directory" in result.error
    assert parent.read_text() == "existing data"


def test_extensionless_export_requires_explicit_format(tmp_path):
    filename = tmp_path / "noext"
    failed = handle_export(ASSEMBLY_CODE, str(filename))
    assert failed.error == (
        f"Export error: cannot infer format from '{filename}'; pass format explicitly."
    )
    assert list(tmp_path.iterdir()) == []
    exported = handle_export(ASSEMBLY_CODE, str(filename), "STEP")
    assert exported.error is None, exported.error
    assert_bounds(cq.importers.importStep(exported.filename).val())
