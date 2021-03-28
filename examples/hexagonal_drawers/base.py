"""
The basic frame and drawer.
"""

import cadquery as cq
from types import SimpleNamespace
from math import tan, radians

hex_diam = 80  # outside of the drawer frame
wall_thick = 3
clearance = SimpleNamespace(tight=0.3)
clearance.loose = clearance.tight * 2
drawer_length = 150
dovetail_min_thick = wall_thick * 2

frame_y = drawer_length + clearance.loose + 2 * wall_thick

frame = (
    cq.Workplane("XZ")
    .polygon(6, hex_diam)
    .extrude(frame_y)
    .faces("<Y")
    .shell(-2 * wall_thick)
)

drawer = (
    frame
    .faces("<Y[1]")
    .wires()
    .translate((0, -clearance.loose, 0))
    .toPending()
    .offset2D(-clearance.loose)
    .extrude(drawer_length, combine=False)
    .faces(">Z or >>Z[-2]")
    .shell(-wall_thick)
)

handle = (
    drawer
    .faces("<Y")
    .edges("<Z")
)
handle_width = handle.val().Length()
handle = (
    handle
    .workplane(centerOption="CenterOfMass")
    .transformed(rotate=(-90, 0, 180))
    .circle(handle_width / 2)
    .circle(handle_width / 2 - wall_thick)
    .transformed(rotate=(30, 0, 0))
    .extrude(hex_diam / 2, combine=False)
    .newObject([drawer.faces("<Y").val()])
    .workplane(centerOption="CenterOfMass")
    .split(keepTop=True)
)

drawer = drawer.union(handle)
del handle

top_length = frame.faces(">Z").val().BoundingBox().ylen
dovetail_base_radius = frame.faces("<Y").edges(">Z").val().Center().z
dovetail_length = 0.9 * top_length

# make the male dovetail join
# should extend wall_thick out from the frame
dovetail_positive = (
    cq.Workplane()
    .hLine(dovetail_min_thick / 2)
    .line(wall_thick * tan(radians(30)), wall_thick)
    .hLineTo(0)
    .mirrorY()
    .extrude(-dovetail_length)
    .faces("<Z")
    .edges("<Y")
    .workplane()
    .transformed(rotate=(60, 0, 0))
    .split(keepBottom=True)
)
# provide some clearance around the straight section, but leave the sloped
# plane at the back alone so it mates as a backstop
# dovetail_straight_length = dovetail_positive.edges(">Y and |Z").val().Length()
dovetail_negative = (
    dovetail_positive
    .tag("dovetail_positive")
    .faces(">Z")
    .wires()
    .toPending()
    .offset2D(clearance.tight)
    .faces(">Z", tag="dovetail_positive")
    .workplane()
    .extrude(-(dovetail_length + clearance.tight))
    .faces("<Z")
    .edges("<Y")
    .workplane()
    .transformed(rotate=(60, 0, 0))
    .split(keepBottom=True)
    .mirror("XZ")
)
dovetail_baseplane = (
    frame
    .faces("<Y")
    .workplane(centerOption="CenterOfMass")
)
dovetail_positive = (
    dovetail_baseplane
    .polarArray(dovetail_base_radius, startAngle=-60, angle=120, count=3)
    .eachpoint(lambda loc: dovetail_positive.val().located(loc), useLocalCoordinates=True)
)

dovetail_negative = (
    dovetail_baseplane
    .polarArray(dovetail_base_radius, startAngle=120, angle=120, count=3)
    .eachpoint(lambda loc: dovetail_negative.val().located(loc), useLocalCoordinates=True)
)
frame = frame.union(dovetail_positive, glue=True).cut(dovetail_negative)

if "show_object" in locals():
    show_object(frame, "frame", options={"alpha": 0.5, "color": "black"})
    show_object(drawer, "drawer", options={"color": "green"})
