from dataclasses import dataclass
from enum import Enum

from logging_setup import SimpleLoggingSetup

CLI_LOG = SimpleLoggingSetup.create_command_logger("cli")


class MusicManagerEnvVar(Enum):
    PROJECT_DETERMINATION_STRATEGY = "PROJECT_DETERMINATION_STRATEGY"


@dataclass
class Duration:
    UNKNOWN = -1

    orig_seconds: int
    seconds: int = None
    minutes: int = None
    hours: int = None

    def __post_init__(self):
        if self.orig_seconds != Duration.UNKNOWN:
            self.minutes, self.seconds = divmod(self.orig_seconds, 60)
            self.hours = divmod(self.minutes, 60)
        else:
            self.seconds = 0
            self.minutes = 0
            self.hours = 0

    @staticmethod
    def unknown():
        return Duration(Duration.UNKNOWN)

    def is_unknown(self):
        return self.seconds == Duration.UNKNOWN

    @classmethod
    def of_string(cls, raw_duration):
        """
        Get seconds from time.
        """
        split_res = raw_duration.split(':')
        nums = [int(e) for e in split_res]
        hours, minutes, seconds = (0, 0, 0)
        if len(nums) == 2:
            minutes, seconds = nums
        elif len(nums) == 3:
            hours, minutes, seconds = nums
        else:
            raise ValueError("Unexpected duration format: {}".format(raw_duration))

        orig_seconds = hours * 3600 + minutes * 60 + seconds
        return Duration(orig_seconds, seconds=seconds, minutes=minutes, hours=hours)

