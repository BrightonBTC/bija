import re
import time
from enum import IntEnum


def is_valid_name(name: str) -> bool:
    regex = re.compile(r'([a-zA-Z_0-9][a-zA-Z_\-0-9]+[a-zA-Z_0-9])+')
    return re.fullmatch(regex, name) is not None


def is_valid_nip05(name: str) -> bool:
    regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
    return re.fullmatch(regex, name) is not None


def is_hex_key(k):
    return len(k) == 64 and all(c in '1234567890abcdefABCDEF' for c in k)


class TimePeriod(IntEnum):
    HOUR = 60*60
    DAY = 60*60*24
    WEEK = 60*60*24*7


def timestamp_minus(period: TimePeriod, multiplier: int = 1):
    now = int(time.time())
    return now - (period * multiplier)

