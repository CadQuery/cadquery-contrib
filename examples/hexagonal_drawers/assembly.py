"""
Display the drawers
"""

import cadquery as cq
import importlib
import base
import organiser_collets
import organiser_3_125_bits
importlib.reload(base)
importlib.reload(organiser_collets)
importlib.reload(organiser_3_125_bits)

sep = 20  # seperation between parts
big_sep = 100  # extra for the organisers

assy = cq.Assembly()
assy.add(base.frame, name="frame")
assy.add(base.drawer, name="drawer")
assy.add(organiser_collets.collet_organiser, name="collet organiser")
assy.add(organiser_3_125_bits.bit_organiser, name="bit organiser")

# pull the drawer out
assy.constrain(
    "frame",
    base.frame.faces("<Y").val().translate((0, -sep, 0)),
    "drawer",
    base.drawer.faces(">Y").val(),
    "Point",
)

# bit organiser aligns with back face of drawer and is big_sep above
assy.constrain(
    "drawer",
    base.drawer.faces("<Y[1]").val().translate((0, 0, big_sep)),
    "bit organiser",
    organiser_3_125_bits.bit_organiser.faces(">Y").val(),
    "Point",
)
assy.constrain(
    "bit organiser",
    organiser_3_125_bits.bit_organiser.faces("<Y").val().translate((0, -sep, 0)),
    "collet organiser",
    organiser_collets.collet_organiser.faces(">Y").val(),
    "Point",
)

# align the z and x axes between obj0 and obj1
align_these = (
    ("frame", "drawer"),
    ("drawer", "collet organiser"),
    ("drawer", "bit organiser"),
)
for obj0, obj1 in align_these:
    assy.constrain(
        obj0,
        cq.Face.makePlane(),
        obj1,
        cq.Face.makePlane(),
        "Axis",
        0,
    )
    assy.constrain(
        obj0,
        cq.Face.makePlane(dir=(1, 0, 0)),
        obj1,
        cq.Face.makePlane(dir=(1, 0, 0)),
        "Axis",
        0,
    )

assy.solve()
if "show_object" in locals():
    show_object(assy)
