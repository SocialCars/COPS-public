#!/usr/bin/env python
from __future__ import print_function
import os
import sys
import subprocess
import random
import itertools

# (from SUMO examples:)
# we need to import python modules from the $SUMO_HOME/tools directory
try:
    sys.path.append(os.path.join(os.path.dirname(
        "__file__"), '..', '..', '..', "tools"))  # tutorial in tests
    sys.path.append(os.path.join(os.environ.get("SUMO_HOME", os.path.join(
        os.path.dirname("__file__"), "..", "..")), "tools"))  # tutorial in docs
    from sumolib import checkBinary
except ImportError:
    sys.exit("please declare environment variable 'SUMO_HOME' as the root"+ \
    "directory of your sumo installation (it should contain folders 'bin'," + \
    "'tools' and 'docs')")

import traci
import sumolib

from cooperativeSearch import *
from parkingSearchVehicle import *
from parkingSpace import *
from vehicleFactory import *
from environment import *

class Runtime(object):

    ## C'tor
    # @param p_args Arguments provided by command line via argparse
    def __init__(self, p_args):

        self._args = p_args

        # seed for random number generator, random for now
        random.seed()

        # if --routefile flag is provided, use the file for routing,
        # otherwise generate (and overwrite if exists) route file (reroute.rou.xml) for this simulation run
        # using the given number of parking search vehicles
        if self._args.routefile:
            self._routefile = self._args.routefile
        else:
            self._routefile = "reroute.rou.xml"
            generatePsvDemand(p_args.psv, self._routefile)

        # run sumo with gui or headless, depending on the --gui flag
        self._sumoBinary = checkBinary('sumo-gui') if self._args.gui else checkBinary('sumo')

        self._environment = Environment()
        print(self._environment._roadNetwork["edges"]["1to2"])

    ## Runs the simulation on both SUMO and Python layers
    def run(self):

        # this is the normal way of using traci. sumo is started as a
        # subprocess and then the python script connects and runs
        l_sumoProcess = subprocess.Popen(
            [self._sumoBinary,
             "-n", "reroute.net.xml",
             "-r", self._routefile,
             "--tripinfo-output", "tripinfo.xml",
             "--gui-settings-file", "gui-settings.cfg",
             "--no-step-log",
             "--remote-port", str(self._args.sumoport)],
            stdout=sys.stdout,
            stderr=sys.stderr)

        # execute the TraCI control loop
        traci.init(self._args.sumoport)

        # internal clock variable, start with 0
        step = 0

        # use sumolib to parse the nodes XML file and write node IDs to the list
        nodes = map(lambda x: str(x.id), sumolib.output.parse('reroute.nod.xml', ['node']))

        # use sumolib to parse the edges XML file and write edge IDs to the list
        edges = map(lambda x: str(x.id), sumolib.output.parse('reroute.edg.xml', ['edge']))

        # full numbers of nodes and edges in the network
        numberOfNodesinNetwork = len(nodes)
        numberOfEdgesinNetwork = len(edges)
        # use sumolib to read the network XML file
        net = sumolib.net.readNet('reroute.net.xml')

        # create dictionaries for easy lookup of node indices and IDs (names)
        convertNodeIDtoNodeIndex = {}
        convertNodeIndexToNodeID = {}
        # create an adjacency matrix of the road network
        # for routing and cooperation purposes
        # matrix elements contain edge length for existing edges, 0 otherwise
        adjacencyMatrix = [[0 for x in range(numberOfNodesinNetwork)] \
            for x in range(numberOfNodesinNetwork)]
        # create additional adjacency matrix containing the corresponding edge IDs
        adjacencyEdgeID = [["" for x in range(numberOfNodesinNetwork)] \
            for x in range(numberOfNodesinNetwork)]
        for fromNode in range(numberOfNodesinNetwork):
            fromNodeID = nodes[fromNode]
            # fill node dictionaries by the way
            convertNodeIndexToNodeID[fromNode]=fromNodeID
            convertNodeIDtoNodeIndex[fromNodeID]=fromNode
            for toNode in range(numberOfNodesinNetwork):
                toNodeID   = nodes[toNode]
                for edge in edges:
                    if (net.getEdge(edge).getFromNode().getID()==fromNodeID and
                        net.getEdge(edge).getToNode().getID()==toNodeID):
                        adjacencyMatrix[fromNode][toNode] = \
                            net.getEdge(edge).getLength()
                        adjacencyEdgeID[fromNode][toNode] = \
                            str(net.getEdge(edge).getID())

        # create a dictionary for easy lookup of opposite edges to any edge
        oppositeEdgeID = dict( filter(
                lambda (x,y): net.getEdge(x).getToNode().getID() == net.getEdge(y).getFromNode().getID() and
                              net.getEdge(x).getFromNode().getID() == net.getEdge(y).getToNode().getID(),
                itertools.permutations(edges, 2)
        ))

        # counter for parking spaces during creation
        parkingSpaceNumber=0
        # create empty list for parking spaces
        parkingSpaces = []
        for edge in edges:
            # get length of each edge (somehow TraCI can only get lane lengths,
            # therefore the id string modification)
            length = traci.lane.getLength(edge+"_0")
            # if an edge is at least 40 meters long, start at 18 meters and
            # create parking spaces every 7 meters until up to 10 meters before the
            # edge ends.
            #     (vehicles can only 'see' parking spaces once they are on the same
            #     edge;
            #     starting at 18 meters ensures the vehicles can safely stop at the
            #     first parking space if it is available)
            if length > 40.0:
                position = 18.0
                # as long as there are more than 10 meters left on the edge, add
                # another parking space
                while position < (traci.lane.getLength(edge+"_0")-10.0):
                    parkingSpaces.append(ParkingSpace(parkingSpaceNumber, edge,
                        position))
                    # also add SUMO poi for better visualization in the GUI
                    traci.poi.add("ParkingSpace" + str(parkingSpaceNumber),
                        traci.simulation.convert2D(edge,(position-2.0))[0],
                        traci.simulation.convert2D(edge,(position-2.0))[1],
                        (255,0,0,0))
                    # increment counter
                    parkingSpaceNumber+=1
                    # go seven meters ahead on the edge
                    position+=7.0

        # mark a number parking spaces as available as specified per command line
        # argument
        for i in range(0, self._args.parkingspaces):
            # check whether we still have enough parking spaces to make available
            if self._args.parkingspaces > parkingSpaceNumber:
                print("Too many parking spaces for network.")
                #exit() #TODO remove this exit, wtf?! Btw, this error handling should probably occur _before_ running the simulation!
            # select a random parking space which is not yet available, and make it
            # available
            success = False
            while not success:
                availableParkingSpaceID = int(random.random()*parkingSpaceNumber)
                if not parkingSpaces[availableParkingSpaceID].available:
                    success = True
            # make sure the available parking space is not assigned to any vehicle
            parkingSpaces[availableParkingSpaceID].unassign()

        # create empty list for parking search vehicles
        l_parkingSearchVehicles=[]

        # prepare dictionaries with vehicle O/D data (IDs and indices)
        # by parsing the generated route XML file
        vehicleOriginNode = {}
        vehicleOriginNodeIndex = {}
        vehicleDestinationNode = {}
        vehicleDestinationNodeIndex = {}
        allVehicleIDs = []
        allOriginNodeIndices = []
        allDestinationNodeIndices = []
        for trip in sumolib.output.parse_fast( \
            "reroute.rou.xml", 'trip', ['id','from','to']):
            allVehicleIDs.append(trip.id)
            vehicleOriginNode[trip.id] =  \
                net.getEdge(trip.attr_from).getFromNode().getID()
            vehicleOriginNodeIndex[trip.id] = \
                convertNodeIDtoNodeIndex[vehicleOriginNode[trip.id]]
            vehicleDestinationNode[trip.id] = \
                net.getEdge(trip.to).getToNode().getID()
            vehicleDestinationNodeIndex[trip.id] = \
                convertNodeIDtoNodeIndex[vehicleDestinationNode[trip.id]]
            allOriginNodeIndices.append(vehicleOriginNodeIndex[trip.id])
            allDestinationNodeIndices.append(vehicleDestinationNodeIndex[trip.id])

        # use Aleksandar's Cooperative Search Router to create a dictionary
        # containing all cooperative vehicle routes (only once in advance)
        coopRouter = CooperativeSearch(adjacencyMatrix, allOriginNodeIndices)
        shortestNeighbors = coopRouter.shortest()

        l_cooperativeRoutes = dict(map(
            lambda trip: ( allVehicleIDs[trip], self.convertNodeSequenceToEdgeSequence(
                adjacencyEdgeID,coopRouter.reconstruct_path(
                            shortestNeighbors[trip],allDestinationNodeIndices[trip],
                            allOriginNodeIndices[trip])) ),
                xrange(len(allVehicleIDs))
        ))

        # use Aleksandar's Cooperative Search Router to create a dictionary
        # containing all non-cooperative vehicle routes (only once in advance)
        indyRouter = CooperativeSearch(adjacencyMatrix, allOriginNodeIndices, 0)
        indyShortestNeighbors = indyRouter.shortest()

        l_individualRoutes = dict(map(
            lambda trip: ( allVehicleIDs[trip], self.convertNodeSequenceToEdgeSequence(
                adjacencyEdgeID,indyRouter.reconstruct_path(
                            indyShortestNeighbors[trip],allDestinationNodeIndices[trip],
                            allOriginNodeIndices[trip]))
            ),
            xrange(len(allVehicleIDs))
        ))

        # create lists for search time and distance results
        searchTimes = []
        searchDistances = []

        # do simulation time steps as long as vehicles are present in the network
        while traci.simulation.getMinExpectedNumber() > 0:
            # tell SUMO to do a simulation step
            traci.simulationStep()
            # increase local time counter
            step += 1
            # every 1000 steps: ensure local time still corresponds to SUMO
            # simulation time
            # (just a safety check for now, can possibly be removed later)
            if step != (traci.simulation.getCurrentTime()/1000):
                print("TIMESTEP ERROR", step, "getCurrentTime",
                        traci.simulation.getCurrentTime())
            # if a new vehicle has departed in SUMO, create the corresponding Python
            # representation
            l_departedVehicles = traci.simulation.getDepartedIDList()
            l_parkingSearchVehicles.extend(map(
                    lambda vehID: ParkingSearchVehicle( vehID, self._args.coopratio, step,
                                                        l_cooperativeRoutes[vehID], l_individualRoutes[vehID] ),
                    l_departedVehicles
            ))

            # if a vehicle has disappeared in SUMO, remove the corresponding Python
            # representation
            for vehID in traci.simulation.getArrivedIDList():
                    # for now: output to console that the vehicle disappeared upon
                    # reaching the destination
                print(str(vehID),
                        "did not find an available parking space during phase 2.")
                l_parkingSearchVehicles.remove(ParkingSearchVehicle(vehID))
            # update status of all vehicles
            # TODO: differentiate this update method into e.g.
            #       getVehicleData() ..... all TraCI getSomething commands
            #       computeRouting() ..... non-cooperative routing
            #       computeCoopRouting() . cooperative routing
            #       selectRouting() ...... select whether to cooperate or not
            #       setVehicleData() ..... all TraCI setSomething commands
            for psv in l_parkingSearchVehicles:
                result = psv.update(parkingSpaces, oppositeEdgeID, step)
                # if result values could be obtained, the vehicle found
                # a parking space in the last time step
                if result:
                    searchTimes.append(result[1])
                    searchDistances.append(result[2])
                else:
                    # if the vehicle is on the last route segment,
                    # choose one of the possible next edges to continue
                    if psv.isOnLastRouteSegment():
                        currentRoute = psv.getVehicleRoute()
                        succEdges = \
                            net.getEdge(currentRoute[-1]).getToNode().getOutgoing()
                        succEdgeIDs = []
                        for edge in succEdges:
                            succEdgeIDs.append(str(edge.getID()))
                        if currentRoute[-1] in oppositeEdgeID:
                            succEdgeIDs.remove(oppositeEdgeID[currentRoute[-1]])
                        nextRouteSegment = random.choice(succEdgeIDs)
                        psv.setNextRouteSegment(nextRouteSegment)

            # break the while-loop if all remaining SUMO vehicles have
            # successfully parked
            if self.getNumberOfRemainingVehicles(l_parkingSearchVehicles)==0:
                print("SUCCESSFULLY PARKED:",
                    self.getNumberOfParkedVehicles(l_parkingSearchVehicles),
                    "OUT OF", self._args.psv)
                break

        # (from SUMO examples):
        # close the TraCI control loop
        traci.close()
        sys.stdout.flush()

        l_sumoProcess.wait()

        # Return results
        return self.getNumberOfParkedVehicles(l_parkingSearchVehicles), searchTimes, searchDistances


    ## Convert a route given as sequence of node indices into the corresponding
    #  sequence of edge IDs
    #  @param adjacencyEdgeID adjacency matrix containing the edge IDs
    #  @param nodeSequence route given as node index list
    #  @return edgeSequence route given as edge ID list
    def convertNodeSequenceToEdgeSequence(self, adjacencyEdgeID, nodeSequence):
        edgeSequence = []
        for segment in range(0, len(nodeSequence)-1):
            nextEdge=adjacencyEdgeID[nodeSequence[segment]][nodeSequence[segment+1]]
            if nextEdge=="":
                print("ERROR: could not convert node sequence to edge sequence.")
                #exit() #TODO remove this exit, wtf?!
            else:
                edgeSequence.append(nextEdge)
        return edgeSequence

    ## Get number of remaining searching vehicles
    #  @param psvList List of parking search vehicle objects
    #  @return Number of remaining vehicles which are not parked
    def getNumberOfRemainingVehicles(self, psvList):
        if not psvList:
            return 0

        remainingVehicles = 0
        for psv in psvList:
            if not psv.getParkedStatus():
                remainingVehicles += 1
        return remainingVehicles


    ## Get number of successfully parked vehicles
    #  @param psvList List of parking search vehicle objects
    #  @return Number of parked vehicles
    def getNumberOfParkedVehicles(self, psvList):
        if not psvList:
            return 0

        parkedVehicles = 0
        for psv in psvList:
            if  psv.getParkedStatus():
                parkedVehicles += 1
        return parkedVehicles


