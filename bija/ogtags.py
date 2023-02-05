import json
import logging
import urllib
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.request import Request

import validators
from bs4 import BeautifulSoup

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import request_url_head
from bija.settings import SETTINGS

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class OGTags:

    def __init__(self, data):
        logger.info('OG TAGS')
        self.note_id = data['note_id']
        self.url = data['url']
        self.og = {}
        self.note = DB.get_note(SETTINGS.get('pubkey'), self.note_id)
        self.response = None

        self.fetch()
        if self.response:
            self.process()

    def fetch(self):
        logger.info('fetch for {}'.format(self.url))
        req = Request(self.url, headers={'User-Agent': 'Bija Nostr Client'})
        h = request_url_head(self.url)
        if h:
            if h.get('content-type').split(';')[0] == 'text/html':
                try:
                    with urllib.request.urlopen(req, timeout=2) as response:
                        if response.status == 200:
                            self.response = response.read()
                except HTTPError as error:
                    print(error.status, error.reason)
                except URLError as error:
                    print(error.reason)
                except TimeoutError:
                    print("Request timed out")

    def process(self):
        logger.info('process {}'.format(self.url))
        if self.response is not None:
            soup = BeautifulSoup(self.response, 'html.parser')
            for prop in ['image', 'title', 'description', 'url']:
                item = soup.find("meta", property="og:{}".format(prop))
                if item is not None:
                    content = item.get("content")
                    if content is not None:
                        if prop in ['url', 'image']:
                            if validators.url(content):
                                self.og[prop] = content
                        else:
                            self.og[prop] = content

            if len(self.og) > 0:
                if 'url' not in self.og:
                    self.og['url'] = self.url
                self.store()

    def store(self):
        logger.info('store OG')
        media = json.loads(self.note['media'])
        media.append([self.og, 'og'])
        DB.update_note_media(self.note_id, json.dumps(media))
