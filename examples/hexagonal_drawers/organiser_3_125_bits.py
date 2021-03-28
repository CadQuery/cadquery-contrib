"""
Organiser for cutters with a shank of 3.125mm
"""

import cadquery as cq
import importlib
import base
import organiser_blank
importlib.reload(organiser_blank)

base_wp = (
    organiser_blank.organiser
    .faces(">Z")
    .workplane(centerOption="CenterOfMass")
)

bit_3_125_points = (
    base_wp
    .rarray(
        3.125 * 3,
        3.125 * 4,
        4,
        4,
    )
    .vals()
)
bit_3_125_points.extend(
    base_wp
    .rarray(
        3.125 * 3,
        3.125 * 4,
        3,
        3,
    )
    .vals()
)
bit_organiser = (
    base_wp
    .newObject(bit_3_125_points)
    .hole(
        3.125 + 2 * base.clearance.loose,
        depth=organiser_blank.organiser.val().BoundingBox().zlen - 1.5 * base.wall_thick,
    )
)
