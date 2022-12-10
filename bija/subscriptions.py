import json
import time

from bija.helpers import timestamp_minus, TimePeriod
from python_nostr.nostr.event import EventKind
from python_nostr.nostr.filter import Filter, Filters
from python_nostr.nostr.message_type import ClientMessageType


class Subscribe:
    def __init__(self, name, relay_manager, db):
        self.relay_manager = relay_manager
        self.db = db
        self.name = name
        self.filters = None

    def send(self):
        request = [ClientMessageType.REQUEST, self.name]
        request.extend(self.filters.to_json_array())
        self.relay_manager.add_subscription(self.name, self.filters)
        time.sleep(1)
        message = json.dumps(request)
        self.relay_manager.publish_message(message)


class SubscribePrimary(Subscribe):
    def __init__(self, name, relay_manager, db, pubkey):
        super().__init__(name, relay_manager, db)
        self.pubkey = pubkey
        self.build_filters()
        self.send()

    def build_filters(self):
        kinds = [EventKind.SET_METADATA,
                 EventKind.TEXT_NOTE,
                 EventKind.RECOMMEND_RELAY,
                 EventKind.CONTACTS,
                 EventKind.ENCRYPTED_DIRECT_MESSAGE,
                 EventKind.DELETE,
                 EventKind.REACTION]
        profile_filter = Filter(authors=[self.pubkey], kinds=kinds)
        kinds = [EventKind.TEXT_NOTE, EventKind.ENCRYPTED_DIRECT_MESSAGE, EventKind.REACTION, EventKind.CONTACTS]
        mentions_filter = Filter(tags={'#p': [self.pubkey]}, kinds=kinds)
        f = [profile_filter, mentions_filter]
        following_pubkeys = self.db.get_following_pubkeys()

        if len(following_pubkeys) > 0:
            following_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.TEXT_NOTE, EventKind.REACTION, EventKind.DELETE],
                since=timestamp_minus(TimePeriod.WEEK)  # TODO: should be configurable in user settings
            )
            following_profiles_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.SET_METADATA],
            )
            f.append(following_filter)
            f.append(following_profiles_filter)

        self.filters = Filters(f)


class SubscribeProfile(Subscribe):
    def __init__(self, name, relay_manager, db, pubkey, since):
        super().__init__(name, relay_manager, db)
        self.pubkey = pubkey
        self.since = since
        self.build_filters()
        self.send()

    def build_filters(self):
        profile = self.db.get_profile(self.pubkey)

        f = [
            Filter(authors=[self.pubkey], kinds=[EventKind.SET_METADATA, EventKind.CONTACTS]),
            Filter(authors=[self.pubkey], kinds=[EventKind.TEXT_NOTE, EventKind.DELETE, EventKind.REACTION],
                   since=self.since)
        ]
        if profile is not None and profile.contacts is not None:
            contacts_filter = Filter(authors=json.loads(profile.contacts), kinds=[EventKind.SET_METADATA])
            f.append(contacts_filter)

        self. filters = Filters(f)


class SubscribeThread(Subscribe):
    def __init__(self, name, relay_manager, db, root):
        super().__init__(name, relay_manager, db)
        self.root = root
        self.build_filters()
        self.send()

    def build_filters(self):
        ids = self.db.get_note_thread_ids(self.root)
        if ids is None:
            ids = [self.root]

        self.filters = Filters([
            Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]),  # event responses
            Filter(ids=ids, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION])
        ])


class SubscribeFeed(Subscribe):
    def __init__(self, name, relay_manager, db, ids):
        super().__init__(name, relay_manager, db)
        self.ids = ids
        self.build_filters()
        self.send()

    def build_filters(self):
        filters = Filters([
            Filter(tags={'#e': self.ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]),  # event responses
            Filter(ids=self.ids, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION])
        ])
