import logging
import traceback

import requests

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import is_nip05, is_bech32_key, bech32_to_hex64

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

class Nip5:

    def __init__(self, nip5):
        self.nip5 = nip5
        self.name = None
        self.address = None
        self.pk = self.fetch()

    def is_valid_format(self):
        parts = is_nip05(self.nip5)
        if parts:
            self.name = parts[0]
            self.address = parts[1]
            return True
        return False

    def match(self, pk):
        if self.pk is not None and self.pk == pk:
            return True
        elif is_bech32_key('npub', self.pk):  # we shouldn't need this as it's not valid to use bech32 but some services are currently using it
            if bech32_to_hex64('npub', self.pk) == pk:
                return True
        return False

    def fetch(self):
        if self.is_valid_format():
            try:
                url = 'https://{}/.well-known/nostr.json'.format(self.address)
                logger.info('request: {}'.format(url))
                response = requests.get(
                    url, params={'name': self.name}, timeout=2, headers={'User-Agent': 'Bija Nostr Client'}
                )
                logger.info('response staus: {}'.format(response.status_code))
                if response.status_code == 200:
                    try:
                        d = response.json()
                        logger.info('response.json: {}'.format(d))
                        logger.info('search name: [{}]'.format(self.name))
                        if self.name in d['names']:
                            logger.info('name found: {}'.format(self.name))
                            return d['names'][self.name]
                        elif self.name.lower() in d['names']:
                            logger.info('name found: {}'.format(self.name.lower()))
                            return d['names'][self.name.lower()]
                    except ValueError:
                        return None
                    except Exception as e:
                        logging.error(traceback.format_exc())
                else:
                    return None
            except ConnectionError:
                return None
            except Exception as e:
                logging.error(traceback.format_exc())
                return None
        else:
            return None

