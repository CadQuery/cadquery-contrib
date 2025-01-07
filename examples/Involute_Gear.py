import cadquery as cq
from cadquery import Workplane, Edge, Wire, Vector
from math import *


def involute_gear(m, z, alpha=20, shift=0, N=20):
    '''
    See https://khkgears.net/new/gear_knowledge/gear_technical_reference/involute_gear_profile.html
    for math
    '''
    
    alpha = radians(alpha)

    # radii
    r_ref = m*z/2
    r_top = r_ref + m*(1+shift)
    r_base = r_ref*cos(alpha)
    r_d = r_ref - 1.25*m
    
    inv = lambda a: tan(a) - a
    
    # angles of interest
    alpha_inv = inv(alpha)
    alpha_tip = acos(r_base/r_top)
    alpha_tip_inv = inv(alpha_tip)
    
    a = 90/z+degrees(alpha_inv)
    a2 = 90/z++degrees(alpha_inv)-degrees(alpha_tip_inv)
    a3 = 360/z-a
    
    # involute curve (radius based parametrization)
    def involute_curve(r_b,sign=1):
        
        def f(r):
            alpha = sign*acos(r_b/r)
            x = r*cos(tan(alpha) - alpha) 
            y = r*sin(tan(alpha) - alpha)
        
            return x,y
        
        return f
    
    # construct all the profiles
    right = (
        Workplane()
        .transformed(rotate=(0,0,a))
        .parametricCurve(involute_curve(r_base,-1), start=r_base, stop = r_top, makeWire=False, N=N)
        .val()
    )
    
    left = (
        Workplane()
        .transformed(rotate=(0,0,-a))
        .parametricCurve(involute_curve(r_base), start=r_base, stop = r_top, makeWire=False, N=N)
        .val()
    )

    top = Edge.makeCircle(r_top,angle1=-a2, angle2=a2)
    bottom = Edge.makeCircle(r_d, angle1=-a3, angle2=-a)
    
    side = Edge.makeLine( cq.Vector(r_d,0), cq.Vector(r_base,0))
    side1 = side.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), -a)
    side2 = side.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), -a3)
    
    # single tooth profile
    profile = Wire.assembleEdges([left,top,right,side1,bottom,side2])
    profile = profile.chamfer2D(m/4, profile.Vertices()[-3:-1])

    # complete gear
    res = (
        Workplane()
        .polarArray(0,0,360,z)
        .each(lambda loc: profile.located(loc))
        .consolidateWires()
    )

    return res.val()


show_object(
    Workplane(obj=involute_gear(1, 20)).toPending().twistExtrude(20, 30)
)
