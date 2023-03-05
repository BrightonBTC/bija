import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.settings import SETTINGS

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class FeedThread:
    def __init__(self, notes):
        logger.info('FEED THREAD')
        self.notes = notes
        self.processed_notes = []
        self.threads = []
        self.roots = []
        self.ids = set()
        self.last_ts = int(time.time())
        self.get_roots()
        self.construct_threads()

    def get_roots(self):
        logger.info('get roots')
        roots = []
        for note in self.notes:
            note = dict(note)
            self.last_ts = note['created_at']
            if note['reshare'] is not None:
                self.add_id(note['reshare'])
                if len(note['content'].strip()) < 1:
                    roots.append(note['reshare'])
                    note['boost'] = True
                else:
                    roots.append(note['id'])
            elif note['thread_root'] is not None:
                roots.append(note['thread_root'])
                self.add_id(note['thread_root'])
            elif note['response_to'] is not None:
                roots.append(note['response_to'])
                self.add_id(note['response_to'])
            elif note['thread_root'] is None and note['response_to'] is None:
                roots.append(note['id'])
                self.add_id(note['id'])
            self.processed_notes.append(note)
        self.roots = list(dict.fromkeys(roots))
        ids = [n['id'] for n in self.notes]

        fids = [x for x in self.roots if x not in ids]
        extra_notes = DB.get_feed(int(time.time()), SETTINGS.get('pubkey'), {'id_list': fids})
        if extra_notes is not None:
            self.processed_notes += extra_notes
        for root in self.roots:
            self.threads.append({
                'self': None,
                'id': root,
                'response': None,
                'responders': {},
                'responder_count': 0,
                'boosters':{},
                'booster_count': 0
            })

    def construct_threads(self):
        for note in self.processed_notes:
            note = dict(note)
            if note['reshare'] is not None and 'boost' not in note:
                self.add_id(note['reshare'])
            thread = next((sub for sub in self.threads if sub['id'] == note['id']), None)
            if thread is not None:
                thread['self'] = note
            elif note['thread_root'] is not None:
                thread = next((sub for sub in self.threads if sub['id'] == note['thread_root']), None)
                if thread is not None:
                    if thread['response'] is None:
                        thread['response'] = note
                    if note['public_key'] not in thread['responders']:
                        thread['responder_count'] += 1
                    if len(thread['responders']) < 2:
                        thread['responders'][note['public_key']] = note['name']
            elif 'boost' in note:
                thread = next((sub for sub in self.threads if sub['id'] == note['reshare']), None)
                if thread is not None:
                    if note['public_key'] not in thread['boosters']:
                        thread['booster_count'] += 1
                    if len(thread['boosters']) < 2:
                        thread['boosters'][note['public_key']] = note['name']
                if thread['self'] is None:
                    thread['self'] = thread['id']

    def add_id(self, note_id):
        logger.info('add id: {}'.format(note_id))
        if note_id not in self.ids:
            self.ids.add(note_id)

class NoteThread:
    def __init__(self, note_id):
        logger.info('NOTE THREAD')
        self.id = note_id
        self.is_root = False
        self.root_id = None
        self.profiles = []
        self.note_ids = [self.id]
        self.public_keys = []
        self.note = None
        self.root = None
        self.parent = None
        self.replies = []

        self.process()


    def process(self):
        self.get_note()
        if not self.is_root:
            self.determine_root()
            self.get_root()
            if self.note is not None and 'response_to' in self.note:
                self.get_parent()

        self.get_replies()

        self.get_profile_briefs()


    def get_note(self):
        logger.info('get note')
        n = DB.get_note(SETTINGS.get('pubkey'), self.id)
        if n is not None:
            n = dict(n)
            n['current'] = True
            if n['thread_root'] is None:
                self.is_root = True
                self.root_id = self.id
                n['class'] = 'main root'
                n['reshare'] = self.get_reshare(n)
                self.root = n
            else:
                n['class'] = 'main'
                n['reshare'] = self.get_reshare(n)
                self.note = n
            self.add_members(n)
        else:
            self.note = self.id


    def get_parent(self):
        logger.info('get parent')
        p = DB.get_note(SETTINGS.get('pubkey'), self.note['response_to'])
        if p is not None:
            p = dict(p)
            p['reshare'] = self.get_reshare(p)
            p['class'] = 'ancestor'
            self.add_members(p)
            self.note_ids.append(p['id'])
            self.parent = p
        else:
            self.parent = self.note['response_to']

    def get_replies(self):
        logger.info('get replies')
        replies = DB.get_feed(int(time.time()), SETTINGS.get('pubkey'), {'replies': self.id})
        if replies is not None:
            for note in replies:
                print('id', note.id)
                print('=========================', note.id)
                n = dict(note)
                print(n['thread_root'], n['response_to'])
                if n['response_to'] == self.id or (n['thread_root'] == self.id and n['response_to'] is None):
                    print('ADDED')
                    n['reshare'] = self.get_reshare(n)
                    n['class'] = 'reply'
                    self.replies.append(n)
                    self.add_members(n)
                    self.note_ids.append(n['id'])
                print('// =========================', note.id)

    def get_reshare(self, note):
        logger.info('get reshare')
        if note['reshare'] is not None:
            reshare = DB.get_note(SETTINGS.get('pubkey'), note['reshare'])
            if reshare is not None:
                return reshare
            else:
                return note['reshare']
        return None

    def add_public_keys(self, public_keys: list):
        logger.info('add pub keys')
        for k in public_keys:
            if k not in self.public_keys:
                self.public_keys.append(k)

    def get_profile_briefs(self):
        logger.info('get profile briefs')
        self.profiles = DB.get_profile_briefs(self.public_keys)

    def add_members(self, note):
        logger.info('add members')
        public_keys = [note['public_key']]
        public_keys = json.loads(note['members']) + public_keys
        self.add_public_keys(public_keys)

    def get_root(self):
        logger.info('get root')
        n = DB.get_note(SETTINGS.get('pubkey'), self.root_id)
        if n is not None:
            n = dict(n)
            n['class'] = 'root'
            n['reshare'] = self.get_reshare(n)
            self.root = n
            self.add_members(n)
            self.note_ids.append(n['id'])
        else:
            self.root = self.root_id

    def determine_root(self):
        logger.info('determine root')
        if self.note is not None and type(self.note) == dict:
            if self.note['thread_root'] is not None:
                self.root_id = self.note['thread_root']


class BoostsThread:
    def __init__(self, note_id):
        logger.info('BOOSTS THREAD')
        self.id = note_id
        self.note = DB.get_note(SETTINGS.get('pubkey'), note_id)
        self.boosts = []
        boosts = DB.get_feed(int(time.time()), SETTINGS.get('pubkey'), {'boost_id': note_id})
        for boost in boosts:
            boost = dict(boost)
            boost['reshare'] = self.note
            self.boosts.append(boost)