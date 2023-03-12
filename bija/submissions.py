import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import is_hex_key, get_at_tags, get_hash_tags, get_note_links, bech32_to_hex64
from bija.settings import SETTINGS
from bija.ws.event import EventKind, Event
from bija.ws.key import PrivateKey
from bija.ws.message_type import ClientMessageType
from bija.ws.pow import mine_event
from bija.app import RELAY_MANAGER

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Submit:
    def __init__(self):
        logger.info('SUBMISSION initiated')
        self.tags = []
        self.content = ""
        self.event_id = None
        self.kind = EventKind.TEXT_NOTE
        self.created_at = int(time.time())
        r = DB.get_preferred_relay()
        self.preferred_relay = r.name
        self.pow_difficulty = None

    def send(self):
        self.tags.append(['client', 'BIJA'])
        if self.pow_difficulty is None or self.pow_difficulty < 1:
            event = Event(SETTINGS.get('pubkey'), self.content, tags=self.tags, created_at=self.created_at, kind=self.kind)
        else:
            logger.info('mine event')
            event = mine_event(self.content, self.pow_difficulty, SETTINGS.get('pubkey'), self.kind, self.tags)
        event.sign(SETTINGS.get('privkey'))
        self.event_id = event.id
        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        logger.info('SUBMIT: {}'.format(message))
        RELAY_MANAGER.publish_message(message)
        logger.info('PUBLISHED')

class SubmitBoost(Submit):
    def __init__(self, note_id, content):
        super().__init__()
        logger.info('SUBMIT boost')
        self.kind = EventKind.BOOST
        self.tags.append(['e', note_id])
        self.content = content
        self.send()

class SubmitDelete(Submit):
    def __init__(self, ids, reason=""):
        super().__init__()
        logger.info('SUBMIT delete')
        self.kind = EventKind.DELETE
        self.ids = ids
        self.content = reason
        self.compose()
        self.send()

    def compose(self):
        logger.info('compose')
        for eid in self.ids:
            if is_hex_key(eid):
                self.tags.append(['e', eid])


class SubmitProfile(Submit):
    def __init__(self, data):
        super().__init__()
        logger.info('SUBMIT profile')
        self.kind = EventKind.SET_METADATA
        self.content = json.dumps(data)
        self.send()


class SubmitLike(Submit):
    def __init__(self, note_id, content="+"):
        super().__init__()
        logger.info('SUBMIT like')
        self.content = content
        self.note_id = note_id
        self.kind = EventKind.REACTION
        self.compose()
        self.send()

    def compose(self):
        logger.info('compose')
        note = DB.get_note(SETTINGS.get('pubkey'), self.note_id)
        members = json.loads(note.members)
        for m in members:
            if is_hex_key(m) and m != note.public_key:
                self.tags.append(["p", m, self.preferred_relay])
        self.tags.append(["p", note.public_key, self.preferred_relay])
        self.tags.append(["e", note.id, self.preferred_relay])


class SubmitNote(Submit):
    def __init__(self, data, members=[], pow_difficulty=None):
        super().__init__()
        logger.info('SUBMIT note')
        self.data = data
        self.members = members
        self.response_to = None
        self.thread_root = None
        self.reshare = None
        if pow_difficulty is not None:
            self.pow_difficulty = int(pow_difficulty)
        self.compose()
        self.send()
        # self.store()

    def compose(self):
        logger.info('compose')
        data = self.data
        if 'quote_id' in data:
            logger.info('has quote id')
            i = '0'
            if self.pow_difficulty is not None and self.pow_difficulty > 0:
                i = '1'
            self.content = "{} #[{}]".format(data['comment'], i)
            self.reshare = data['quote_id']
            self.tags.append(["e", data['quote_id']])
            if self.members is not None:
                for m in self.members:
                    if is_hex_key(m):
                        self.tags.append(["p", m, self.preferred_relay])
        elif 'new_post' in data:
            logger.info('is new post')
            self.content = data['new_post']
        elif 'reply' in data:
            logger.info('is reply')
            self.content = data['reply']
            if self.members is not None:
                for m in self.members:
                    if is_hex_key(m):
                        self.tags.append(["p", m, self.preferred_relay])
            if 'parent_id' not in data or 'thread_root' not in data:
                self.event_id = False
            elif len(data['parent_id']) < 1 and is_hex_key(data['thread_root']):
                self.thread_root = data['thread_root']
                self.tags.append(["e", data['thread_root'], self.preferred_relay, "root"])
            elif is_hex_key(data['parent_id']) and is_hex_key(data['thread_root']):
                self.thread_root = data['thread_root']
                self.response_to = data['parent_id']
                self.tags.append(["e", data['parent_id'], self.preferred_relay, "reply"])
                self.tags.append(["e", data['thread_root'], self.preferred_relay, "root"])
        else:
            self.event_id = False
        if 'uploads' in data:
            logger.info('has uploads')
            self.content += data['uploads']
        self.process_hash_tags()
        self.process_mentions()

    def process_mentions(self):
        logger.info('process mentions')
        matches = get_at_tags(self.content)
        note_matches = get_note_links(self.content)
        offset = 1
        if self.pow_difficulty is not None and self.pow_difficulty > 0:
            offset = 0
        for match in matches:
            name = DB.get_profile_by_name_or_pk(match[1:])
            if name is not None:
                self.tags.append(["p", name['public_key']])
                index = len(self.tags) - offset
                self.content = self.content.replace(match, "#[{}]".format(index))
        for match in note_matches:
            match = match[1:-1]
            self.tags.append(["e", bech32_to_hex64('note', match)])
            index = len(self.tags) - offset
            self.content = self.content.replace(match, "#[{}]".format(index))

    def process_hash_tags(self):
        logger.info('process hashtags')
        matches = get_hash_tags(self.content)
        if len(matches) > 0:
            for match in matches:
                self.tags.append(["t", match[1:].strip()])


class SubmitRelayList(Submit):
    def __init__(self):
        super().__init__()
        logger.info('SUBMIT relay list')
        self.kind = EventKind.RELAY_LIST
        self.compose()
        self.send()

    def compose(self):
        logger.info('compose')
        relays = DB.get_relays(fav=True)
        for r in relays:
            if r.send and r.receive:
                self.tags.append(["r", r.name])
            elif r.send:
                self.tags.append(["r", r.name, "write"])
            elif r.receive:
                self.tags.append(["r", r.name, "read"])


class SubmitFollowList(Submit):
    def __init__(self):
        super().__init__()
        logger.info('SUBMIT follow list')
        self.kind = EventKind.CONTACTS
        self.compose()
        self.send()

    def compose(self):
        logger.info('compose')
        pk_list = DB.get_following_pubkeys(SETTINGS.get('pubkey'))
        for pk in pk_list:
            self.tags.append(["p", pk])

class SubmitBlockList(Submit):
    def __init__(self, l: list):
        super().__init__()
        logger.info('SUBMIT block list')
        self.kind = EventKind.BLOCK_LIST
        encrypted = encrypt(json.dumps(l), SETTINGS.get('pubkey'))
        if encrypted:
            self.content = encrypted
            self.send()

class SubmitPersonList(Submit):
    def __init__(self, name, l: list):
        super().__init__()
        logger.info('SUBMIT person list')
        l = list(set(tuple(x) for x in l))
        self.tags.append(['d', name])
        self.kind = EventKind.PERSON_LIST
        encrypted = encrypt(json.dumps(l), SETTINGS.get('pubkey'))
        if encrypted:
            self.content = encrypted
            self.send()


class SubmitBookmarkList(Submit):
    def __init__(self, name, l: list):
        super().__init__()
        logger.info('SUBMIT bookmark list')
        #l = list(set(tuple(x) for x in l))
        self.tags.append(['d', name])
        self.kind = EventKind.BOOKMARK_LIST
        encrypted = encrypt(json.dumps(l), SETTINGS.get('pubkey'))
        if encrypted:
            self.content = encrypted
            self.send()


class SubmitEncryptedMessage(Submit):
    def __init__(self, data, pow_difficulty=None):
        super().__init__()
        logger.info('SUBMIT encrypted message')
        self.kind = EventKind.ENCRYPTED_DIRECT_MESSAGE
        self.data = data
        if pow_difficulty is not None:
            self.pow_difficulty = int(pow_difficulty)
        self.compose()

    def compose(self):
        logger.info('compose')
        pk = None
        txt = None
        for v in self.data:
            if v[0] == "new_message":
                txt = v[1]
            elif v[0] == "new_message_pk":
                pk = v[1]
        if pk is not None and txt is not None:
            self.tags.append(['p', pk])
            self.content = encrypt(txt, pk)
            self.send()
        else:
            self.event_id = False

def encrypt(message, public_key):
    logger.info('encrypt message')
    try:
        k = bytes.fromhex(SETTINGS.get('privkey'))
        pk = PrivateKey(k)
        return pk.encrypt_message(message, public_key)
    except ValueError:
        return False
