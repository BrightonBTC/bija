import json
import re
import time
import urllib
from enum import IntEnum
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

import requests
from bs4 import BeautifulSoup

from bija.ws import bech32
from bija.ws.bech32 import bech32_encode, bech32_decode, convertbits

logger = logging.getLogger(__name__)
FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(format=FORMAT)
logger.setLevel(logging.INFO)

def hex64_to_bech32(prefix: str, hex_key: str):
    if is_hex_key(hex_key):
        converted_bits = bech32.convertbits(bytes.fromhex(hex_key), 8, 5)
        return bech32_encode(prefix, converted_bits, bech32.Encoding.BECH32)


def bech32_to_hex64(prefix: str, b_key: str):
    hrp, data, spec = bech32_decode(b_key)
    if hrp != prefix:
        return False
    decoded = convertbits(data, 5, 8, False)
    key = bytes(decoded).hex()
    if not is_hex_key(key):
        return False
    return key


# TODO: regex for this
def is_bech32_key(hrp: str, key_str: str) -> bool:
    if key_str[:4] == hrp and len(key_str) == 63:
        return True
    return False


def is_valid_name(name: str) -> bool:
    regex = re.compile(r'([a-zA-Z_0-9][a-zA-Z_\-0-9]+[a-zA-Z_0-9])+')
    return re.fullmatch(regex, name) is not None


def get_at_tags(content: str) -> list[Any]:
    regex = re.compile(r'(@[a-zA-Z_0-9][a-zA-Z_\-0-9]+[a-zA-Z_0-9])+')
    return re.findall(regex, content)


def get_hash_tags(content: str) -> list[Any]:
    regex = re.compile(r'\s\B#\w*[a-zA-Z]+\w*\W')
    return re.findall(regex, ' '+content+' ')


def get_note_links(content: str) -> list[Any]:
    regex = re.compile(r'\Wnote1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}\W')
    return re.findall(regex, ' '+content+' ')


def get_embeded_tag_indexes(content: str):
    regex = re.compile(r'#\[([0-9]+)]')
    return re.findall(regex, content)


def get_urls_in_string(content: str):
    regex = re.compile(r'((https?):((//)|(\\\\))+([\w\d:#@%/;$()~_?\+-=\\\.&](#!)?)*)')
    url = re.findall(regex, content)
    return [x[0] for x in url]


def get_invoice(content: str):
    regex = re.compile(r'(lnbc[a-zA-Z0-9]*)')
    return re.search(regex, content)


def url_linkify(content):
    urls = get_urls_in_string(content)
    for url in set(urls):
        parts = url.split('//')
        if len(parts) < 2:
            parts = ['', url]
            url = 'https://' + url
        if len(parts[1]) > 21:
            link_text = parts[1][:21] + '&#8230;'
        else:
            link_text = parts[1]
        content = content.replace(
            url,
            "<a href='{}' target='blank'>{}</a>".format(url, link_text))
    return content


def strip_tags(content: str):
    return BeautifulSoup(content, features="html.parser").get_text()


def is_nip05(name: str):
    parts = name.split('@')
    if len(parts) == 2:
        if parts[0] == '_':
            test_str = 'test@{}'.format(parts[1])
        else:
            test_str = name
    else:
        test_str = 'test@{}'.format(parts[0])
        parts.insert(0, '_')

    regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
    if re.fullmatch(regex, test_str):
        return parts
    else:
        return False


def is_valid_relay(url: str) -> bool:
    regex = re.compile(
        r'^wss?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.fullmatch(regex, url) is not None


def is_hex_key(k):
    return len(k) == 64 and all(c in '1234567890abcdefABCDEF' for c in k)


class TimePeriod(IntEnum):
    HOUR = 60 * 60
    DAY = 60 * 60 * 24
    WEEK = 60 * 60 * 24 * 7

def is_json(s):
  try:
    json.loads(s)
  except ValueError as e:
    return False
  return True

def timestamp_minus(period: TimePeriod, multiplier: int = 1, start=False):
    if not start:
        start = int(time.time())
    return start - (period * multiplier)


def list_index_exists(lst, i):
    try:
        return lst[i]
    except IndexError:
        return None


def request_relay_data(url):
    parts = urlparse(url)
    url = url.replace(parts.scheme, 'https')
    get = Request(url, headers={'Accept': 'application/nostr+json'})
    try:
        with urllib.request.urlopen(get, timeout=2) as response:
            if response.status == 200:
                return response.read()
            return False
    except HTTPError as error:
        print(error.status, error.reason)
        return False
    except URLError as error:
        print(error.reason)
        return False
    except TimeoutError:
        print("Request timed out")
        return False

def request_url_head(url):
    try:
        h = requests.head(url, timeout=1)
        if h.status_code == 200:
            return h.headers
        return False
    except requests.exceptions.Timeout as e:
        logging.error(e)
        return False
    except requests.exceptions.HTTPError as e:
        logging.error(e)
        return False
    except Exception as e:
        logging.error(e)
        return False
