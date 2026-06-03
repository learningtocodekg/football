FIELD_WIDTH = 53.3   # yards, sideline to sideline (x-axis)
FIELD_LENGTH = 120.0  # yards, including both 10-yd end zones (y-axis)
END_ZONE_DEPTH = 10.0


def in_bounds(x: float, y: float) -> bool:
    return 0.0 <= x <= FIELD_WIDTH and 0.0 <= y <= FIELD_LENGTH
