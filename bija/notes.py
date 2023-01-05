import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class FeedThread:
    def __init__(self, notes):
        logger.info('FEED THREAD')
        self.notes = notes
        self.threads = []
        self.roots = []
        self.ids = set()
        self.last_ts = int(time.time())

        self.get_roots()
        self.build()

    def get_roots(self):
        logger.info('get roots')
        roots = []
        for note in self.notes:
            note = dict(note)
            self.last_ts = note['created_at']
            if note['thread_root'] is not None:
                roots.append(note['thread_root'])
                self.add_id(note['thread_root'])
            elif note['response_to'] is not None:
                roots.append(note['response_to'])
                self.add_id(note['response_to'])
            elif note['thread_root'] is None and note['response_to'] is None:
                roots.append(note['id'])
                self.add_id(note['id'])

        self.roots = list(dict.fromkeys(roots))

    def add_id(self, note_id):
        logger.info('add id: {}'.format(note_id))
        if note_id not in self.ids:
            self.ids.add(note_id)

    def build(self):
        logger.info('build')
        for root in self.roots:
            t = self.build_thread(root)
            self.threads.append(t)

    def build_thread(self, root):
        logger.info('build thread')
        t = {'self': None, 'id': root, 'response': None, 'responders': {}}
        responders = []
        for _note in self.notes:
            note = dict(_note)

            is_root, is_response = self.is_in_thread(note, root)
            if is_root:
                self.notes.remove(_note)
                t['self'] = note
            elif is_response:
                self.notes.remove(_note)
                if t['response'] is None:
                    t['response'] = note
                if len(t['responders']) < 2:
                    t['responders'][note['public_key']] = note['name']
                responders.append(note['public_key'])

            if note['reshare'] is not None:
                reshare = DB.get_note(note['reshare'])
                self.add_id(note['reshare'])
                if reshare is not None:
                    note['reshare'] = reshare

        responders = list(dict.fromkeys(responders))
        t['responder_count'] = len(responders)

        if t['self'] is None:
            t['self'] = DB.get_note(root)
            if t['self'] is not None:
                t['self'] = dict(t['self'])
                if t['self']['reshare'] is not None:
                    reshare = DB.get_note(t['self']['reshare'])
                    self.add_id(t['self']['reshare'])
                    if reshare is not None:
                        t['self']['reshare'] = reshare
        return t


    @staticmethod
    def is_in_thread(note, root):
        is_root = False
        is_response = False
        if note['id'] == root:
            is_root = True
        elif note['response_to'] == root or note['thread_root'] == root:
            is_response = True
        return is_root, is_response


class NoteThread:
    def __init__(self, note_id):
        logger.info('NOTE THREAD')
        self.id = note_id
        self.is_root = False
        self.root = []
        self.root_id = note_id
        self.note = self.get_note()
        self.ancestors = []
        self.children = []
        self.note_ids = [self.id]
        self.public_keys = []
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
        n = DB.get_note(self.id)
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
            return n
        return self.id

    def get_notes(self):
        logger.info('get notes')
        return DB.get_note_thread(self.root_id)

    def get_children(self):
        logger.info('get children')
        to_remove = []
        for note in self.notes:
            n = dict(note)
            if n['response_to'] == self.id or (n['thread_root'] == self.id and n['response_to'] is None):
                self.children.append(n)
                self.add_members(n)
                to_remove.append(note)
                n['reshare'] = self.get_reshare(n)
                n['class'] = 'reply'
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
                self.ancestors.insert(0, n)
                self.add_members(n)
                to_remove.append(note)
                self.note_ids.insert(0, n['id'])
                n['reshare'] = self.get_reshare(n)
                n['class'] = 'ancestor'
                if n['response_to'] is not None:
                    self.get_ancestor(n['response_to'])
                found = True
                break
        if not found and note_id != self.root_id:
            self.ancestors.insert(0, note_id)
        self.remove_notes_from_list(to_remove)

    def get_root(self):
        logger.info('get root')
        for note in self.notes:
            n = dict(note)
            if n['id'] == self.root_id:
                self.root = [n]
                self.add_members(n)
                self.notes.remove(note)
                self.note_ids.append(n['id'])
                n['class'] = 'root'
                n['reshare'] = self.get_reshare(n)
                break

    def get_reshare(self, note):
        logger.info('get reshare')
        if note['reshare'] is not None:
            reshare = DB.get_note(note['reshare'])
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
