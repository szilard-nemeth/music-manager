from dataclasses import dataclass
from enum import Enum


class MusicManagerEnvVar(Enum):
    PROJECT_DETERMINATION_STRATEGY = "PROJECT_DETERMINATION_STRATEGY"


@dataclass
class Duration:
    UNKNOWN = -1

    orig_seconds: int
    seconds: int = None
    minutes: int = None

    def __post_init__(self):
        if self.orig_seconds != Duration.UNKNOWN:
            self.minutes, self.seconds = divmod(self.orig_seconds, 60)
            self.hours = divmod(self.minutes, 60)
        else:
            self.minutes = 0
            self.seconds = 0

    @staticmethod
    def unknown():
        return Duration(Duration.UNKNOWN)

    def is_unknown(self):
        return self.seconds == Duration.UNKNOWN
