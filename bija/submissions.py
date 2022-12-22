import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import is_hex_key, get_at_tags, get_hash_tags
from python_nostr.nostr.event import EventKind, Event
from python_nostr.nostr.key import PrivateKey
from python_nostr.nostr.message_type import ClientMessageType

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Submit:
    def __init__(self, relay_manager, keys):
        logger.info('SUBMISSION initiated')
        self.relay_manager = relay_manager
        self.keys = keys
        self.tags = []
        self.content = ""
        self.event_id = None
        self.kind = EventKind.TEXT_NOTE
        self.created_at = int(time.time())
        r = DB.get_preferred_relay()
        self.preferred_relay = r.name

    def send(self):
        self.tags.append(['client', 'BIJA'])
        event = Event(self.keys['public'], self.content, tags=self.tags, created_at=self.created_at, kind=self.kind)
        event.sign(self.keys['private'])
        self.event_id = event.id
        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        logger.info('SUBMIT: {}'.format(message))
        self.relay_manager.publish_message(message)
        logger.info('PUBLISHED')


class SubmitDelete(Submit):
    def __init__(self, relay_manager, keys, ids, reason=""):
        super().__init__(relay_manager, keys)
        self.kind = EventKind.DELETE
        self.ids = ids
        self.content = reason
        self.compose()
        self.send()

    def compose(self):
        for eid in self.ids:
            if is_hex_key(eid):
                self.tags.append(['e', eid])


class SubmitProfile(Submit):
    def __init__(self, relay_manager, keys, data):
        super().__init__(relay_manager, keys)
        self.kind = EventKind.SET_METADATA
        self.content = json.dumps(data)
        self.send()


class SubmitLike(Submit):
    def __init__(self, relay_manager, keys, note_id, content="+"):
        super().__init__(relay_manager, keys)
        logger.info('SUBMIT like')
        self.content = content
        self.note_id = note_id
        self.kind = EventKind.REACTION
        self.compose()
        self.send()

    def compose(self):
        note = DB.get_note(self.note_id)
        members = json.loads(note.members)
        for m in members:
            if is_hex_key(m) and m != note.public_key:
                self.tags.append(["p", m, self.preferred_relay])
        self.tags.append(["p", note.public_key, self.preferred_relay])
        self.tags.append(["e", note.id, self.preferred_relay])


class SubmitNote(Submit):
    def __init__(self, relay_manager, keys, data, members=[]):
        super().__init__(relay_manager, keys)
        self.data = data
        self.members = members
        self.response_to = None
        self.thread_root = None
        self.reshare = None
        self.compose()
        self.send()
        self.store()

    def compose(self):
        data = self.data
        if 'quote_id' in data:
            self.content = "{} #[0]".format(data['comment'])
            self.reshare = data['quote_id']
            self.tags.append(["e", data['quote_id']])
            if self.members is not None:
                for m in self.members:
                    if is_hex_key(m):
                        self.tags.append(["p", m, self.preferred_relay])
        elif 'new_post' in data:
            self.content = data['new_post']
        elif 'reply' in data:
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
            self.content += data['uploads']
        self.process_hash_tags()
        self.process_mentions()

    def process_mentions(self):
        matches = get_at_tags(self.content)
        for match in matches:
            name = DB.get_profile_by_name_or_pk(match[1:])
            if name is not None:
                self.tags.append(["p", name['public_key']])
                index = len(self.tags) - 1
                self.content = self.content.replace(match, "#[{}]".format(index))

    def process_hash_tags(self):
        matches = get_hash_tags(self.content)
        if len(matches) > 0:
            for match in matches:
                self.tags.append(["t", match[1:]])

    def store(self):
        DB.insert_note(
            self.event_id,
            self.keys['public'],
            self.content,
            self.response_to,
            self.thread_root,
            self.reshare,
            self.created_at,
            json.dumps(self.members)
        )


class SubmitFollowList(Submit):
    def __init__(self, relay_manager, keys):
        super().__init__(relay_manager, keys)
        self.kind = EventKind.CONTACTS
        self.compose()
        self.send()

    def compose(self):
        pk_list = DB.get_following_pubkeys()
        for pk in pk_list:
            self.tags.append(["p", pk])


class SubmitEncryptedMessage(Submit):
    def __init__(self, relay_manager, keys, data):
        super().__init__(relay_manager, keys)
        self.kind = EventKind.ENCRYPTED_DIRECT_MESSAGE
        self.data = data
        self.compose()

    def compose(self):
        pk = None
        txt = None
        for v in self.data:
            if v[0] == "new_message":
                txt = v[1]
            elif v[0] == "new_message_pk":
                pk = v[1]
        if pk is not None and txt is not None:
            self.tags.append(['p', pk])
            self.content = self.encrypt(txt, pk)
            self.send()
        else:
            self.event_id = False

    def encrypt(self, message, public_key):
        try:
            k = bytes.fromhex(self.keys['private'])
            pk = PrivateKey(k)
            return pk.encrypt_message(message, public_key)
        except ValueError:
            return False
