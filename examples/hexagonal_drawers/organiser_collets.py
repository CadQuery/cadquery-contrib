"""
An organiser with holes for ER11 collets.
"""

import cadquery as cq
from types import SimpleNamespace
import importlib
import organiser_blank
importlib.reload(organiser_blank)


collet_dims = SimpleNamespace(
    upper_diam=11.35,
    cone_height=13.55,
    lower_diam=7.8,
)
collet = (
    cq.Solid.makeCone(
        collet_dims.upper_diam / 2,
        collet_dims.lower_diam / 2,
        collet_dims.cone_height,
    )
    .mirror("XY")
    .translate(cq.Vector(0, 0, collet_dims.cone_height / 3))
)
collet_organiser_points = (
    organiser_blank.organiser
    .faces(">Z")
    .workplane(centerOption="CenterOfMass")
    .rarray(
        collet_dims.upper_diam * 1.5,
        collet_dims.upper_diam * 2.3,
        3,
        2,
    )
    .vals()
)
collet_organiser_points.extend(
    organiser_blank.organiser
    .faces(">Z")
    .workplane(centerOption="CenterOfMass")
    .rarray(
        collet_dims.upper_diam * 1.5,
        collet_dims.upper_diam * 2.3,
        2,
        1,
    )
    .vals()
)
collets = (
    cq.Workplane()
    .pushPoints(collet_organiser_points)
    .eachpoint(lambda loc: collet.located(loc))
)
collet_organiser = (
    organiser_blank.organiser
    .cut(collets)
)

if "show_object" in locals():
    show_object(collet_organiser, "collet organiser")
