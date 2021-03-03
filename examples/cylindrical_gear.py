import cadquery as cq 
from math import *

class HollowCylinderSelector(cq.Selector):
    """
    Selects any shape present in the infinite hollow cylinder.   
    """
    #It works for the use I have in this code, it's not tested for any other configuration hence it might not be super robust
    def __init__(self, inner_radius, outer_radius, along_axis = "Z"):
        self.r1 = inner_radius
        self.r2 = outer_radius
        if along_axis == "X":
            self.axis = 0
        elif along_axis == "Y":
            self.axis = 1
        elif along_axis == "Z":
            self.axis = 2
        
    def filter(self, objectList):
        result =[]
        for o in objectList:
            p = o.Center()
            p_coords = [p.x, p.y, p.z]
            del p_coords[self.axis]
            p_radius = sqrt(p_coords[0]**2 + p_coords[1]**2)

            if p_radius> self.r1 and p_radius < self.r2 :   
                result.append(o)

        return result

def involute(r):
    #callback for paramCurve() function
    def curve(t):
        """
        The involute curve is the curve that describe the flank of a tooth of a gear
        """
        x = r*(cos(t) + t*sin(t))
        y = r*(sin(t) - t*cos(t))
        return x,y
    return curve

def cylindrical_gear(m, z, alpha, b, helix_angle = None):
    """
    Create a cylindrical gear (either straight or helix)
    Note that the helix one is pretty slow to be generated and the filling of the root edge of the gear don't work for helix_angle > 3°

    params :
    m : module of the gear (gear meshes only if they have the same module)
    z : number of teeths
    b : thickness of the gear 
    """
    r_p = m*z/2 #primitif radius (radius at which contact with other gear is made)
    r_a = r_p + m   #radius of the top of the tooth
    r_f = r_p - 1.25*m #radius of the root of the tooth
    r_b = r_p*cos(radians(alpha)) #radius of the base circle from where the involute curve starts

    def create_tooth_profile(m, z, alpha):
        #Callback for eachpoint() function
        def tooth_profile(loc):


            STOP = sqrt((r_a/r_b)**2 - 1) # the STOP value is calculated by solving the following equation for t : ||involute(t)|| = r_a , ||involute(t)|| being the norm of the vector 
            #below I start my 2D shape by sketching the 2 flanks of the tooth define by the 2 involutes
            right = cq.Workplane("XY").parametricCurve(involute(r_b), stop = STOP, makeWire=False)
            wire = cq.Workplane("XY").tag("base").transformed(rotate=(0,0,180/z)).parametricCurve(involute(r_b), stop = -STOP, makeWire=False)        

            end_point_a = wire.val().endPoint().toTuple() #storing the global coord of the point for later use
            if r_b < r_f:                
                raise ValueError("r_b is smaller than r_f, your gear is undercut, try changing yours input parameter (use smaller alpah angle")
                # A gear could work even if it's undercut, I was just lazy to take care of it
                  
            else:
                wire = (wire.vertices("<X").workplane(centerOption="CenterOfMass").hLine(r_f-r_b)) # drawsing the rest of the profile starting from the bottom of the left involute
                start_arc_root_pt = wire.val().endPoint().toTuple() #storing coord of the point again
                #below building the final closed wire of the 2D tooth shape
                wire = (wire.workplaneFromTagged("base")
                    .moveTo(start_arc_root_pt[0], start_arc_root_pt[1] )
                    .radiusArc((r_f,0),r_f)
                    .hLine(r_b-r_f)
                    .parametricCurve(involute(r_b), stop = STOP, makeWire=False)
                    .radiusArc(end_point_a,r_a)
                    .combine()
                    .wire().clean()
                )    
            return wire.val().moved(loc)  #took the trick from slot2D function, eachpoint feeds via the previously created polararray
            # the Location objects of the points, so this return create a 2D tooth profile and then rotate it to the right coord
        return tooth_profile

    #creating all the 2D profiles of the gear
    teeths = (cq.Workplane("XY")    
    .polarArray(0, 0, 360, z) #since my involute curve starts at the origin, I just need rotate workplane, which actually works when specifing 0 radius to polararray
    .eachpoint(create_tooth_profile(m,z,alpha), useLocalCoordinates=True)
    )

    #extruding the 2D teeths in 3D
    if helix_angle is None:
        teeths = teeths.extrude(b)
    else:
        teeths = teeths.twistExtrude(b, helix_angle)

    # creating the final gear by extruding the middle portion and unioning it with alls the teeths previously created
    gear = (cq.Workplane("XY").circle(r_f).extrude(b).union(teeths)
    .edges( #Selecting only the edges parallel to Z axis at the root of the teeths
        HollowCylinderSelector(0, 1.01*r_f) -
        cq.DirectionMinMaxSelector(cq.Vector(0,0,1)) -
        cq.DirectionMinMaxSelector(cq.Vector(0,0,1),directionMax=False)
        )
    .fillet(0.4*m) 
    .faces(">Z")
    .circle(0.5*r_f)
    .cutThruAll()
    )
    return gear

############################################################
############################################################
############################################################

#Creation of 2 gears that meshes

alpha = 20
m = 1
z1 = 20
z2 = 12
b = m*5


gear = cylindrical_gear(m,z1,alpha,b)
gear2 = cylindrical_gear(m,z2,alpha,b).val().move(cq.Location(cq.Vector(m*z1/2+m*z2/2,0,0)))
show_object(gear)
show_object(gear2)
