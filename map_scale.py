def calculate_spn(toponym):

    envelope = toponym["boundedBy"]["Envelope"]

    lower_corner = list(map(float, envelope["lowerCorner"].split()))
    upper_corner = list(map(float, envelope["upperCorner"].split()))

    delta_longitude = abs(upper_corner[0] - lower_corner[0])
    delta_latitude = abs(upper_corner[1] - lower_corner[1])

    return f"{delta_longitude},{delta_latitude}"