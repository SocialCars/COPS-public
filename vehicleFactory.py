import random
import sumolib


## Generate a random demand of vehicles for the parking space search and create the corresponding XML file
#  @param num Number of vehicles
def generatePsvDemand(num):
    # create seperate lists for possible origin or destination edges
    origins = []
    destinations = []
    # parse edges XML file for all network edges
    for edge in sumolib.output.parse('reroute.edg.xml', ['edge']):
        # if the edge ID contains "entry": use it as origin only;
        # otherwise: use it as destination only
        if "entry" in str(edge.id):
            origins.append(str(edge.id))
        else:
            destinations.append(str(edge.id))

    # open routes XML file for write access
    f = open("reroute.rou.xml", 'w', 1)
    
    # define tab as 4 spaces
    tab = "    "
    # base string for vehicle trip data
    veh = '<trip id="veh{0}" depart="0" from="{1}" to="{2}" type="Car" ' + \
            'color="0,1,0"/>\n'
    
    # write header
    f.write("<vehicles>\n")
    # write definitions of 'Car' type
    f.write(tab + '<vType accel="1.0" decel="5.0" id="Car" length="4.0"' + \
            ' maxSpeed="100.0" sigma="0.0"/>\n')
    # for each vehicle, select random O/D from possible origins/destinations
    # and write trip info to XML file
    for i in range(num):
        origin = random.choice(origins)
        dest = random.choice(destinations)
        f.write(tab + veh.format(i, origin, dest))
    # write footer
    f.write("</vehicles>")
    # close the XML file
    f.close()
