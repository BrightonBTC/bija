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
        self.pk = None
        self.response = None

        self.fetch()
        if self.response is not None:
            self.process()

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
        elif self.pk is not None and is_bech32_key('npub', self.pk):  # we shouldn't need this as it's not valid to use bech32 but some services are currently using it
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
                logger.info('response status: {}'.format(response.status_code))
                if response.status_code == 200:
                    self.response = response
            except requests.exceptions.HTTPError as e:
                logger.error("Http Error: {}".format(e))
                pass
            except requests.exceptions.ConnectionError as e:
                logger.error("Error Connecting:".format(e))
                pass
            except requests.exceptions.Timeout as e:
                logger.error("Timeout Error:".format(e))
                pass
            except requests.exceptions.RequestException as e:
                logger.error("OOps: Something Else".format(e))
                pass


    def process(self):
        try:
            d = self.response.json()
            logger.info('response.json: {}'.format(d))
            logger.info('search name: [{}]'.format(self.name))
            if self.name in d['names']:
                logger.info('name found: {}'.format(self.name))
                self.pk = d['names'][self.name]
            elif self.name.lower() in d['names']:
                logger.info('name found: {}'.format(self.name.lower()))
                self.pk = d['names'][self.name.lower()]
        except ValueError:
            logging.error(traceback.format_exc())
            pass
        except Exception:
            logging.error(traceback.format_exc())
            pass
