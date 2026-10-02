"""
Tests for the CadQuery MCP server, CLI, and shared core.

These tests verify that:
- The core module executes CadQuery scripts correctly
- SVG rendering works correctly (headless)
- Geometry inspection returns correct values
- Parameter extraction works
- Export functionality works
- Error handling is correct
- Multi-view rendering works
- The MCP server dispatches to core correctly
- The CLI argument parser and subcommands work

Run with: pytest test_cadquery_mcp_server.py -v
"""

import pytest
import asyncio
import base64
import tempfile
import os
import subprocess
import sys


# ============================================================================
# Core module tests (no MCP dependency required)
# ============================================================================

class TestCore:
    """Test the shared cadquery_core module directly."""

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
        assert len(result.svg_contents) == 1
        assert "<svg" in result.svg_contents[0]
        assert "</svg>" in result.svg_contents[0]
        assert "<path" in result.svg_contents[0]

    def test_render_with_show_object(self):
        """Test SVG rendering using show_object() instead of result variable."""
        from cadquery_core import handle_render

        code = "import cadquery as cq\nbox = cq.Workplane('XY').box(5, 5, 5)\nshow_object(box)"
        result = handle_render(code)

        assert result.error is None
        assert len(result.svg_contents) == 1
        assert "<svg" in result.svg_contents[0]

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
        assert len(result.svg_contents) == 1
        assert result.view_names == ["front"]

    def test_render_all_views(self):
        """Test that all standard views render successfully."""
        from cadquery_core import handle_render, VIEWS

        code = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)"
        for view_name in VIEWS.keys():
            result = handle_render(code, view=view_name)
            assert result.error is None, f"View '{view_name}' failed: {result.error}"
            assert "<svg" in result.svg_contents[0]

    def test_render_multi_view(self):
        """Test that multi_view returns 4 SVGs."""
        from cadquery_core import handle_render

        result = handle_render(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            multi_view=True,
        )

        assert result.error is None
        assert len(result.svg_contents) == 4
        assert len(result.view_names) == 4
        assert "isometric" in result.view_names
        assert "front" in result.view_names
        for svg in result.svg_contents:
            assert "<svg" in svg

    def test_render_dimensions(self):
        """Test that width/height parameters are accepted."""
        from cadquery_core import handle_render

        result = handle_render(
            "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
            width=400,
            height=300,
        )
        assert result.error is None
        assert "<svg" in result.svg_contents[0]

    def test_render_show_hidden(self):
        """Test that show_hidden option affects output."""
        from cadquery_core import handle_render

        code = "import cadquery as cq\nresult = cq.Workplane('XY').box(20, 20, 10).faces('>Z').workplane().hole(5)"

        result_with = handle_render(code, show_hidden=True)
        result_without = handle_render(code, show_hidden=False)

        assert result_with.error is None
        assert result_without.error is None
        # SVG with hidden lines should have more content
        assert len(result_with.svg_contents[0]) > len(result_without.svg_contents[0])

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
        assert "<svg" in result.svg_contents[0]


# ============================================================================
# MCP server tests (require mcp package)
# ============================================================================

mcp = pytest.importorskip("mcp", reason="MCP package not installed")


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
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)",
        }))

        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].mimeType == "image/svg+xml"

        svg_content = base64.b64decode(result[0].data).decode("utf-8")
        assert "<svg" in svg_content

    def test_render_error_returns_text_content(self):
        """Test that MCP render errors return TextContent."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({"code": "x = 1"}))
        assert result[0].type == "text"
        assert "No shape produced" in result[0].text

    def test_multi_view_returns_multiple_images(self):
        """Test that multi_view returns text + 4 images."""
        from cadquery_mcp_server import _handle_render

        result = asyncio.run(_handle_render({
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)",
            "multi_view": True,
        }))

        assert len(result) == 5
        assert result[0].type == "text"
        assert "4 views" in result[0].text
        for i in range(1, 5):
            assert result[i].type == "image"
            assert result[i].mimeType == "image/svg+xml"

    def test_inspect_returns_text_content(self):
        """Test that MCP inspect returns TextContent."""
        from cadquery_mcp_server import _handle_inspect

        result = asyncio.run(_handle_inspect({
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
        }))
        assert result[0].type == "image"

        # inspect
        result = asyncio.run(call_tool("inspect", {
            "code": "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)",
        }))
        assert "Bounding Box" in result[0].text

        # unknown
        result = asyncio.run(call_tool("unknown_tool", {}))
        assert "Unknown tool" in result[0].text


# ============================================================================
# CLI tests
# ============================================================================

class TestCLI:
    """Test the cadquery-cli argument parser and subcommands."""

    def test_import(self):
        """Test that the CLI module can be imported."""
        import cadquery_cli
        assert cadquery_cli.build_parser is not None

    def test_parser_render(self):
        """Test render subcommand argument parsing."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args(["render", "test.py", "-o", "out.svg"])
        assert args.command == "render"
        assert args.file == "test.py"
        assert args.output == "out.svg"
        assert args.view == "isometric"
        assert args.multi_view is False

    def test_parser_render_options(self):
        """Test render with all options."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args([
            "render", "test.py",
            "--view", "front",
            "--multi-view",
            "--width", "1200",
            "--height", "900",
            "--no-hidden",
            "-o", "out.svg",
        ])
        assert args.view == "front"
        assert args.multi_view is True
        assert args.width == 1200
        assert args.height == 900
        assert args.no_hidden is True

    def test_parser_render_inline_code(self):
        """Test render with inline code."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args(["render", "-c", "result = cq.Workplane('XY').box(1,2,3)"])
        assert args.code == "result = cq.Workplane('XY').box(1,2,3)"
        assert args.file is None

    def test_parser_inspect(self):
        """Test inspect subcommand parsing."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args(["inspect", "test.py"])
        assert args.command == "inspect"
        assert args.file == "test.py"

    def test_parser_params(self):
        """Test params subcommand parsing."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args(["params", "test.py"])
        assert args.command == "params"

    def test_parser_export(self):
        """Test export subcommand parsing."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args(["export", "test.py", "-o", "model.step"])
        assert args.command == "export"
        assert args.output == "model.step"
        assert args.format is None

    def test_parser_export_format(self):
        """Test export with explicit format."""
        from cadquery_cli import build_parser
        parser = build_parser()

        args = parser.parse_args(["export", "test.py", "-o", "model.out", "--format", "STL"])
        assert args.format == "STL"

    def test_cli_render_file(self):
        """Integration test: render a script file via CLI."""
        from cadquery_cli import cmd_render, build_parser

        # Write a temp script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)\n")
            script = f.name

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            outfile = f.name

        try:
            parser = build_parser()
            args = parser.parse_args(["render", script, "-o", outfile])
            args.func(args)

            assert os.path.exists(outfile)
            with open(outfile) as f:
                content = f.read()
            assert "<svg" in content
        finally:
            for p in (script, outfile):
                if os.path.exists(p):
                    os.unlink(p)

    def test_cli_inspect_file(self):
        """Integration test: inspect a script file via CLI."""
        from cadquery_cli import cmd_inspect, build_parser

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import cadquery as cq\nresult = cq.Workplane('XY').box(10, 20, 30)\n")
            script = f.name

        try:
            parser = build_parser()
            args = parser.parse_args(["inspect", script])
            # Just verify it doesn't crash (output goes to stdout)
            args.func(args)
        finally:
            if os.path.exists(script):
                os.unlink(script)

    def test_cli_export_file(self):
        """Integration test: export a script to STEP via CLI."""
        from cadquery_cli import cmd_export, build_parser

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import cadquery as cq\nresult = cq.Workplane('XY').box(5, 5, 5)\n")
            script = f.name

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            outfile = f.name

        try:
            parser = build_parser()
            args = parser.parse_args(["export", script, "-o", outfile])
            args.func(args)

            assert os.path.exists(outfile)
            assert os.path.getsize(outfile) > 0
        finally:
            for p in (script, outfile):
                if os.path.exists(p):
                    os.unlink(p)

    def test_cli_render_multi_view(self):
        """Integration test: multi-view render creates separate files."""
        from cadquery_cli import cmd_render, build_parser

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)\n")
            script = f.name

        outbase = tempfile.mktemp(suffix=".svg")

        try:
            parser = build_parser()
            args = parser.parse_args(["render", script, "--multi-view", "-o", outbase])
            args.func(args)

            base = outbase[:-4]  # strip .svg
            expected_files = [f"{base}_{v}.svg" for v in ["isometric", "front", "top", "right"]]
            for ef in expected_files:
                assert os.path.exists(ef), f"Missing: {ef}"
                with open(ef) as f:
                    assert "<svg" in f.read()
        finally:
            if os.path.exists(script):
                os.unlink(script)
            base = outbase[:-4]
            for v in ["isometric", "front", "top", "right"]:
                p = f"{base}_{v}.svg"
                if os.path.exists(p):
                    os.unlink(p)
