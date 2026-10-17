# CadQuery MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that
lets AI assistants execute CadQuery scripts and render, inspect, and export 3D
CAD models. Run it with the `cadquery-mcp` entry point.

For command-line workflows, use the existing
[cq-cli](https://github.com/CadQuery/cq-cli) project.

## Features

- **render** - Execute CadQuery code and produce shaded PNGs or SVG line drawings
  - Offscreen PNG rendering preserves assembly colors and part locations
  - Multiple camera angles: isometric, isometric_back, front, back, top, bottom, left, right
  - Multi-view mode (isometric, front, top, right) for complex models
  - Configurable image dimensions
  - Hidden line rendering for SVG

- **inspect** - Get geometry information about a shape
  - Bounding box dimensions
  - Volume and surface area
  - Center of mass
  - Topology counts (solids, faces, edges, vertices)

- **get_parameters** - Extract customizable parameters from CadQuery scripts

- **export** - Export models to various formats
  - STEP, STL, SVG, DXF, AMF, 3MF, VRML, BREP
  - Assembly STEP exports retain names, colors, and locations

Shapes, Workplanes with multiple objects, nested assemblies, and multiple
`show_object()` outputs are supported. Failed MCP tool calls set `isError: true`.

## Installation

### Prerequisites

Use a dedicated environment with CadQuery 2.8 or later and MCP Python SDK 1.30 or
later (both below their next major version). For example:

```bash
# conda
conda create -n cadquery -c conda-forge cadquery=2.8.0 pip
conda activate cadquery

# mamba (drop-in replacement for conda; default in miniforge)
mamba create -n cadquery -c conda-forge cadquery=2.8.0 pip
```

### Install from Source

```bash
git clone https://github.com/CadQuery/cadquery-contrib.git
cd cadquery-contrib/mcp-server
python -m pip install .
```

For development (editable install):

```bash
python -m pip install -e .
```

### Run Tests

```bash
python -m pip install pytest
python -m pytest test_cadquery_mcp_server.py test_mcp_assemblies.py -v
```

## MCP Server Configuration

### Claude Code

Register the server from your CAD project's root, using absolute paths to the
Python interpreter with CadQuery/MCP installed and to this checkout's server:

```bash
claude mcp add --transport stdio --scope project cadquery -- \
  /absolute/path/to/environment/bin/python -u \
  /absolute/path/to/cadquery-contrib/mcp-server/cadquery_mcp_server.py
```

This writes a project-root `.mcp.json` (not `~/.claude/settings.json`):

```json
{
    "mcpServers": {
        "cadquery": {
            "type": "stdio",
            "command": "/absolute/path/to/environment/bin/python",
            "args": ["-u", "/absolute/path/to/cadquery-contrib/mcp-server/cadquery_mcp_server.py"]
        }
    }
}
```

Start or restart Claude Code in that project, approve the project server when
prompted, and check `/mcp`. `claude mcp get cadquery` shows the selected launcher,
scope, and status. A pending-approval status requires that interactive approval.
Use `--scope user` instead of `--scope project` for all projects. Local entries
take precedence over project entries, which take precedence over user entries;
remove stale registrations that shadow the intended checkout.

On WSL, run Claude Code and this Linux launcher inside WSL. A Windows-native
Claude Desktop process needs a Windows launcher or a `wsl.exe` wrapper instead.
If the Linux font cache is unwritable, add an `env` entry such as
`"XDG_CACHE_HOME": "/tmp/cadquery-cache"` to the server configuration.
See [Claude Code's MCP documentation](https://code.claude.com/docs/en/mcp).

### Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
    "mcpServers": {
        "cadquery": {
            "command": "cadquery-mcp"
        }
    }
}
```

**Note:** If using conda/mamba, you may need to specify the full path:

```json
{
    "mcpServers": {
        "cadquery": {
            "command": "/path/to/conda/envs/yourenv/bin/cadquery-mcp"
        }
    }
}
```

## MCP Usage Examples

Once configured, you can ask Claude to create 3D models:

> "Create a box with a hole through it"

Claude will execute:

```python
import cadquery as cq

result = (
    cq.Workplane('XY')
    .box(20, 20, 10)
    .faces('>Z')
    .workplane()
    .hole(5)
)
```

And return a rendered PNG image of the model. Set `image_format` to `svg` to
request an SVG line drawing instead. SVG preserves geometry but not part colors.

### Multi-View Rendering

For complex models, request multiple views:

> "Show me this bracket from multiple angles"

The server will return isometric, front, top, and right views.

### Parametric Models

CadQuery scripts can define parameters:

```python
height = 10.0  # Height of the box
width = 20.0   # Width of the box
depth = 5.0    # Depth of the box

import cadquery as cq
result = cq.Workplane('XY').box(width, height, depth)
```

Use the `get_parameters` tool to extract these for modification.

### Exporting Models

Export to STEP for manufacturing or STL for 3D printing:

> "Export this model as a STEP file to ~/models/bracket.step"

## API Reference (MCP tools)

### render

Execute CadQuery code and return rendered image(s).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| code | string | required | CadQuery Python code to execute |
| image_format | string | "png" | Shaded PNG with colors, or SVG line drawing |
| view | string | "isometric" | Camera angle (isometric, isometric_back, front, back, top, bottom, left, right) |
| multi_view | boolean | false | Return multiple views |
| width | integer | 800 | Image width in pixels |
| height | integer | 600 | Image height in pixels |
| show_hidden | boolean | true | Show hidden lines in SVG; unused for PNG |

Image width and height must be integers from 16 through 4096. PNG rendering uses
VTK's offscreen OpenGL backend; a working graphics backend is required. Explicit
SVG rendering does not require a display. PNG failures are returned as errors,
rather than silently falling back to SVG.

### inspect

Get geometry information about the resulting shape.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| code | string | required | CadQuery Python code to execute |

### get_parameters

Extract customizable parameters from a script.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| code | string | required | CadQuery Python code to parse |

### export

Export the model to a file.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| code | string | required | CadQuery Python code to execute |
| filename | string | required | Output filename |
| format | string | auto | Export format (STEP, STL, SVG, DXF, AMF, 3MF, VRML, BREP) |

## Writing CadQuery Scripts for MCP

Scripts should either:

1. Assign the final shape to a variable named `result`:
   ```python
   result = cq.Workplane('XY').box(1, 2, 3)
   ```

2. Use `show_object()` to output shapes:
   ```python
   box = cq.Workplane('XY').box(1, 2, 3)
   show_object(box)
   ```

Assemblies may be assigned to `result` or passed to `show_object()`. Multiple
displayed objects are collected into an assembly, including display colors:

```python
import cadquery as cq
result = cq.Assembly(name="example")
result.add(cq.Workplane("XY").box(10, 10, 10), name="red_block",
           color=cq.Color("red"))
result.add(cq.Workplane("XY").box(5, 5, 5), name="blue_block",
           loc=cq.Location((20, 0, 0)), color=cq.Color("blue"))
```

## License

Apache License 2.0 - see [LICENSE](../LICENSE) for details.

## Contributing

Contributions are welcome! Please see the [cadquery-contrib](https://github.com/CadQuery/cadquery-contrib) repository for guidelines.
