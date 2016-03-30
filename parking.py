#!/usr/bin/env python
from __future__ import print_function

import argparse
import jsoncfg, json
import os

from runtime import runner
from runtime import configuration



# Main entry point for the wrapper module.
# For now: starts repetitive simulation runs with identical parameters, 
# and presents the results afterwards.
if __name__ == "__main__":
    l_configdir = os.path.expanduser(u"~/.parkingsearch")
    l_parser = argparse.ArgumentParser(description="Process parameters for headless simulation runs.")
    l_parser.add_argument("--config", dest="config", type=str, default=os.path.join(l_configdir, u"config.json"))
    l_parser.add_argument("-p","--parkingspaces", dest="parkingspaces", type=int, help="number of available parking spaces")
    l_parser.add_argument("-s","--parking-search-vehicles", dest="psv", type=int, help="number of parking search vehicles")
    l_parser.add_argument("-c","--cooperative-ratio", dest="coopratio", type=float, help="cooperative driver ratio [0,1]")
    l_parser.add_argument("--port", dest="sumoport", type=int, help="port used for communicating with sumo instance")
    l_parser.add_argument("--load-route-file", dest="routefile", type=str, help="provide a route file (SUMO xml format), overrides use of auto-generated routes")
    l_parser.add_argument("--resourcedir", dest="resourcedir", type=str, help="base directory, relative to current working directory, for reading/writing temporary and SUMO related files (default: resources)")
    l_parser.add_argument("-r","--runs", dest="runs", type=int, help="number of iterations to run")
    l_parser.add_argument("--fixedseed", dest="fixedseed", type = int, help="flag whether random number generator get run number as fixed seed")

    # if display GUI, restrict to one run (implies --run 1)
    # for more than one run, disallow use of --gui
    l_parser.add_argument("--headless", dest="headless", default=False, action='store_true', help="start simulation in headless mode without SUMO GUI")

    l_args = l_parser.parse_args()

    # raise exception if gui mode requested with > 1 run
    if not l_args.headless and l_args.runs > 1:
        message = "Number of runs can't exceed 1, if run in GUI mode."
        raise argparse.ArgumentTypeError(message)

    # raise exception if headless mode requested  AND number of parking spaces < vehicles
    # in the static case this produces an endless loop of at least one vehicle searching for a free space.
    # In Gui mode this behavior is acceptable
    if l_args.headless and l_args.parkingspaces < l_args.psv:
        message = "Number of parking spaces must be at least equal to number of vehicles, if run in headless mode."
        raise argparse.ArgumentTypeError(message)

    # raise an exception if provided basedir does not exist
    if l_args.resourcedir and not os.path.isdir(l_args.resourcedir):
        message = "The provided directory {} does not exist for argument --resourcedir".format(l_args.resourcedir)
        raise argparse.ArgumentTypeError(message)



    l_config = configuration.Configuration(l_args, l_configdir)

    print(l_config.get("simulation"))



    l_resultSum = 0

    l_successesSum       = 0
    l_searchTimesSum     = 0
    l_searchDistancesSum = 0.0

    l_runtime = runner.Runtime(l_config)

    for i_run in xrange(l_config.get("simulation").get("runs")):
        print("RUN:", i_run+1, "OF", l_config.get("simulation").get("runs"))
        l_successes, l_searchTimes, l_searchDistances = l_runtime.run(i_run)

        l_successesSum += l_successes
        l_searchTimesSum += sum(l_searchTimes) #/ float(len(searchTimes))
        l_searchDistancesSum += sum(l_searchDistances) #/ float(len(searchDistances))

    l_successRate = 100*l_successesSum/(l_config.get("simulation").get("runs")*l_config.get("simulation").get("vehicles"))
    print("")
    print("==== SUMMARY AFTER", l_config.get("simulation").get("runs"), "RUNS ====")
    print("PARAMETERS:        ", l_config.get("simulation").get("parkingspaces"), "parking spaces")
    print("                   ", l_config.get("simulation").get("vehicles"), "searching vehicles")
    print("                   ", l_config.get("simulation").get("cooperation")*100, "percent of drivers cooperate")
    print("TOTAL SUCCESS RATE:", l_successRate, "percent",
        "of cars found an available parking space")
    print("")

    if l_successesSum:
        l_searchTimesAvg = l_searchTimesSum / float(l_successesSum)
        l_searchDistancesAvg = l_searchDistancesSum / float(l_successesSum)
        print("AVG SEARCH TIME    ", l_searchTimesAvg, "seconds")
        print("AVG SEARCH DISTANCE", l_searchDistancesAvg, "meters")
    print("")

