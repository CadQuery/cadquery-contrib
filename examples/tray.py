import cadquery as cq
from cadquery import Assembly, Color, Location as Loc, Vector as Vec
from numpy import linspace,diff

Ws = 1200
Hs = 600

W = 770
H = 460
d = 5 
N = 7
h = 50

vpts = [(0,-3*H/8), (0,-H/4),(0,-H/8), (0,0), (0,H/8),(0,H/4),(0,3*H/8)]

pts = linspace(-(W-d)/2,(W-d)/2,N+2)
delta = diff(pts)[0]

def make_base():

    return (
        cq.Workplane()
        .rect(W,H)
        .extrude(d)
        .pushPoints(
            [(pt,0) for pt in pts] + 
            [(0,H/2-d/2),(0,-H/2+d/2)])
        .rect(d,d)
        .cutThruAll()
        )

def make_side():

    return cq.Workplane().rect(d,H-2*d).extrude(h)
    
def make_front():

    return (
        cq.Workplane()
        .rect(W,d).extrude(h-d)
        .faces('<Z').workplane()
        .rect(d,d).extrude(d)
        .faces('<Y').workplane()
        .pushPoints([(pt,(h-d)/2) for pt in pts])
        .rect(d,d).cutThruAll()
        )

def make_divider():

    return (
        cq.Workplane()
        .rect(d,H-2*d)
        .extrude(h-2*d)
        .faces('>Z').workplane()
        .pushPoints(vpts)
        .rect(d,d)
        .cutBlind(-d)
        .faces('<Z').workplane()
        .rect(d,d).extrude(d)
        .pushPoints([(0,-H/2+d-d/2,-(h-d)/2),(0,+H/2-d+d/2,-(h-d)/2)])
        .box(d,d,d)
        )

def make_spacer():
    
    return (
        cq.Workplane("XZ")
        .rect(delta-d,h-d)
        .pushPoints([(-(delta-d)/2,h/2-d-d/2),((delta-d)/2,h/2-d-d/2)])
        .rect(d,2*d)
        .extrude(d)
        )

base = make_base()
side_l = make_divider()
side_r = make_divider()
front_f = make_front()
front_b = make_front()

assy = (
    cq.Assembly(base,name='base',color=cq.Color(1,1,.4,0.5))
    .add(side_l,name='side_l',loc=Loc(Vec(-(W-d)/2,0,d)))
    .add(side_l,name='side_r',loc=Loc(Vec(+(W-d)/2,0,d)))
    .add(front_f,name='front_f',loc=Loc(Vec(0,-(H-d)/2,d)))
    .add(front_b,name='front_b',loc=Loc(Vec(0,(H-d)/2,d)))
    )

for i,p in enumerate(pts[1:-1]):
    
    assy = assy.add(make_divider(),name=f'div{i}',loc=Loc(Vec(p,0,d)))

for i,p in enumerate(pts[1:]):
    
    assy = assy.add(make_spacer(),name=f'div2{i}',loc=Loc(Vec(p-delta/2,d/2,d+(h)/2-d/2)))


show_object(assy)


# export to dxf
from path import Path
from cadquery import exporters as exp

with Path('tray').mkdir_p():
    exp.exportDXF(cq.Workplane().rect(Ws,Hs).extrude(1).section(),'sheet.dxf')
    exp.exportDXF(base.section(),'base.dxf')
    exp.exportDXF(front_f.section(),'front.dxf')
    exp.exportDXF(make_divider().faces('>X').workplane().section(), 'divider.dxf')
    exp.exportDXF(make_spacer().section(), 'spacer.dxf')
