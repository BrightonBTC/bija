import json
import time

from bija.helpers import is_hex_key
from python_nostr.nostr.event import EventKind, Event
from python_nostr.nostr.key import PrivateKey
from python_nostr.nostr.message_type import ClientMessageType


class Submit:
    def __init__(self, relay_manager, db, keys):
        self.relay_manager = relay_manager
        self.keys = keys
        self.db = db
        self.tags = []
        self.content = ""
        self.event_id = None
        self.kind = EventKind.TEXT_NOTE
        self.created_at = int(time.time())
        r = self.db.get_preferred_relay()
        self.preferred_relay = r.name

    def send(self):
        self.tags.append(['client', 'BIJA'])
        event = Event(self.keys['public'], self.content, tags=self.tags, created_at=self.created_at, kind=self.kind)
        event.sign(self.keys['private'])
        self.event_id = event.id
        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        self.relay_manager.publish_message(message)


class SubmitDelete(Submit):
    def __init__(self, relay_manager, db, keys, ids, reason=""):
        super().__init__(relay_manager, db, keys)
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
    def __init__(self, relay_manager, db, keys, data):
        super().__init__(relay_manager, db, keys)
        self.kind = EventKind.SET_METADATA
        self.content = json.dumps(data)
        self.send()


class SubmitLike(Submit):
    def __init__(self, relay_manager, db, keys, note_id, content="+"):
        super().__init__(relay_manager, db, keys)
        self.content = content
        self.note_id = note_id
        self.kind = EventKind.REACTION
        self.compose()
        self.send()

    def compose(self):
        note = self.db.get_note(self.note_id)
        members = json.loads(note.members)
        for m in members:
            if is_hex_key(m) and m != note.public_key:
                self.tags.append(["p", m, self.preferred_relay])
        self.tags.append(["p", note.public_key, self.preferred_relay])
        self.tags.append(["e", note.id, self.preferred_relay])


class SubmitNote(Submit):
    def __init__(self, relay_manager, db, keys, data, members=None):
        super().__init__(relay_manager, db, keys)
        self.data = data
        self.members = members
        self.response_to = None
        self.thread_root = None
        self.compose()
        self.send()
        self.store()

    def compose(self):
        data = self.data
        if 'quote_id' in data:
            self.content = "{} #[0]".format(data['comment'])
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

    def store(self):
        self.db.insert_note(
            self.event_id,
            self.keys['public'],
            self.content,
            self.response_to,
            self.thread_root,
            self.created_at
        )


class SubmitFollowList(Submit):
    def __init__(self, relay_manager, db, keys):
        super().__init__(relay_manager, db, keys)
        self.kind = EventKind.CONTACTS
        self.compose()
        self.send()

    def compose(self):
        pk_list = self.db.get_following_pubkeys()
        for pk in pk_list:
            self.tags.append(["p", pk])


class SubmitEncryptedMessage(Submit):
    def __init__(self, relay_manager, db, keys, data):
        super().__init__(relay_manager, db, keys)
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
