import logging
import time

from flask import request, url_for

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import is_hex_key, is_bech32_key, is_nip05, bech32_to_hex64
from bija.nip5 import Nip5

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Search:

    def __init__(self):
        logger.info('SEARCH')
        self.term = None
        self.message = None
        self.results = None
        self.redirect = None
        self.action = None

        self.process()

    def process(self):
        if 'search_term' in request.args or len(request.args['search_term'].strip()) < 1:
            self.term = request.args['search_term']
            if self.term[:1] == '#':
                self.by_hash()
            elif self.term[:1] == '@':
                self.by_at()
            elif is_hex_key(self.term):
                self.by_hex()
            elif is_bech32_key('npub', self.term):
                self.by_npub()
            elif is_bech32_key('note', self.term):
                self.by_note()
            elif is_nip05(self.term):
                self.by_nip05()
        else:
            self.message = "no search term found!"

    def by_hash(self):
        # self.message = 'Searching network for {}'.format(self.term)
        # self.results = DB.get_search_feed(int(time.time()), self.term)
        # self.action = 'hash'
        self.redirect = url_for('topic_page', topic=self.term[1:])

    def by_at(self):
        pk = DB.get_profile_by_name_or_pk(self.term[1:])
        if pk is not None:
            self.redirect = url_for('profile_page', pk=pk.public_key)

    def by_hex(self):
        self.redirect = url_for('profile_page', pk=self.term)

    def by_npub(self):
        b_key = bech32_to_hex64('npub', self.term)
        if b_key:
            self.redirect = url_for('profile_page', pk=b_key)
        else:
            self.message = 'invalid npub'

    def by_note(self):
        b_key = bech32_to_hex64('note', self.term)
        if b_key:
            self.redirect = url_for('note_page', note_id=b_key)
        else:
            self.message = 'invalid note'

    def by_nip05(self):
        profile = DB.get_pk_by_nip05(self.term)
        if profile is not None:
            self.redirect = url_for('profile_page', pk=profile.public_key)
        else:
            nip5 = Nip5(self.term)
            if nip5.pk is not None:
                self.redirect = url_for('profile_page', pk=nip5.pk)
            else:
                self.message = "Nip-05 identifier could not be located"

    def get(self):
        return self.results, self.redirect, self.message, self.action

