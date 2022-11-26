import re
import time
from enum import IntEnum


def is_valid_name(name: str) -> bool:
    regex = re.compile(r'([a-zA-Z_0-9][a-zA-Z_\-0-9]+[a-zA-Z_0-9])+')
    return re.fullmatch(regex, name) is not None


def validate_nip05(name: str):
    parts = name.split('@')
    print(parts)
    if len(parts) == 2:
        if parts[0] == '_':
            test_str = 'test@{}'.format(parts[1])
        else:
            test_str = name
    else:
        test_str = 'test@{}'.format(parts[0])
        parts.insert(0, '_')
    regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
    print(test_str)
    if re.fullmatch(regex, test_str) is not None:
        return parts
    else:
        return False


def is_valid_relay(url: str) -> bool:
    regex = re.compile(
        r'^wss?://' 
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.fullmatch(regex, url) is not None


def is_hex_key(k):
    return len(k) == 64 and all(c in '1234567890abcdefABCDEF' for c in k)


class TimePeriod(IntEnum):
    HOUR = 60*60
    DAY = 60*60*24
    WEEK = 60*60*24*7


def timestamp_minus(period: TimePeriod, multiplier: int = 1):
    now = int(time.time())
    return now - (period * multiplier)

