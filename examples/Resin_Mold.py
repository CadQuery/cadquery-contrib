import cadquery as cq
BS = cq.selectors.BoxSelector

# PARAMETERS
mount_holes = True

# mold size
mw = 40
mh = 13
ml = 120

# wire and fix size
wd = 6  # wire diameter
rt = 7  # resin thickness
rl = 50  # resin length
rwpl = 10  # resin to wire pass length

# pocket fillet
pf = 18

# mount holes
mhd = 7  # hole diameter
mht = 3  # hole distance from edge

# filling hole
fhd = 6

# DRAWING

# draw base
base = cq.Workplane("XY").box(ml, mw, mh, (True, True, False))

# draw wire
pocket = cq.Workplane("XY", (0, 0, mh)).moveTo(-ml/2., 0).line(0, wd/2.)\
    .line((ml-rl)/2.-rwpl, 0).line(rwpl, rt).line(rl, 0)\
    .line(rwpl, -rt).line((ml-rl)/2.-rwpl, 0)\
    .line(0, -(wd/2.)).close().revolve(axisEnd=(1, 0))\
    .edges(BS((-rl/2.-rwpl-.1, -100, -100), (rl/2.+rwpl+.1, 100, 100)))\
    .fillet(pf)

r = base.cut(pocket)

# mount holes
if mount_holes:
    px = ml/2.-mht-mhd/2.
    py = mw/2.-mht-mhd/2
    r = r.faces("<Z").workplane().pushPoints([
    (px, py),
    (-px, py),
    (-px, -py),
    (px, -py)
    ]).hole(mhd)

# fill holes
r = r.faces("<Y").workplane().center(0, mh/2.).pushPoints([
    (-rl/2., 0),
    (0, 0),
    (rl/2., 0)
    ]).hole(fhd, mw/2.)

show_object(r)