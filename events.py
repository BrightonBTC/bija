import json
import ssl
import time

from nostr.event import EventKind, Event
from nostr.filter import Filters, Filter
from nostr.key import PrivateKey
from nostr.message_type import ClientMessageType
from nostr.relay_manager import RelayManager


class BijaEvents:
    subscriptions = []
    pool_handler_running = False
    unseen_notes = 0

    def __init__(self, db, session):
        self.db = db
        self.session = session
        self.relay_manager = RelayManager()
        relays = self.db.get_relays()
        n_relays = 0
        for r in relays:
            n_relays += 1
            self.relay_manager.add_relay(r.name)
        if n_relays > 0:
            self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})

    def message_pool_handler(self):
        if self.pool_handler_running:
            return
        self.pool_handler_running = True
        while True:
            while self.relay_manager.message_pool.has_events():
                msg = self.relay_manager.message_pool.get_event()
                print("EVENT OF KIND => ", msg.event.kind, " /", time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime()))

                if msg.event.kind == EventKind.SET_METADATA:
                    self.handle_metadata_event(msg.event)

                if msg.event.kind == EventKind.CONTACTS:
                    self.handle_contact_list_event(msg.event)

                if msg.event.kind == EventKind.TEXT_NOTE:
                    self.handle_note_event(msg.event, msg.subscription_id)

                if msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                    self.handle_private_message_event(msg.event)

    def get_relay_connect_status(self):
        relays = {}
        for r in self.relay_manager.relays.values():
            if r.is_open:
                relays[r.url] = 1
            else:
                relays[r.url] = 0
        return relays

    def handle_metadata_event(self, event):
        s = json.loads(event.content)
        name = None
        nip05 = None
        about = None
        picture = None
        if 'name' in s:
            name = s['name']
        if 'nip05' in s:
            nip05 = s['nip05']
        if 'about' in s:
            about = s['about']
        if 'picture' in s:
            picture = s['picture']
        self.db.upd_profile(
            event.public_key,
            name,
            nip05,
            picture,
            about,
            event.created_at,
        )

    def handle_note_event(self, event, subscription):
        response_to = None
        thread_root = None
        members = ""
        if len(event.tags) > 0:
            parents = []
            for item in event.tags:
                if item[0] == "p":
                    members += item[1] + ", "
                elif item[0] == "e":
                    if len(item) == 2:  # deprecate format
                        parents.append(item[1])
                    elif len(item) > 3 and item[3] in ["root", "reply"]:
                        if item[3] == "root":
                            thread_root = item[1]
                        elif item[3] == "reply":
                            response_to = item[1]
                if len(parents) == 1:
                    response_to = parents[0]
                elif len(parents) > 1:
                    thread_root = parents[0]
                    response_to = parents[1]
        if subscription in ['primary', 'following'] and self.db.is_note(event.id) is None:
            self.unseen_notes += 1
        self.db.insert_note(
            event.id,
            event.public_key,
            event.content,
            response_to,
            thread_root,
            event.created_at,
            members
        )

    def submit_note(self, msg):
        print(msg)
        k = bytes.fromhex(self.session.get("keys")['private'])
        private_key = PrivateKey(k)

        event = Event(private_key.public_key.hex(), msg)
        print(event.id)
        event.sign(private_key.hex())

        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        self.relay_manager.publish_message(message)
        return event.id

    def handle_contact_list_event(self, event):
        keys = []
        for p in event.tags:
            if p[0] == "p":
                keys.append(p[1])
        if event.public_key == self.session.get("keys")['public']:
            self.db.add_following(keys)
        self.subscribe_following(keys)

    def handle_private_message_event(self, event):
        to = False
        for p in event.tags:
            if p[0] == "p":
                to = p[1]
                break
        if to and [getattr(event, attr) for attr in ['id', 'public_key', 'content', 'created_at']]:
            self.db.insert_private_message(
                event.id,
                event.public_key,
                event.content,
                to,
                event.created_at
            )

    # create site wide subscription
    def subscribe_primary(self):
        keys = self.session.get("keys")
        if 'primary' not in self.subscriptions and keys is not None:
            print("add primary subscription")
            pubkey = keys['public']
            self.subscriptions.append('primary')
            event_kinds = [EventKind.SET_METADATA,
                           EventKind.TEXT_NOTE,
                           EventKind.RECOMMEND_RELAY,
                           EventKind.CONTACTS,
                           EventKind.ENCRYPTED_DIRECT_MESSAGE,
                           EventKind.DELETE]
            filters = Filters([Filter(authors=[pubkey], kinds=event_kinds)])
            subscription_id = 'primary'
            request = [ClientMessageType.REQUEST, subscription_id]
            request.extend(filters.to_json_array())
            self.relay_manager.add_subscription(subscription_id, filters)
            time.sleep(1.25)
            message = json.dumps(request)
            self.relay_manager.publish_message(message)

    def subscribe_following(self, public_keys):
        if 'following' not in self.subscriptions:
            print("add following subscription", public_keys)
            self.subscriptions.append('following')
            event_kinds = [EventKind.SET_METADATA,
                           EventKind.TEXT_NOTE,
                           EventKind.DELETE]
            filters = Filters([Filter(authors=public_keys, kinds=event_kinds)])
            subscription_id = 'following'
            request = [ClientMessageType.REQUEST, subscription_id]
            request.extend(filters.to_json_array())
            self.relay_manager.add_subscription(subscription_id, filters)
            time.sleep(1.25)
            message = json.dumps(request)
            self.relay_manager.publish_message(message)

    def close(self):
        print("CLOSING CONNECTIONS")
        self.relay_manager.close_connections()

