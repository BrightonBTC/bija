import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import timestamp_minus
from bija.settings import SETTINGS

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class FeedThread:
    def __init__(self, notes):
        logger.info('FEED THREAD')
        self.tm = time.time()
        self.notes = notes
        self.processed_notes = []
        self.threads = []
        self.roots = []
        self.ids = set()
        self.last_ts = int(time.time())
        print('--------------- 1', self.tm - time.time())
        self.get_roots()
        self.construct_threads()
        print('--------------- 8', self.tm - time.time())

    def get_roots(self):
        logger.info('get roots')
        roots = []
        print('--------------- 2', self.tm - time.time())
        for note in self.notes:
            note = dict(note)
            self.last_ts = note['created_at']
            if note['reshare'] is not None and len(note['content'].strip()) < 1:
                roots.append(note['reshare'])
                note['boost'] = True
                self.add_id(note['reshare'])
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
        print('--------------- 3', self.tm - time.time())
        ids = [n['id'] for n in self.notes]

        fids = [x for x in self.roots if x not in ids]
        extra_notes = DB.get_feed(int(time.time()), SETTINGS.get('pubkey'), {'id_list': fids})
        print('--------------- 4', self.tm - time.time())
        if extra_notes is not None:
            self.processed_notes += extra_notes
        print('--------------- 5', self.tm - time.time())
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
        print('--------------- 6', self.tm - time.time())
        for note in self.processed_notes:
            note = dict(note)
            if note['reshare'] is not None and 'boost' not in note:
                print('============ a', self.tm - time.time())
                reshare = DB.get_note(SETTINGS.get('pubkey'), note['reshare'])
                self.add_id(note['reshare'])
                if reshare is not None:
                    note['reshare'] = reshare
                print('============ b', self.tm - time.time())
            print('============ c', self.tm - time.time())
            thread = next((sub for sub in self.threads if sub['id'] == note['id']), None)
            print('============ d', self.tm - time.time())
            if thread is not None:
                thread['self'] = note
            elif note['thread_root'] is not None:
                print('============ e', self.tm - time.time())
                thread = next((sub for sub in self.threads if sub['id'] == note['thread_root']), None)
                if thread is not None:
                    if thread['response'] is None:
                        thread['response'] = note
                    if note['public_key'] not in thread['responders']:
                        thread['responder_count'] += 1
                    if len(thread['responders']) < 2:
                        thread['responders'][note['public_key']] = note['name']
                print('============ f', self.tm - time.time())
            elif 'boost' in note:
                print('============ g', self.tm - time.time())
                thread = next((sub for sub in self.threads if sub['id'] == note['reshare']), None)
                if thread is not None:
                    if note['public_key'] not in thread['boosters']:
                        thread['booster_count'] += 1
                    if len(thread['boosters']) < 2:
                        thread['boosters'][note['public_key']] = note['name']
                if thread['self'] is None:
                    thread['self'] = thread['id']
                print('============ h', self.tm - time.time())
        print('--------------- 7', self.tm - time.time())

    def add_id(self, note_id):
        logger.info('add id: {}'.format(note_id))
        if note_id not in self.ids:
            self.ids.add(note_id)

class NoteThread:
    def __init__(self, note_id):
        logger.info('NOTE THREAD')
        self.id = note_id
        self.is_root = False
        self.root = []
        self.root_id = note_id
        self.public_keys = []
        self.note = self.get_note()
        self.ancestors = []
        self.children = []
        self.note_ids = [self.id]
        self.profiles = []
        self.determine_root()
        self.notes = self.get_notes()
        self.process()
        self.get_profile_briefs()
        self.result_set = self.root+self.ancestors+[self.note]+self.children

    def process(self):
        logger.info('process')
        self.get_children()

        if not self.is_root:
            self.get_root()

        if self.note is not None and type(self.note) == dict and self.note['response_to'] is not None:
            self.get_ancestor(self.note['response_to'])

        if len(self.children) > 0 and type(self.note) == dict:
            self.note['class'] = self.note['class'] + ' ancestor'

        if len(self.root) > 0 and type(self.root[0]) == dict:
            self.root[0]['class'] = self.root[0]['class'] + ' ancestor'

    def get_note(self):
        logger.info('get note')
        n = DB.get_note(SETTINGS.get('pubkey'), self.id)
        if n is not None:
            n = dict(n)
            n['current'] = True
            if n['thread_root'] is None:
                self.is_root = True
                n['class'] = 'main root'
            else:
                self.is_root = False
                n['class'] = 'main'
            n['reshare'] = self.get_reshare(n)
            self.add_members(n)
            return n
        return self.id

    def get_notes(self):
        logger.info('get notes')
        return DB.get_note_thread(SETTINGS.get('pubkey'), self.root_id)

    def get_children(self):
        logger.info('get children')
        to_remove = []
        for note in self.notes:
            n = dict(note)
            if n['response_to'] == self.id or (n['thread_root'] == self.id and n['response_to'] is None):
                n['reshare'] = self.get_reshare(n)
                n['class'] = 'reply'
                self.children.append(n)
                self.add_members(n)
                to_remove.append(note)
                self.note_ids.append(n['id'])
        self.remove_notes_from_list(to_remove)

    def remove_notes_from_list(self, notes: list):
        logger.info('remove used notes')
        for n in notes:
            self.notes.remove(n)

    def get_ancestor(self, note_id):
        logger.info('get ancestor')
        to_remove = []
        found = False
        for note in self.notes:
            n = dict(note)
            if n['id'] == note_id:
                n['reshare'] = self.get_reshare(n)
                n['class'] = 'ancestor'
                if n['response_to'] is not None:
                    self.get_ancestor(n['response_to'])
                self.ancestors.append(n)
                self.add_members(n)
                to_remove.append(note)
                self.note_ids.insert(0, n['id'])
                found = True
                break
        if not found and note_id != self.root_id:
            self.ancestors.append(note_id)
        self.remove_notes_from_list(to_remove)

    def get_root(self):
        logger.info('get root')
        for note in self.notes:
            n = dict(note)
            if n['id'] == self.root_id:
                n['class'] = 'root'
                n['reshare'] = self.get_reshare(n)
                self.root = [n]
                self.add_members(n)
                self.notes.remove(note)
                self.note_ids.append(n['id'])
                break
        if len(self.root) < 1:
            self.root = [self.root_id]

    def get_reshare(self, note):
        logger.info('get reshare')
        if note['reshare'] is not None:
            reshare = DB.get_note(SETTINGS.get('pubkey'), note['reshare'])
            if reshare is not None:
                return reshare
            else:
                return note['reshare']
        return None

    def determine_root(self):
        logger.info('determine root')
        if self.note is not None and type(self.note) == dict:
            if self.note['thread_root'] is not None:
                self.root_id = self.note['thread_root']

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