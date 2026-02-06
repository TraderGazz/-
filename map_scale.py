def calculate_spn(toponym):
    envelope = toponym["boundedBy"]["Envelope"]
    lower_corner = list(map(float, envelope["lowerCorner"].split()))
    upper_corner = list(map(float, envelope["upperCorner"].split()))
    delta_longitude = abs(upper_corner[0] - lower_corner[0])
    delta_latitude = abs(upper_corner[1] - lower_corner[1])
    return f"{delta_longitude},{delta_latitude}"


def calculate_map_center_and_spn(point1, point2):
    lon1, lat1 = map(float, point1)
    lon2, lat2 = map(float, point2)

    center_lon = (lon1 + lon2) / 2
    center_lat = (lat1 + lat2) / 2

    delta_lon = abs(lon1 - lon2) * 1.5
    delta_lat = abs(lat1 - lat2) * 1.5

    if delta_lon < 0.005:
        delta_lon = 0.005
    if delta_lat < 0.005:
        delta_lat = 0.005

    return f"{center_lon},{center_lat}", f"{delta_lon},{delta_lat}"


def calculate_distance(point1, point2):
    from math import radians, sin, cos, sqrt, atan2

    lon1, lat1 = map(float, point1)
    lon2, lat2 = map(float, point2)

    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    radius = 6371000
    return c * radius