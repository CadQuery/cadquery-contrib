"""
Tests for the CadQuery MCP (Model Context Protocol) server.

These tests verify that:
- The MCP server can execute CadQuery scripts
- SVG rendering works correctly (headless)
- Geometry inspection returns correct values
- Parameter extraction works
- Export functionality works
- Error handling is correct
- Multi-view rendering works

Run with: pytest test_cadquery_mcp_server.py -v
"""

import pytest
import asyncio
import base64
import tempfile
import os

# Skip all tests in this module if mcp is not installed
mcp = pytest.importorskip("mcp", reason="MCP package not installed")


class TestMCPServer:
    """Test cases for the CadQuery MCP server."""

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

    def test_render_default_png(self):
        """Test default PNG rendering of a simple box."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
        }))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/png"

        # Decode and verify PNG header
        png_data = base64.b64decode(result[0].data)
        assert png_data.startswith(b"\x89PNG\r\n\x1a\n")

    def test_render_svg_explicit(self):
        """Test SVG rendering of a simple box when requested."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
            "format": "svg",
        }))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/svg+xml"

        # Decode and verify SVG content
        svg_content = base64.b64decode(result[0].data).decode("utf-8")
        assert "<svg" in svg_content
        assert "</svg>" in svg_content
        assert "<path" in svg_content  # Should have path elements for the box edges

    def test_render_svg_with_show_object(self):
        """Test SVG rendering using show_object() instead of result variable."""
        from cadquery_mcp_server import _handle_render

        code = """
import cadquery as cq
box = cq.Workplane('XY').box(5, 5, 5)
show_object(box)
"""
        result = asyncio.run(_handle_render({"code": code, "format": "svg"}))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/svg+xml"

    def test_render_no_shape_error(self):
        """Test that render returns an error when no shape is produced."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "x = 1 + 1",  # No shape produced
        }))

        assert len(result) == 1
        assert result[0].type == "text"
        assert "No shape produced" in result[0].text

    def test_render_syntax_error(self):
        """Test that render handles syntax errors gracefully."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "this is not valid python!!!",
        }))

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Syntax error" in result[0].text

    def test_render_execution_error(self):
        """Test that render handles execution errors gracefully."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "raise ValueError('test error')",
        }))

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Execution error" in result[0].text

    def test_inspect_box_geometry(self):
        """Test geometry inspection of a simple box."""
        from cadquery_mcp_server import _handle_inspect

        result = asyncio.run(_handle_inspect({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
        }))

        assert len(result) == 1
        assert result[0].type == "text"

        text = result[0].text
        assert "Bounding Box" in text
        assert "10.0000" in text  # X size
        assert "20.0000" in text  # Y size
        assert "30.0000" in text  # Z size
        assert "Volume" in text
        assert "6000" in text  # Volume = 10 * 20 * 30

    def test_inspect_topology(self):
        """Test that topology information is returned."""
        from cadquery_mcp_server import _handle_inspect

        result = asyncio.run(_handle_inspect({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        }))

        text = result[0].text
        assert "Topology" in text
        assert "Solids: 1" in text
        assert "Faces: 6" in text  # A box has 6 faces
        assert "Edges: 12" in text  # A box has 12 edges
        assert "Vertices: 8" in text  # A box has 8 vertices

    def test_get_parameters_finds_variables(self):
        """Test that get_parameters extracts script parameters."""
        from cadquery_mcp_server import _handle_get_parameters

        code = """
height = 10.0
width = 20.0
name = "test"
enabled = True

import cadquery as cq
result = cq.Workplane('XY').box(width, height, 5)
"""
        result = asyncio.run(_handle_get_parameters({"code": code}))

        assert len(result) == 1
        assert result[0].type == "text"

        text = result[0].text
        assert "height" in text
        assert "width" in text
        assert "name" in text
        assert "enabled" in text
        assert "10.0" in text
        assert "20.0" in text

    def test_get_parameters_no_params(self):
        """Test get_parameters when no parameters are found."""
        from cadquery_mcp_server import _handle_get_parameters

        result = asyncio.run(_handle_get_parameters({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 2, 3)",
        }))

        assert len(result) == 1
        assert "No parameters found" in result[0].text

    def test_export_step(self):
        """Test STEP export functionality."""
        from cadquery_mcp_server import _handle_export

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            filename = f.name

        try:
            result = asyncio.run(_handle_export({
                "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
                "filename": filename,
            }))

            assert len(result) == 1
            assert result[0].type == "text"
            assert "Exported to" in result[0].text

            # Verify file was created and has content
            assert os.path.exists(filename)
            assert os.path.getsize(filename) > 0
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_export_stl(self):
        """Test STL export functionality."""
        from cadquery_mcp_server import _handle_export

        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            filename = f.name

        try:
            result = asyncio.run(_handle_export({
                "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(5, 5, 5)",
                "filename": filename,
            }))

            assert len(result) == 1
            assert "Exported to" in result[0].text
            assert os.path.exists(filename)
            assert os.path.getsize(filename) > 0
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_export_no_shape_error(self):
        """Test that export returns an error when no shape is produced."""
        from cadquery_mcp_server import _handle_export

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            filename = f.name

        try:
            result = asyncio.run(_handle_export({
                "code": "x = 1",
                "filename": filename,
            }))

            assert len(result) == 1
            assert "No shape produced" in result[0].text
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_call_tool_dispatch(self):
        """Test that call_tool correctly dispatches to handlers."""
        from cadquery_mcp_server import call_tool

        # Test render dispatch
        result = asyncio.run(call_tool("render", {
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        }))
        assert result[0].type == "image"

        # Test inspect dispatch
        result = asyncio.run(call_tool("inspect", {
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        }))
        assert "Bounding Box" in result[0].text

        # Test unknown tool
        result = asyncio.run(call_tool("unknown_tool", {}))
        assert "Unknown tool" in result[0].text

    def test_complex_model_render(self):
        """Test rendering a more complex model."""
        from cadquery_mcp_server import _handle_render

        code = """
import cadquery as cq

# Create a box with a hole
result = (
    cq.Workplane('XY')
    .box(20, 20, 10)
    .faces('>Z')
    .workplane()
    .hole(5)
)
"""
        result = asyncio.run(_handle_render({"code": code}))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/png"

        png_content = base64.b64decode(result[0].data)
        assert png_content.startswith(b"\x89PNG\r\n\x1a\n")

    def test_render_with_dimensions(self):
        """Test that width/height parameters are accepted."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
            "width": 400,
            "height": 300,
        }))

        assert result[0].type == "image"
        assert result[0].mimeType == "image/png"
        png_content = base64.b64decode(result[0].data)
        assert png_content.startswith(b"\x89PNG\r\n\x1a\n")


class TestMCPServerEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_code(self):
        """Test handling of empty code."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({"code": ""}))
        assert result[0].type == "text"
        assert "No shape produced" in result[0].text

    def test_whitespace_only_code(self):
        """Test handling of whitespace-only code."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({"code": "   \n\n   "}))
        assert result[0].type == "text"
        assert "No shape produced" in result[0].text

    def test_inspect_with_show_object(self):
        """Test inspect works with show_object() syntax."""
        from cadquery_mcp_server import _handle_inspect

        code = """
import cadquery as cq
box = cq.Workplane('XY').box(5, 10, 15)
show_object(box)
"""
        result = asyncio.run(_handle_inspect({"code": code}))

        text = result[0].text
        assert "5.0000" in text
        assert "10.0000" in text
        assert "15.0000" in text


class TestMCPServerViews:
    """Test multi-view and custom view angle functionality."""

    def test_render_front_view(self):
        """Test rendering from front view."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
            "view": "front",
        }))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/png"
        png_content = base64.b64decode(result[0].data)
        assert png_content.startswith(b"\x89PNG\r\n\x1a\n")

    def test_render_top_view(self):
        """Test rendering from top view."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
            "view": "top",
        }))

        assert len(result) == 1
        assert result[0].type == "image"

    def test_render_all_standard_views(self):
        """Test that all standard views render successfully."""
        from cadquery_mcp_server import _handle_render, VIEWS

        code = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)"

        for view_name in VIEWS.keys():
            result = asyncio.run(_handle_render({
                "code": code,
                "view": view_name,
            }))
            assert result[0].type == "image", f"View '{view_name}' failed"

    def test_multi_view_returns_multiple_images(self):
        """Test that multi_view returns multiple images."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            "multi_view": True,
        }))

        # Should return: 1 text description + 4 images (isometric, front, top, right)
        assert len(result) == 5
        assert result[0].type == "text"
        assert "4 views" in result[0].text

        # Check all 4 images
        for i in range(1, 5):
            assert result[i].type == "image"
            assert result[i].mimeType == "image/png"

    def test_multi_view_content(self):
        """Test that multi_view images have valid image content."""
        from cadquery_mcp_server import _handle_render

        # Test PNG multi-view (default)
        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            "multi_view": True,
        }))

        for i in range(1, 5):
            png_content = base64.b64decode(result[i].data)
            assert png_content.startswith(b"\x89PNG\r\n\x1a\n")

        # Test SVG multi-view
        result_svg = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            "multi_view": True,
            "format": "svg",
        }))

        for i in range(1, 5):
            assert result_svg[i].mimeType == "image/svg+xml"
            svg_content = base64.b64decode(result_svg[i].data).decode("utf-8")
            assert "<svg" in svg_content
            assert "</svg>" in svg_content

    def test_show_hidden_option(self):
        """Test that show_hidden option is respected."""
        from cadquery_mcp_server import _handle_render

        code = """
import cadquery as cq
result = cq.Workplane('XY').box(20, 20, 10).faces('>Z').workplane().hole(5)
"""
        # Render with hidden lines
        result_with_hidden = asyncio.run(_handle_render({
            "code": code,
            "show_hidden": True,
            "format": "svg",
        }))

        # Render without hidden lines
        result_without_hidden = asyncio.run(_handle_render({
            "code": code,
            "show_hidden": False,
            "format": "svg",
        }))

        svg_with = base64.b64decode(result_with_hidden[0].data).decode("utf-8")
        svg_without = base64.b64decode(result_without_hidden[0].data).decode("utf-8")

        # SVG with hidden lines should have more content (dashed lines for hidden edges)
        assert len(svg_with) > len(svg_without)

    def test_views_dictionary_exists(self):
        """Test that VIEWS dictionary is properly defined."""
        from cadquery_mcp_server import VIEWS

        expected_views = ["isometric", "front", "back", "top", "bottom", "left", "right", "isometric_back"]
        for view in expected_views:
            assert view in VIEWS
            # Each view should be a 3-tuple (projection direction)
            assert len(VIEWS[view]) == 3
