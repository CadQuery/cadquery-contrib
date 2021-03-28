"""
An organiser that takes up 1/3 of a drawer and has no cutouts yet.
"""

import cadquery as cq
import importlib
import base
importlib.reload(base)


# organiser base
# first grab the inner profile of the drawer
lines = (
    base.drawer
    .faces(">Y")
    .workplane(offset=-base.drawer_length / 2)
    .section()
    .edges()
    .vals()
)
assert len(lines) == 8
# sort lines by radius about y axis
lines.sort(
    key=lambda x: cq.Vector(x.Center().x, 0, x.Center().z).Center().Length
)
wire = cq.Wire.assembleEdges(lines[0:3])
wire = cq.Wire.combine(
    [wire, cq.Edge.makeLine(wire.endPoint(), wire.startPoint())]
)[0]
wire_center = wire.Center()
wire = wire.translate(cq.Vector(0, -wire_center.y, 0))
organiser = (
    cq.Workplane("XZ")
    .newObject([wire])
    .toPending()
    .extrude(base.drawer_length / 3 - base.clearance.loose)
)
