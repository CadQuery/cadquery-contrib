# CadQuery MCP Server & CLI

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server **and** a standalone command-line tool that enable AI assistants (like Claude) and shell-based workflows to execute CadQuery scripts and render 3D CAD models.

The package installs two entry points:

- `cadquery-mcp` — MCP server for AI assistants
- `cadquery-cli` — CLI for direct use from a terminal or shell scripts

Both share the same underlying engine (`cadquery_core`) so behavior is identical.

## Features

- **render** - Execute CadQuery code and produce SVG images of the 3D model
  - Multiple camera angles: isometric, isometric_back, front, back, top, bottom, left, right
  - Multi-view mode (isometric, front, top, right) for complex models
  - Configurable image dimensions
  - Hidden line rendering

- **inspect** - Get geometry information about a shape
  - Bounding box dimensions
  - Volume and surface area
  - Center of mass
  - Topology counts (solids, faces, edges, vertices)

- **get_parameters** / `params` - Extract customizable parameters from CadQuery scripts

- **export** - Export models to various formats
  - STEP, STL, SVG, DXF, AMF, 3MF, VRML, BREP

## Installation

### Prerequisites

CadQuery must be installed first. The recommended method is via conda or mamba:

```bash
# conda
conda install -c conda-forge cadquery

# mamba (drop-in replacement for conda; default in miniforge)
mamba install -c conda-forge cadquery
```

### Install from Source

```bash
git clone https://github.com/CadQuery/cadquery-contrib.git
cd cadquery-contrib/mcp-server
pip install .
```

For development (editable install):

```bash
pip install -e .
```

### Run Tests

```bash
pip install pytest
pytest test_cadquery_mcp_server.py -v
```

## MCP Server Configuration

### Claude Code

Add to your `~/.claude/settings.json`:

```json
{
    "mcpServers": {
        "cadquery": {
            "command": "cadquery-mcp"
        }
    }
}
```

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

## CLI Usage

The `cadquery-cli` command exposes the same functionality as the MCP server, for use in terminals, scripts, or CI.

```bash
# Render a script to an SVG (isometric by default)
cadquery-cli render script.py -o output.svg

# Render multiple views (isometric, front, top, right) into separate files
cadquery-cli render script.py --multi-view -o views.svg

# Specific view + custom dimensions
cadquery-cli render script.py --view front --width 1200 --height 900

# Inspect geometry (bounding box, volume, surface area, etc.)
cadquery-cli inspect script.py

# Extract parameters defined in the script
cadquery-cli params script.py

# Export to STEP / STL / etc. (format inferred from filename)
cadquery-cli export script.py -o model.step
cadquery-cli export script.py -o model.stl

# Inline code instead of a script file
cadquery-cli render -c "import cadquery as cq; result = cq.Workplane('XY').box(1,2,3)" -o box.svg

# Read a script from stdin
cat script.py | cadquery-cli render - -o output.svg
```

Run `cadquery-cli --help` (or `cadquery-cli <subcommand> --help`) for the full flag list.

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

And return a rendered SVG image of the model.

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

Use the `get_parameters` tool (MCP) or `cadquery-cli params` (CLI) to extract these for modification.

### Exporting Models

Export to STEP for manufacturing or STL for 3D printing:

> "Export this model as a STEP file to ~/models/bracket.step"

## API Reference (MCP tools)

### render

Execute CadQuery code and return rendered image(s).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| code | string | required | CadQuery Python code to execute |
| view | string | "isometric" | Camera angle (isometric, isometric_back, front, back, top, bottom, left, right) |
| multi_view | boolean | false | Return multiple views |
| width | integer | 800 | Image width in pixels |
| height | integer | 600 | Image height in pixels |
| show_hidden | boolean | true | Show hidden lines |

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

## Writing CadQuery Scripts for MCP / CLI

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

## License

Apache License 2.0 - see [LICENSE](../LICENSE) for details.

## Contributing

Contributions are welcome! Please see the [cadquery-contrib](https://github.com/CadQuery/cadquery-contrib) repository for guidelines.
