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
CadQuery MCP (Model Context Protocol) Server.

This module provides an MCP server that allows AI assistants like Claude
to execute CadQuery scripts and receive rendered images of 3D models.

Usage:
    Run as a standalone server:
        python -m cadquery_mcp_server

    Or use the entry point:
        cadquery-mcp

Project configuration in Claude Code (.mcp.json in the project root):
    {
        "mcpServers": {
            "cadquery": {
                "type": "stdio",
                "command": "/absolute/path/to/your/environment/bin/python",
                "args": ["-u", "/absolute/path/to/mcp-server/cadquery_mcp_server.py"]
            }
        }
    }
"""

import asyncio
import base64
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, CallToolResult

from cadquery_core import (
    VIEWS,
    handle_render,
    handle_inspect,
    handle_get_parameters,
    handle_export,
)


server = Server("cadquery")
ToolResponse = list[TextContent | ImageContent] | CallToolResult


def _error_response(message: str) -> CallToolResult:
    """Report tool failures through MCP's error flag, not just their text."""
    return CallToolResult(isError=True, content=[TextContent(type="text", text=message)])


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available CadQuery tools."""
    return [
        Tool(
            name="render",
            description=(
                "Execute CadQuery Python code and return a rendered image of the 3D model. "
                "The code should use show_object() to output shapes, or assign the final result to 'result'. "
                "Example: result = cq.Workplane('XY').box(1, 2, 3). "
                "Returns shaded PNG by default, preserving assembly colors and locations. "
                "Use image_format='svg' for a monochrome line drawing. "
                "Use 'view' to specify camera angle, or 'multi_view' to get multiple angles at once."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "CadQuery Python code to execute",
                    },
                    "image_format": {
                        "type": "string",
                        "enum": ["png", "svg"],
                        "default": "png",
                        "description": "PNG for viewable colored images (default); SVG for line drawings.",
                    },
                    "view": {
                        "type": "string",
                        "description": "Camera view angle. Options: isometric (default), front, back, top, bottom, left, right, isometric_back",
                        "enum": list(VIEWS.keys()),
                        "default": "isometric",
                    },
                    "multi_view": {
                        "type": "boolean",
                        "description": "If true, returns multiple images from different angles (isometric, front, top, right). Useful for complex models.",
                        "default": False,
                    },
                    "width": {
                        "type": "integer",
                        "description": "Image width in pixels (default: 800)",
                        "default": 800,
                        "minimum": 16,
                        "maximum": 4096,
                    },
                    "height": {
                        "type": "integer",
                        "description": "Image height in pixels (default: 600)",
                        "default": 600,
                        "minimum": 16,
                        "maximum": 4096,
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "Whether to show hidden lines in SVG (default: true); unused for PNG.",
                        "default": True,
                    },
                },
                "required": ["code"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="inspect",
            description=(
                "Execute CadQuery code and return geometry information about the resulting shape, "
                "including bounding box dimensions, volume, surface area, and center of mass."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "CadQuery Python code to execute",
                    },
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="get_parameters",
            description=(
                "Parse CadQuery code and extract the parameters (variables) that can be customized. "
                "Returns parameter names, types, and default values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "CadQuery Python code to parse",
                    },
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="export",
            description=(
                "Execute CadQuery code and export the result to a file. "
                "Supported formats: STEP, STL, SVG, DXF, AMF, 3MF, VRML, BREP. "
                "Assembly STEP exports preserve part names, colors, and locations; mesh formats flatten geometry."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "CadQuery Python code to execute",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename (format determined by extension)",
                    },
                    "format": {
                        "type": "string",
                        "description": "Export format (optional, inferred from filename if not provided)",
                        "enum": ["STEP", "STL", "SVG", "DXF", "AMF", "3MF", "VRML", "BREP"],
                    },
                },
                "required": ["code", "filename"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> ToolResponse:
    """Handle tool calls."""

    try:
        if name == "render":
            return await _handle_render(arguments)
        elif name == "inspect":
            return await _handle_inspect(arguments)
        elif name == "get_parameters":
            return await _handle_get_parameters(arguments)
        elif name == "export":
            return await _handle_export(arguments)
        return _error_response(f"Unknown tool: {name}")
    except Exception as e:
        return _error_response(f"Error: {type(e).__name__}: {e}")


async def _handle_render(arguments: dict[str, Any]) -> ToolResponse:
    """Execute CadQuery code and return rendered PNG or SVG images."""
    image_format = arguments.get("image_format", "png")
    result = handle_render(
        arguments["code"],
        view=arguments.get("view", "isometric"),
        multi_view=arguments.get("multi_view", False),
        width=arguments.get("width", 800),
        height=arguments.get("height", 600),
        show_hidden=arguments.get("show_hidden", True),
        image_format=image_format,
    )

    if result.error:
        return _error_response(result.error)

    items: list[TextContent | ImageContent] = []
    if len(result.view_names) > 1:
        items.append(
            TextContent(
                type="text",
                text=f"Rendered {len(result.view_names)} views: {', '.join(result.view_names)}",
            )
        )
    payloads = result.png_contents if image_format == "png" else [
        svg.encode("utf-8") for svg in result.svg_contents
    ]
    mime_type = "image/png" if image_format == "png" else "image/svg+xml"
    for data in payloads:
        items.append(ImageContent(
            type="image", data=base64.b64encode(data).decode("ascii"), mimeType=mime_type,
        ))
    return items


async def _handle_inspect(arguments: dict[str, Any]) -> ToolResponse:
    """Execute CadQuery code and return geometry information."""
    result = handle_inspect(arguments["code"])

    if result.error:
        return _error_response(result.error)

    return [TextContent(type="text", text=result.text)]


async def _handle_get_parameters(arguments: dict[str, Any]) -> ToolResponse:
    """Parse CadQuery code and extract parameters."""
    result = handle_get_parameters(arguments["code"])

    if result.error:
        return _error_response(result.error)

    return [TextContent(type="text", text=result.text)]


async def _handle_export(arguments: dict[str, Any]) -> ToolResponse:
    """Execute CadQuery code and export to file."""
    result = handle_export(
        arguments["code"],
        arguments["filename"],
        arguments.get("format"),
    )

    if result.error:
        return _error_response(result.error)

    return [TextContent(type="text", text=f"Exported to: {result.filename}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run():
    """Entry point for the cadquery-mcp command."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
