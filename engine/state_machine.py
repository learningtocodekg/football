from enum import Enum


class PlayPhase(Enum):
    PRE_SNAP = "PRE_SNAP"
    LIVE = "LIVE"
    BALL_IN_AIR = "BALL_IN_AIR"
    RESOLUTION = "RESOLUTION"
    END = "END"
