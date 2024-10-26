import cadquery as cq
from math import pi, cos, acos, sin, sqrt, atan, tan
import numpy as np


# TETRAKAIDECAHEDRON

def pmcross(self, r1=1, fn=6, forConstruction=False):
        def _makeCross(loc):
            pnts = []
            t = 2*pi / fn
            R = r1/2 / sin(t)
            for i in range(fn+1):
                pts = [R*cos(i * t + pi/fn), R*sin(i * t + pi/fn)]
                pnts.append(cq.Vector(pts[0], pts[1], 0))
                    
            return cq.Wire.makePolygon(pnts, forConstruction).locate(loc)
        
        return self.eachpoint(_makeCross, True)
cq.Workplane.pmcross = pmcross

L = 20
W = 20
H = 20
D = 10 # Cell diameter
WT = 1
FRO = 3
FRI = 2
NPS = 6

A = 180 / NPS
BS = acos(1/sqrt(3)) * 180/pi
BH = acos(1/3) * 180/pi

tc = 1.
dc = (D -2*WT +2*tc) / (2 * cos((90-BS)*pi/180))

dcc = dc * tan(A*pi/180)

path_h = cq.Workplane('XY').pmcross(dc, NPS)
cell_h0 = cq.Workplane('XZ').workplane().center(dc/2,0).polygon(10,tc).sweep(path_h)

lo = [cell_h0.val()]
cell_s = cell_h0

# ADD HEXAGONS
cell_h1 = cell_h0.translate((-dc*sin(A*pi/180), dc*cos(A*pi/180), 0))
V1 = [-dcc*cos(A*pi/180), dcc*sin(A*pi/180), 0]
V2 = [0, dcc, 0]
cell_h1 = cell_h1.rotate(V1,V2,BH)
cell_h1 = cell_h1.cut(cell_h0)
cell_s = cell_s.union(cell_h1, glue=True)

cell_h2 = cell_h0.translate((-dc*sin(A*pi/180), -dc*cos(A*pi/180), 0))
V1 = [-dcc*cos(A*pi/180), -dcc*sin(A*pi/180), 0]
V2 = [0, -dcc, 0]
cell_h2 = cell_h2.rotate(V1,V2,-BH)
cell_h2 = cell_h2.cut(cell_h0)
cell_s = cell_s.union(cell_h2, glue=True)

cell_h3 = cell_h0.translate((dc, 0, 0))
V1 = [dc/2, -dcc/2, 0]
V2 = [dc/2, dcc/2, 0]
cell_h3 = cell_h3.rotate(V1,V2,-BH)
cell_h3 = cell_h3.cut(cell_h0)
cell_s = cell_s.union(cell_h3, glue=True)


# ADD SYMMETRY
dz = dc * cos((90-BH)*pi/180) + dcc * cos((90-BS)*pi/180)
cell = cell_s.rotate((0,0,0),(1,0,0),180).rotate((0,0,0),(0,0,1),60).translate((0,0,dz))
cell = cell_s.union(cell).rotateAboutCenter((0,1,0),90-BS)

# PATTERN
dx = dc * sin((90-BS)*pi/180)  + dcc/2 - tc/2
dy = dz = dc * cos((90-BS)*pi/180) + dcc/2 + tc/2
x_af0 = np.arange(0, H, dx)[:-2]
y_af0 = np.arange(0, W, dy)[1:]
z_af0 = np.arange(0, L,  dz)#[:-1]

x_af, y_af, z_af = np.meshgrid(x_af0, y_af0, z_af0)
xyz_af = np.array([[x,y,z] for x,y,z in zip(x_af.flatten(), y_af.flatten(), z_af.flatten())])

xyz_af[::2, 0] += dx
xyz_af[::2, 1] += dy
xyz_af[::2, 2] += dz
xyz_af = np.unique(xyz_af, axis = 0)
xyz_af = [tuple(e) for e in xyz_af]

def cell_pos(pos):
    return cell.translate(pos).val()
cellS = cq.Workplane('XY').pushPoints(xyz_af).each(cell_pos).combine()
cellS = cellS.translate((0, -W/2-dc/2+FRI, -L/2-dz/2))

show_object(cellS)

#cq.exporters.export(cellS.val(), 'EV_Tetrakaidecahedron.step')


