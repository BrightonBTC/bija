import json

from bija.app import app
from bija.db import BijaDB

DB = BijaDB(app.session)


class FeedThread:
    def __init__(self, notes):
        self.notes = notes
        self.threads = []
        self.roots = []
        self.ids = set()
        self.last_ts = None

        self.get_roots()
        self.build()

    def get_roots(self):
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
        if note_id not in self.ids:
            self.ids.add(note_id)

    def build(self):
        for root in self.roots:
            t = self.build_thread(root)
            self.threads.append(t)

    def build_thread(self, root):
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

            if (is_root or is_response) and note['reshare'] is not None:
                reshare = DB.get_note(note['reshare'])
                self.add_id(note['reshare'])
                if reshare is not None:
                    note['reshare'] = reshare

        responders = list(dict.fromkeys(responders))
        t['responder_count'] = len(responders)

        if t['self'] is None:
            t['self'] = DB.get_note(root)
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
    def __init__(self, root):
        self.root = root
        self.notes = []
        self.public_keys = []
        self.profiles = []

        self.process()
        self.get_profile_briefs()

    def process(self):
        notes = DB.get_note_thread(self.root)
        for note in notes:
            note = dict(note)
            public_keys = []
            if note['reshare'] is not None:
                reshare = DB.get_note(note['reshare'])
                if reshare is not None:
                    note['reshare'] = reshare
            public_keys.append(note['public_key'])
            public_keys = json.loads(note['members']) + public_keys
            self.add_public_keys(public_keys)
            self.notes.append(note)

    def add_public_keys(self, public_keys: list):
        for k in public_keys:
            if k not in self.public_keys:
                self.public_keys.append(k)

    def get_profile_briefs(self):
        self.profiles = DB.get_profile_briefs(self.public_keys)