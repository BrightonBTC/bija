import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import timestamp_minus, TimePeriod
from python_nostr.nostr.event import EventKind
from python_nostr.nostr.filter import Filter, Filters
from python_nostr.nostr.message_type import ClientMessageType

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Subscribe:
    def __init__(self, name, relay_manager):
        self.relay_manager = relay_manager
        self.name = name
        logger.info('SUBSCRIBE: {}'.format(name))
        self.filters = None

    def send(self):
        request = [ClientMessageType.REQUEST, self.name]
        request.extend(self.filters.to_json_array())
        logger.info('add subscription to relay manager')
        self.relay_manager.add_subscription(self.name, self.filters)
        message = json.dumps(request)
        logger.info('publish subscriptiom')
        self.relay_manager.publish_message(message)


class SubscribePrimary(Subscribe):
    def __init__(self, name, relay_manager, pubkey):
        super().__init__(name, relay_manager)
        self.pubkey = pubkey
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
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
        following_pubkeys = DB.get_following_pubkeys()

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


class SubscribeSearch(Subscribe):
    def __init__(self, name, relay_manager, term):
        super().__init__(name, relay_manager)
        self.term = term
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        f = [
            Filter(kinds=[EventKind.TEXT_NOTE], tags={'#t': [self.term]}, limit=10)
        ]
        self.filters = Filters(f)


class SubscribeProfile(Subscribe):
    def __init__(self, name, relay_manager, pubkey, since):
        super().__init__(name, relay_manager)
        self.pubkey = pubkey
        self.since = since
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        profile = DB.get_profile(self.pubkey)

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
    def __init__(self, name, relay_manager, root):
        super().__init__(name, relay_manager)
        self.root = root
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        ids = DB.get_note_thread_ids(self.root)
        if ids is None:
            ids = [self.root]

        self.filters = Filters([
            Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]),  # event responses
            Filter(ids=ids, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION])
        ])


class SubscribeFeed(Subscribe):
    def __init__(self, name, relay_manager, ids):
        super().__init__(name, relay_manager)
        self.ids = ids
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        self.filters = Filters([
            Filter(tags={'#e': self.ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]),  # event responses
            Filter(ids=self.ids, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION])
        ])
