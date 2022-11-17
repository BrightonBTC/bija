import json
import ssl
import time

from python_nostr.nostr.event import EventKind, Event
from python_nostr.nostr.filter import Filters, Filter
from python_nostr.nostr.key import PrivateKey
from python_nostr.nostr.message_type import ClientMessageType
from python_nostr.nostr.relay_manager import RelayManager


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
                print("EVENT OF KIND => ", msg.event.kind, " /", time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime()), " /", msg.subscription_id, " /")

                if msg.event.kind == EventKind.SET_METADATA:
                    self.handle_metadata_event(msg.event)

                if msg.event.kind == EventKind.CONTACTS:
                    self.handle_contact_list_event(msg.event)

                if msg.event.kind == EventKind.TEXT_NOTE:
                    self.handle_note_event(msg.event, msg.subscription_id)

                if msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                    self.handle_private_message_event(msg.event)

                if msg.event.kind == EventKind.DELETE:
                    self.handle_deleted_event(msg.event)

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

        is_known = self.db.is_known_pubkey(event.public_key)
        if is_known is None:
            self.db.add_profile(event.public_key, updated_at=0)
        self.db.insert_note(
            event.id,
            event.public_key,
            event.content,
            response_to,
            thread_root,
            event.created_at,
            members
        )
        print("CONTENT >>>>>>>", event.content)

    def submit_note(self, data):
        k = bytes.fromhex(self.session.get("keys")['private'])
        private_key = PrivateKey(k)
        r = self.db.get_preferred_relay()
        preferred_relay = r.name
        tags = []
        note = None
        response_to = None
        thread_root = None
        for v in data:
            if v[0] == "new_post":
                note = v[1]
                break
            elif v[0] == "reply":
                note = v[1]
            elif v[0] == "pubkey":
                tags.append(["p", v[1], preferred_relay,])
            elif v[0] == "parent_id":
                response_to = v[1]
                tags.append(["e", v[1], preferred_relay, "reply"])
            elif v[0] == "thread_root":
                thread_root = v[1]
                tags.append(["e", v[1], preferred_relay, "root"])
        if note is None:
            return False
        created_at = int(time.time())
        event = Event(private_key.public_key.hex(), note, tags=tags, created_at=created_at)
        event.sign(private_key.hex())

        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        self.relay_manager.publish_message(message)
        self.db.insert_note(
            event.id,
            private_key.public_key.hex(),
            note,
            response_to,
            thread_root,
            created_at
        )
        return event.id

    def handle_contact_list_event(self, event):
        keys = []
        for p in event.tags:
            if p[0] == "p":
                keys.append(p[1])
        if event.public_key == self.session.get("keys")['public']:
            following_pubkeys = self.db.get_following_pubkeys()
            subscription_reload = False
            new = set(keys) - set(following_pubkeys)
            removed = set(following_pubkeys) - set(keys)
            if len(new) > 0:
                print("NEW FOLLOWER")
                self.db.set_following(new)
                subscription_reload = True
            if len(removed) > 0:
                print("REMOVED FOLLOWER")
                self.db.set_following(removed, False)
                subscription_reload = True
            if subscription_reload:
                print("RELOAD PRIMARY SUBSCRIPTION")
                # self.close_subscription('primary')
                # time.sleep(1)
                # self.subscribe_primary()
            # self.subscribe_following(keys)

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

    def handle_deleted_event(self, event):
        pass

    def close_subscription(self, name):
        self.subscriptions.remove(name)
        self.relay_manager.close_subscription(name)

    def close_secondary_subscriptions(self):
        for s in self.subscriptions:
            if s not in ['primary', 'following']:
                print("CLOSE SUBSCRIPTION: ", s)
                self.close_subscription(s)

    def subscribe_note(self, note_id):
        subscription_id = 'note-thread'
        print("OPEN SUBSCRIPTION: ", subscription_id)
        self.subscriptions.append(subscription_id)
        filters = Filters([
            Filter(ids=[note_id], kinds=[EventKind.TEXT_NOTE]),
            Filter(tags={'#e': [note_id]}, kinds=[EventKind.TEXT_NOTE])
        ])
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        self.relay_manager.add_subscription(subscription_id, filters)
        time.sleep(1.25)
        message = json.dumps(request)
        self.relay_manager.publish_message(message)
        print("OPEN SUBSCRIPTION: ", subscription_id, message)

    def subscribe_profile(self, pubkey, since):
        subscription_id = 'profile'
        print("OPEN SUBSCRIPTION: ", subscription_id)
        self.subscriptions.append(subscription_id)
        filters = Filters([
            Filter(authors=[pubkey], kinds=[EventKind.SET_METADATA]),
            Filter(authors=[pubkey], kinds=[EventKind.TEXT_NOTE, EventKind.DELETE], since=since)
        ])
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        self.relay_manager.add_subscription(subscription_id, filters)
        time.sleep(1.25)
        message = json.dumps(request)
        self.relay_manager.publish_message(message)
        print("OPEN SUBSCRIPTION: ", subscription_id, message)

    # create site wide subscription
    def subscribe_primary(self):
        keys = self.session.get("keys")
        if 'primary' not in self.subscriptions and keys is not None:
            print("add primary subscription")
            pubkey = keys['public']
            self.subscriptions.append('primary')

            profile_filter = Filter(authors=[pubkey], kinds=[EventKind.SET_METADATA,
                           EventKind.TEXT_NOTE,
                           EventKind.RECOMMEND_RELAY,
                           EventKind.CONTACTS,
                           EventKind.ENCRYPTED_DIRECT_MESSAGE,
                           EventKind.DELETE])

            following_pubkeys = self.db.get_following_pubkeys()
            print(following_pubkeys)

            following_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.SET_METADATA, EventKind.TEXT_NOTE, EventKind.DELETE],
                since=int(time.time()) - (60 * 60 * 76))

            filters = Filters([profile_filter, following_filter])
            subscription_id = 'primary'
            request = [ClientMessageType.REQUEST, subscription_id]
            request.extend(filters.to_json_array())
            self.relay_manager.add_subscription(subscription_id, filters)
            time.sleep(1.25)
            message = json.dumps(request)
            self.relay_manager.publish_message(message)
        else:
            print('CONDITION NOT MET')

    # def subscribe_following(self, public_keys):
    #     if 'following' in self.subscriptions:
    #         print("close following subscription", public_keys)
    #         self.relay_manager.close_subscription('following')
    #         time.sleep(1)
    #     print("add following subscription", public_keys)
    #     self.subscriptions.append('following')
    #     event_kinds = [EventKind.SET_METADATA,
    #                    EventKind.TEXT_NOTE,
    #                    EventKind.DELETE]
    #     filters = Filters([Filter(authors=public_keys, kinds=event_kinds, since=int(time.time())-(60*60*12))])
    #     subscription_id = 'following'
    #     request = [ClientMessageType.REQUEST, subscription_id]
    #     request.extend(filters.to_json_array())
    #     self.relay_manager.add_subscription(subscription_id, filters)
    #     time.sleep(1.25)
    #     message = json.dumps(request)
    #     self.relay_manager.publish_message(message)

    def close(self):
        print("CLOSING CONNECTIONS")
        self.relay_manager.close_connections()

