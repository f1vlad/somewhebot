CONFIG_FILE = "gpstrace.cfg"
OUTPUT_FILE = "gpstrace.csv"
VISIT_PING_TIME = 10 * 60   # seconds

import random
from datetime import datetime, timedelta
import csv
from ConfigParser import ConfigParser, NoOptionError

class Location(object):
    """
    A single named GPS location, with latitude, longitude, and "visit" time
    (a tuple with minimal and maximal time to "spend" on that location, in seconds;
    by default (0,0) is used). Actual time of each "visit" is choosen randomly
    between min and max.
    """

    def __init__(self, name, latitude, longitude, visit_time = None):
        if not isinstance(latitude, type(0.1)) or not isinstance(longitude, type(0.1)):
            raise TypeError("latitude and longitude must be signed, floating point numbers")
        if not visit_time:
            visit_time = (0,0)
        if not isinstance(visit_time, type(())) or len(visit_time) != 2:
            raise TypeError("visit_time must be a tuple with 2 integers - time in seconds")

        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.visit_time = visit_time

    def random_visit(self):
        return timedelta(seconds=random.randint(self.visit_time[0], self.visit_time[1]))

class Route(object):
    """
    Route with a starting and ending Location, an optional list of Locations
    between them, probability for selecting this route (a float in range 0.0
    to 1.0, default: 1.0), and a tuple of days of the week this route is "active"
    (0=Monday, 6=Sunday; default: all days - (0,1,2,3,4,5,6) ).
    """

    def __init__(self, name, start_at, end_at, waypoints=None, probability=1.0, weekdays=None):
        if not isinstance(start_at, Location):
            raise TypeError("start_at must be a Location instance")
        if waypoints and not isinstance(waypoints, (type([]))):
            raise TypeError("waypoints must be a list of Location instances")
        if not isinstance(end_at, Location):
            raise TypeError("end_at must be a Location instance")
        if not isinstance(probability, type(0.1)) or (probability < 0.0 and probability > 1.0):
            raise TypeError("probability must be a floating point number between 0.0 and 1.0")

        self.name = name
        self.start_at = start_at
        self.waypoints = waypoints or []
        for i, wp in enumerate(self.waypoints):
            if not isinstance(wp, Location):
                raise TypeError("Waypoint at index %d of route '%s' must be a Location instance" % (i, self.name))
        self.end_at = end_at
        self.probability = probability
        self.weekdays = weekdays or range(8)

    def __repr__(self):
        return  "<Route %s(%s,%s,%s,%r)>" % (self.name,self.start_at.name, self.end_at.name, self.probability, self.weekdays)
class NoAvailableRouteError(Exception):
    pass

class TravelTracer:
    """
    Simulates a GPS travel trace, using a list of defined Routes.
    """

    def __init__(self, cfgfile):
        """
        Reads the given cfgfile and initializes all locations and routes.

        Format:

        # single-line comments allowed
        [Location <name>]
        latitude = <float value>
        longitute = <float value>
        visit_time = <min time>,<max time>

        [Route <name>]
        start_at = <location name>
        end_at = <location name>
        # all these are optional:
        waypoints = <location name>, [<loc2>, ...] <last location> # default: empty list
        probability = <float> # default: 1.0
        weekdays = 0, 1, ... # Monday=0, ... Sunday=6; default: 0,1,2,3,4,5,6

        Time values can have a suffix: "h" - hours, "m" - minutes, "s" - seconds (default, if not given).
        Sections for locations must begin with "Location ", for routes with "Route " (case-sensitive)
        """

        self.user_id = None
        self.routes = []
        config = ConfigParser()
        if config.read(cfgfile):
            self.locations = {}
            route_names = []
            for section in config.sections():

                if section.startswith("Location "):
                    name = section[len("Location "):]
                    try:
                        visit_time = self.parse_visit_time(config.get(section, "visit_time"), name)
                    except NoOptionError:
                        visit_time = None
                    self.locations[name] = Location(name,
                                                    config.getfloat(section, "latitude"),
                                                    config.getfloat(section, "longitude"),
                                                    visit_time)
                elif section.startswith("Route "):
                    name = section[len("Route "):]
                    route_names.append(name)

            for route in route_names:
                section = "Route %s" % route
                waypoints = None
                probability = 1.0
                weekdays = None
                try:
                    start_at = self.locations[config.get(section, "start_at")]
                    end_at = self.locations[config.get(section, "end_at")]
                except KeyError, e:
                    raise ValueError("Undefined location %s in route '%s'" % (e, route))
                try:
                    waypoints = self.parse_waypoints(config.get(section, "waypoints"), route)
                except NoOptionError:
                    pass
                try:
                    probability = config.getfloat(section, "probability")
                except NoOptionError:
                    pass
                try:
                    weekdays = self.parse_weekdays(config.get(section, "weekdays"), route)
                except NoOptionError:
                    pass

                self.routes.append(Route(route, start_at, end_at, waypoints, probability, weekdays))

        else:
            raise Exception("Invalid config file: %s" % cfgfile)

    def parse_visit_time(self, visit_time, location):
        """
        Parses "visit_time" key in the configuration, returning a tuple with min and max (seconds).
        """

        parts = str(visit_time).replace(' ','').split(',')
        try:
            if len(parts) != 2:
                raise ValueError
            for i, part in enumerate(parts):
                if part.endswith('h'):
                    parts[i] = int(part[:-1]) * 3600
                elif part.endswith('m'):
                    parts[i] = int(part[:-1]) * 60
                elif part.endswith('s'):
                    parts[i] = int(part[:-1])
                else:
                    parts[i] = int(part)
            return tuple(parts)
        except ValueError:
            raise ValueError("Invalid visit_time '%s' for location '%s'" % (visit_time, location))

    def parse_waypoints(self, waypoints, name):
        """
        Parses a list of waypoints as a comma-delimited list of location names.
        Returns a list of Location instances.
        """

        result = []
        parts = str(waypoints).replace(' ','').split(',')
        for part in parts:
            if part in self.locations:
                result.append(self.locations[part])
            else:
                raise ValueError("Undefined location '%s' in waypoints list for route '%s'" % (part, name))
        return result

    def parse_weekdays(self, weekdays, name):
        """
        Parses a comma-delimited list of weekdays (0=Monday, 6=Sunday).
        Returns a tuple of integers.
        """

        result = []
        parts = str(weekdays).replace(' ','').split(',')
        for part in parts:
            try:
                day = int(part)
                if day < 0 or day > 6:
                    raise ValueError
                result.append(day)
            except ValueError:
                raise ValueError("Invalid weekdays for route '%s'" % name)
        return tuple(result)

    def set_user(self, user_id):
        self.user_id = user_id

    def choose_route(self, weekday, start_at):
        """
        Among all available routes, finds the one, matching start_at
        location, active on the given weekday, and having the highest
        probability. Raises NoAvailableRouteError otherwise.
        """

        max_probability = 0.0
        chosen_route = None

        for route in self.routes:
            if route.start_at == start_at and weekday in route.weekdays and route.probability > max_probability:
                max_probability = route.probability
                chosen_route = route
        if not chosen_route:
            raise NoAvailableRouteError("Starting at location '%s'" % start_at.name)

        return chosen_route

    def generate_pings(self, location, start_time, visit_time):
        Tc = start_time
        end_time = start_time + visit_time
        pings = []
        while Tc < end_time:
            pings.append(Tc)
            Tc += timedelta(seconds=VISIT_PING_TIME)
        return pings

    def trace(self, start_at, start_time, end_time = None):
        """
        Simulates a GPS travel trace, using the available routes.
        The process can be outlined as follows:
        1. Initially, the following is provided:
            Ls - a staring location;
            Ts - start timestamp;
            Te - end timestamp (if not given, the next day is assumed);
        2. Current timestamp (Tc) is set to Ts, current location (Lc) is set to Ls;
        3. From all available routes, active for the weekday at Tc and starting
        at Lc, the one with the highest probability is chosen;
        4. If a route cannot be chosen, the trace is interrupted.
        5. The chosen route is traced from its starting location, through its
        waypoints (if any), to its ending location (Le). On each step,
        random_visit() on each passed location is called (Tv);
        6. During the time between Tc and Tc+Tv, one point is generated each
        VISIT_PING_TIME seconds; The next location/waypoint is next, etc.
        until the end location is reached;
        7. Lc is set to the chosen route's end location;
        8. If Tc is less than Te, go to step 3, otherwise trace is completed.

        The result of the trace is returned as a list of 2-element tuples (visited
        location instance and timestamp of the visit).
        """

        if not isinstance(start_at, Location):
            raise TypeError("start_at must be a Location instance")
        if not isinstance(start_time, datetime):
            raise TypeError("start_time must be a datetime instance")
        if not end_time:
            end_time = start_time + timedelta(days=1)

        points = []
        Tc = start_time
        Lc = start_at

        while Tc < end_time:
            route = self.choose_route(Tc.weekday(), Lc)

            visit_time = route.start_at.random_visit()
            for pingtime in self.generate_pings(route.start_at, Tc, visit_time):
                points.append((route.start_at, pingtime))
            Tc += visit_time

            for wp in route.waypoints:
                points.append((wp, Tc))
                Tc += wp.random_visit()

            visit_time = route.end_at.random_visit()
            for pingtime in self.generate_pings(route.end_at, Tc, visit_time):
                points.append((route.end_at, pingtime))
            Tc += visit_time

            Lc = route.end_at

        return points

    def save_trace(self, points, csvfile):
        """
        Saves the given list of trace points, returned from trace() to a CSV file.
        """
        output = csv.writer(open(csvfile, 'wb'))

        for point in points:
            loc, timestamp = point
            # only 1-second precision
            timestamp = timestamp.replace(microsecond=0)
            output.writerow([self.user_id, loc.latitude, loc.longitude, timestamp.isoformat(' ')])

if __name__ == "__main__":
    from sys import argv

    start_location = None
    start_time = datetime.now().replace(microsecond=0)
    end_time = None

    if len(argv) < 3:
        print("Usage: python %s <user id> <start location> [<start time> [<end time>]]" % argv[0])
        print("")
        print("Time format: 'YYYY-MM-DD HH:MM:SS'")
        print("Start time by default will be the current time (%s)" % start_time.isoformat(' '))
        print("If only start time is specified, end time will be +1 day")

    tt = TravelTracer(CONFIG_FILE)
    if len(argv) >= 3:
        user_id = argv[1]
        start_location = argv[2]
        tt.set_user(user_id)
        if start_location not in tt.locations:
            raise ValueError("Undefined start location '%s'" % start_location)

        if len(argv) >= 4:
            start_time = datetime.strptime(argv[3], "%Y-%m-%d %H:%M:%S")
        if len(argv) == 5:
            end_time = datetime.strptime(argv[4], "%Y-%m-%d %H:%M:%S")

        tt.save_trace(tt.trace(tt.locations[start_location], start_time, end_time), OUTPUT_FILE)