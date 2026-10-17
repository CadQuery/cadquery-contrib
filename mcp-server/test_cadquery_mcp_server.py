"""
Tests for the CadQuery MCP server and CAD operations.

These tests verify that:
- The core module executes CadQuery scripts correctly
- SVG rendering works correctly (headless)
- Geometry inspection returns correct values
- Parameter extraction works
- Export functionality works
- Error handling is correct
- Multi-view rendering works
- The MCP server dispatches to core correctly

Run with: pytest test_cadquery_mcp_server.py -v
"""

import pytest
import asyncio
import base64
import tempfile
import os
from types import SimpleNamespace


# ============================================================================
# CAD operation tests
# ============================================================================

class TestCore:
    """Test CAD operations independently of MCP responses."""

    def test_import(self):
        """Test that the core module can be imported."""
        import cadquery_core
        assert cadquery_core.VIEWS is not None
        assert len(cadquery_core.VIEWS) == 8

    def test_render_simple_box(self):
        """Test SVG rendering of a simple box."""
        from cadquery_core import handle_render

        result = handle_render(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)"
        )

        assert result.error is None
        assert len(result.images) == 1
        assert result.mime_type == "image/svg+xml"
        assert b"<svg" in result.images[0]
        assert b"</svg>" in result.images[0]
        assert b"<path" in result.images[0]

    def test_render_with_show_object(self):
        """Test SVG rendering using show_object() instead of result variable."""
        from cadquery_core import handle_render

        code = "import cadquery as cq\nbox = cq.Workplane('XY').box(5, 5, 5)\nshow_object(box)"
        result = handle_render(code)

        assert result.error is None
        assert len(result.images) == 1
        assert b"<svg" in result.images[0]

    def test_render_no_shape_error(self):
        """Test that render returns an error when no shape is produced."""
        from cadquery_core import handle_render

        result = handle_render("x = 1 + 1")
        assert result.error is not None
        assert "No shape produced" in result.error

    def test_render_syntax_error(self):
        """Test that render handles syntax errors gracefully."""
        from cadquery_core import handle_render

        result = handle_render("this is not valid python!!!")
        assert result.error is not None
        assert "Syntax error" in result.error

    def test_render_execution_error(self):
        """Test that render handles execution errors gracefully."""
        from cadquery_core import handle_render

        result = handle_render("raise ValueError('test error')")
        assert result.error is not None
        assert "Execution error" in result.error

    def test_render_front_view(self):
        """Test rendering from front view."""
        from cadquery_core import handle_render

        result = handle_render(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
            view="front",
        )
        assert result.error is None
        assert len(result.images) == 1
        assert result.view_names == ["front"]

    def test_render_all_views(self):
        """Test that all standard views render successfully."""
        from cadquery_core import handle_render, VIEWS

        code = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)"
        for view_name in VIEWS.keys():
            result = handle_render(code, view=view_name)
            assert result.error is None, f"View '{view_name}' failed: {result.error}"
            assert b"<svg" in result.images[0]

    def test_render_multi_view(self):
        """Test that multi_view returns 4 SVGs."""
        from cadquery_core import handle_render

        result = handle_render(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            multi_view=True,
        )

        assert result.error is None
        assert len(result.images) == 4
        assert len(result.view_names) == 4
        assert "isometric" in result.view_names
        assert "front" in result.view_names
        for svg in result.images:
            assert b"<svg" in svg

    def test_render_dimensions(self):
        """Test that width/height parameters are accepted."""
        from cadquery_core import handle_render

        result = handle_render(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
            width=400,
            height=300,
        )
        assert result.error is None
        assert b"<svg" in result.images[0]

    def test_render_show_hidden(self):
        """Test that show_hidden option affects output."""
        from cadquery_core import handle_render

        code = "import cadquery as cq\nresult = cq.Workplane('XY').box(20, 20, 10).faces('>Z').workplane().hole(5)"

        result_with = handle_render(code, show_hidden=True)
        result_without = handle_render(code, show_hidden=False)

        assert result_with.error is None
        assert result_without.error is None
        # SVG with hidden lines should have more content
        assert len(result_with.images[0]) > len(result_without.images[0])

    def test_render_empty_code(self):
        """Test handling of empty code."""
        from cadquery_core import handle_render

        result = handle_render("")
        assert result.error is not None
        assert "No shape produced" in result.error

    def test_render_whitespace_code(self):
        """Test handling of whitespace-only code."""
        from cadquery_core import handle_render

        result = handle_render("   \n\n   ")
        assert result.error is not None
        assert "No shape produced" in result.error

    def test_inspect_box(self):
        """Test geometry inspection of a simple box."""
        from cadquery_core import handle_inspect

        result = handle_inspect(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)"
        )

        assert result.error is None
        assert "Bounding Box" in result.text
        assert "10.0000" in result.text
        assert "20.0000" in result.text
        assert "30.0000" in result.text
        assert "Volume" in result.text
        assert "6000" in result.text

    def test_inspect_topology(self):
        """Test that topology information is returned."""
        from cadquery_core import handle_inspect

        result = handle_inspect(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)"
        )

        assert "Topology" in result.text
        assert "Solids: 1" in result.text
        assert "Faces: 6" in result.text
        assert "Edges: 12" in result.text
        assert "Vertices: 8" in result.text

    def test_inspect_with_show_object(self):
        """Test inspect works with show_object() syntax."""
        from cadquery_core import handle_inspect

        code = "import cadquery as cq\nbox = cq.Workplane('XY').box(5, 10, 15)\nshow_object(box)"
        result = handle_inspect(code)

        assert result.error is None
        assert "5.0000" in result.text
        assert "10.0000" in result.text
        assert "15.0000" in result.text

    def test_get_parameters(self):
        """Test that get_parameters extracts script parameters."""
        from cadquery_core import handle_get_parameters

        code = 'height = 10.0\nwidth = 20.0\nname = "test"\nenabled = True\n\nimport cadquery as cq\nresult = cq.Workplane(\'XY\').box(width, height, 5)'
        result = handle_get_parameters(code)

        assert result.error is None
        assert "height" in result.text
        assert "width" in result.text
        assert "name" in result.text
        assert "enabled" in result.text
        assert "10.0" in result.text
        assert "20.0" in result.text

    def test_get_parameters_none(self):
        """Test get_parameters when no parameters are found."""
        from cadquery_core import handle_get_parameters

        result = handle_get_parameters(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 2, 3)"
        )

        assert result.error is None
        assert "No parameters found" in result.text

    def test_export_step(self):
        """Test STEP export functionality."""
        from cadquery_core import handle_export

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            filename = f.name

        try:
            result = handle_export(
                "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
                filename,
            )

            assert result.error is None
            assert result.filename == filename
            assert os.path.exists(filename)
            assert os.path.getsize(filename) > 0
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_export_stl(self):
        """Test STL export functionality."""
        from cadquery_core import handle_export

        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            filename = f.name

        try:
            result = handle_export(
                "import cadquery as cq\nresult = cq.Workplane('XY').box(5, 5, 5)",
                filename,
            )

            assert result.error is None
            assert os.path.exists(filename)
            assert os.path.getsize(filename) > 0
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_export_no_shape(self):
        """Test that export returns an error when no shape is produced."""
        from cadquery_core import handle_export

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            filename = f.name

        try:
            result = handle_export("x = 1", filename)
            assert result.error is not None
            assert "No shape produced" in result.error
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_views_dictionary(self):
        """Test that VIEWS dictionary is properly defined."""
        from cadquery_core import VIEWS

        expected = ["isometric", "front", "back", "top", "bottom", "left", "right", "isometric_back"]
        for view in expected:
            assert view in VIEWS
            assert len(VIEWS[view]) == 3

    def test_complex_model_render(self):
        """Test rendering a more complex model."""
        from cadquery_core import handle_render

        code = """
import cadquery as cq
result = (
    cq.Workplane('XY')
    .box(20, 20, 10)
    .faces('>Z')
    .workplane()
    .hole(5)
)
"""
        result = handle_render(code)
        assert result.error is None
        assert b"<svg" in result.images[0]


# ============================================================================
# MCP server tests
# ============================================================================

class TestMCPServer:
    """Test the MCP server wrapper layer."""

    def test_import(self):
        """Test that the MCP server module can be imported."""
        import cadquery_mcp_server
        assert cadquery_mcp_server.server is not None

    def test_list_tools(self):
        """Test that list_tools returns the expected tools."""
        from cadquery_mcp_server import list_tools

        tools = asyncio.run(list_tools())
        tool_names = [t.name for t in tools]

        assert "render" in tool_names
        assert "inspect" in tool_names
        assert "get_parameters" in tool_names
        assert "export" in tool_names

    def test_render_returns_image_content(self):
        """Test that MCP render returns ImageContent with base64 SVG."""
        from cadquery_mcp_server import _render_tool

        result = asyncio.run(_render_tool({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
            "image_format": "svg",
        }))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/svg+xml"

        svg_content = base64.b64decode(result[0].data).decode("utf-8")
        assert "<svg" in svg_content

    def test_render_error_returns_text_content(self):
        """Test that MCP render errors return TextContent."""
        from cadquery_mcp_server import _render_tool

        result = asyncio.run(_render_tool({"code": "x = 1"}))
        assert result.isError is True
        assert result.content[0].type == "text"
        assert "No shape produced" in result.content[0].text

    def test_multi_view_returns_multiple_images(self):
        """Test that multi_view returns text + 4 images."""
        from cadquery_mcp_server import _render_tool

        result = asyncio.run(_render_tool({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            "multi_view": True,
            "image_format": "svg",
        }))

        assert len(result) == 5
        assert result[0].type == "text"
        assert "4 views" in result[0].text
        for i in range(1, 5):
            assert result[i].type == "image"
            assert result[i].mimeType == "image/svg+xml"

    def test_inspect_returns_text_content(self):
        """Test that MCP inspect returns TextContent."""
        from cadquery_mcp_server import _inspect_tool

        result = asyncio.run(_inspect_tool({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        }))

        assert result[0].type == "text"
        assert "Bounding Box" in result[0].text

    def test_call_tool_dispatch(self):
        """Test that call_tool correctly dispatches to handlers."""
        from cadquery_mcp_server import call_tool

        # render
        result = asyncio.run(call_tool("render", {
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
            "image_format": "svg",
        }))
        assert result[0].type == "image"

        # inspect
        result = asyncio.run(call_tool("inspect", {
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        }))
        assert "Bounding Box" in result[0].text

        # unknown
        result = asyncio.run(call_tool("unknown_tool", {}))
        assert result.isError is True
        assert "Unknown tool" in result.content[0].text


@pytest.mark.parametrize("image_format", ["svg", "png"])
@pytest.mark.parametrize("multi_view", [False, True])
def test_renderer_failure_is_a_cad_error(monkeypatch, image_format, multi_view):
    import cadquery_core as core
    from cadquery_mcp_server import _render_tool

    def render(shape, view, *args):
        if not multi_view or view == "front":
            raise RuntimeError("renderer failed")
        return b"partial PNG" if image_format == "png" else "partial SVG"

    monkeypatch.setattr(core, f"render_{image_format}", render)
    arguments = {
        "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        "image_format": image_format,
        "multi_view": multi_view,
    }
    result = core.handle_render(**arguments)
    assert result.error == "Render error: RuntimeError: renderer failed"
    assert result.images == []
    assert result.mime_type == ""
    assert result.view_names == []

    # Call the adapter directly: the dispatcher must not be needed to catch this.
    response = asyncio.run(_render_tool(arguments))
    assert response.isError is True
    assert response.content[0].text == result.error


@pytest.mark.parametrize("name", ["render", "inspect", "get_parameters", "export"])
def test_parser_failure_stays_in_cad_layer(monkeypatch, tmp_path, name):
    import cadquery_core as core
    import cadquery_mcp_server as server

    def parse(code):
        raise RuntimeError("parser failed")

    monkeypatch.setattr(core.cqgi, "parse", parse)
    arguments = {"code": "unused"}
    if name == "export":
        arguments["filename"] = str(tmp_path / "unused.step")
    result = getattr(core, f"handle_{name}")(**arguments)
    assert "RuntimeError: parser failed" in result.error
    response = asyncio.run(getattr(server, f"_{name}_tool")(arguments))
    assert response.isError is True
    assert response.content[0].text == result.error
    assert list(tmp_path.iterdir()) == []


def test_inspection_formatting_failure_stays_in_cad_layer(monkeypatch):
    import cadquery_core as core
    from cadquery_mcp_server import _inspect_tool

    # BoundingBox succeeds, but its result cannot be formatted.
    shape = SimpleNamespace(BoundingBox=lambda: object())
    monkeypatch.setattr(core, "_execute_code", lambda code: (shape, None))
    result = core.handle_inspect("unused")
    assert result.error.startswith("Inspect error: AttributeError:")
    response = asyncio.run(_inspect_tool({"code": "unused"}))
    assert response.isError is True
    assert response.content[0].text == result.error


def test_parameter_formatting_failure_stays_in_cad_layer(monkeypatch):
    import cadquery_core as core
    from cadquery_mcp_server import _get_parameters_tool

    model = SimpleNamespace(metadata=SimpleNamespace(parameters={"broken": object()}))
    monkeypatch.setattr(core.cqgi, "parse", lambda code: model)
    result = core.handle_get_parameters("unused")
    assert result.error.startswith("Parameter error: AttributeError:")
    response = asyncio.run(_get_parameters_tool({"code": "unused"}))
    assert response.isError is True
    assert response.content[0].text == result.error


def test_inspection_omits_incomplete_topology(monkeypatch):
    import cadquery_core as core

    shape = core.cq.Workplane("XY").box(1, 1, 1).val()

    def fail_faces():
        raise RuntimeError("topology unavailable")

    monkeypatch.setattr(shape, "Faces", fail_faces)
    monkeypatch.setattr(core, "_execute_code", lambda code: (shape, None))
    result = core.handle_inspect("unused")
    assert result.error is None
    assert "Bounding Box:" in result.text
    assert "Volume:" in result.text
    assert "Topology:" not in result.text
    assert "Solids:" not in result.text
