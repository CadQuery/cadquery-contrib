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
CadQuery CLI — render, inspect, export, and query CadQuery scripts from
the command line.

Usage:
    cadquery-cli render script.py -o output.svg
    cadquery-cli render script.py --multi-view -o views.svg
    cadquery-cli render script.py --view front --width 1200 --height 900
    cadquery-cli inspect script.py
    cadquery-cli params script.py
    cadquery-cli export script.py -o model.step
    cadquery-cli export script.py -o model.stl
    cadquery-cli render -c "import cadquery as cq; result = cq.Workplane('XY').box(1,2,3)"
"""

import argparse
import sys

from cadquery_core import (
    VIEWS,
    handle_render,
    handle_inspect,
    handle_get_parameters,
    handle_export,
)


def _read_code(args) -> str:
    """Read CadQuery code from file, inline string, or stdin."""
    if hasattr(args, "code") and args.code:
        return args.code
    if hasattr(args, "file") and args.file:
        if args.file == "-":
            return sys.stdin.read()
        with open(args.file) as f:
            return f.read()
    # No file or code provided
    print("Error: provide a script file or use -c for inline code.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_render(args):
    """Handle the 'render' subcommand."""
    code = _read_code(args)

    result = handle_render(
        code,
        view=args.view,
        multi_view=args.multi_view,
        width=args.width,
        height=args.height,
        show_hidden=not args.no_hidden,
    )

    if result.error:
        print(result.error, file=sys.stderr)
        sys.exit(1)

    if args.output:
        if args.multi_view:
            # Write each view to a separate file:
            #   output.svg -> output_isometric.svg, output_front.svg, ...
            base = args.output
            if base.lower().endswith(".svg"):
                base = base[:-4]
            for svg, name in zip(result.svg_contents, result.view_names):
                path = f"{base}_{name}.svg"
                with open(path, "w") as f:
                    f.write(svg)
                print(f"Wrote {path}")
        else:
            with open(args.output, "w") as f:
                f.write(result.svg_contents[0])
            print(f"Wrote {args.output}")
    else:
        # Write to stdout
        sys.stdout.write(result.svg_contents[0])


def cmd_inspect(args):
    """Handle the 'inspect' subcommand."""
    code = _read_code(args)

    result = handle_inspect(code)

    if result.error:
        print(result.error, file=sys.stderr)
        sys.exit(1)

    print(result.text)


def cmd_params(args):
    """Handle the 'params' subcommand."""
    code = _read_code(args)

    result = handle_get_parameters(code)

    if result.error:
        print(result.error, file=sys.stderr)
        sys.exit(1)

    print(result.text)


def cmd_export(args):
    """Handle the 'export' subcommand."""
    code = _read_code(args)

    if not args.output:
        print("Error: -o / --output is required for export.", file=sys.stderr)
        sys.exit(1)

    result = handle_export(code, args.output, args.format)

    if result.error:
        print(result.error, file=sys.stderr)
        sys.exit(1)

    print(f"Exported to: {result.filename}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadquery-cli",
        description="CadQuery CLI — render, inspect, export, and query CadQuery scripts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- Common arguments (added to each subparser) -------------------------
    def add_input_args(sub):
        """Add file/code input arguments common to all subcommands."""
        group = sub.add_mutually_exclusive_group(required=True)
        group.add_argument("file", nargs="?", default=None,
                           help="CadQuery Python script file (use '-' for stdin)")
        group.add_argument("-c", "--code", default=None,
                           help="Inline CadQuery Python code")

    # -- render -------------------------------------------------------------
    render_p = subparsers.add_parser("render",
                                     help="Render a CadQuery script to SVG")
    add_input_args(render_p)
    render_p.add_argument("-o", "--output", default=None,
                          help="Output SVG file (default: stdout)")
    render_p.add_argument("--view", default="isometric",
                          choices=list(VIEWS.keys()),
                          help="Camera view angle (default: isometric)")
    render_p.add_argument("--multi-view", action="store_true", default=False,
                          help="Render from 4 angles (isometric, front, top, right)")
    render_p.add_argument("--width", type=int, default=800,
                          help="Image width in pixels (default: 800)")
    render_p.add_argument("--height", type=int, default=600,
                          help="Image height in pixels (default: 600)")
    render_p.add_argument("--no-hidden", action="store_true", default=False,
                          help="Hide hidden lines (default: show them)")
    render_p.set_defaults(func=cmd_render)

    # -- inspect ------------------------------------------------------------
    inspect_p = subparsers.add_parser("inspect",
                                      help="Inspect geometry: bbox, volume, topology")
    add_input_args(inspect_p)
    inspect_p.set_defaults(func=cmd_inspect)

    # -- params -------------------------------------------------------------
    params_p = subparsers.add_parser("params",
                                     help="Extract customizable parameters from a script")
    add_input_args(params_p)
    params_p.set_defaults(func=cmd_params)

    # -- export -------------------------------------------------------------
    export_p = subparsers.add_parser("export",
                                     help="Export to STEP, STL, DXF, AMF, 3MF, VRML, BREP")
    add_input_args(export_p)
    export_p.add_argument("-o", "--output", required=True,
                          help="Output filename (format inferred from extension)")
    export_p.add_argument("--format", default=None,
                          choices=["STEP", "STL", "SVG", "DXF", "AMF", "3MF", "VRML", "BREP"],
                          help="Explicit export format (overrides extension)")
    export_p.set_defaults(func=cmd_export)

    return parser


def run():
    """Entry point for the cadquery-cli command."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    run()
