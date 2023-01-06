import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import timestamp_minus, TimePeriod
from bija.settings import Settings
from python_nostr.nostr.event import EventKind
from python_nostr.nostr.filter import Filter, Filters
from python_nostr.nostr.message_type import ClientMessageType
from bija.app import RELAY_MANAGER

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Subscribe:
    def __init__(self, name):
        self.name = name
        logger.info('SUBSCRIBE: {}'.format(name))
        self.filters = None

    def send(self):
        request = [ClientMessageType.REQUEST, self.name]
        request.extend(self.filters.to_json_array())
        logger.info('add subscription to relay manager')
        RELAY_MANAGER.add_subscription(self.name, self.filters)
        message = json.dumps(request)
        logger.info('publish subscriptiom: {}'.format(message))
        RELAY_MANAGER.publish_message(message)


class SubscribePrimary(Subscribe):
    def __init__(self, name, pubkey):
        super().__init__(name)
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
                kinds=[EventKind.TEXT_NOTE, EventKind.REACTION, EventKind.DELETE, EventKind.CONTACTS],
                since=timestamp_minus(TimePeriod.DAY)  # TODO: should be configurable in user settings
            )
            following_profiles_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.SET_METADATA],
            )
            f.append(following_filter)
            f.append(following_profiles_filter)

        self.filters = Filters(f)


class SubscribeSearch(Subscribe):
    def __init__(self, name, term):
        super().__init__(name)
        self.term = term
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        required_pow = Settings.get('pow_required')
        subid = None
        if required_pow:
            logger.info('required pow {}'.format(required_pow))
            difficulty = int(int(required_pow)/4) * "0"
            logger.info('calculated difficulty {}'.format(difficulty))
            subid = {"ids": [difficulty]}
        f = [
            Filter(kinds=[EventKind.TEXT_NOTE], tags={'#t': [self.term]}, limit=10, subid=subid)
        ]
        self.filters = Filters(f)


class SubscribeProfile(Subscribe):
    def __init__(self, name, pubkey, since):
        super().__init__(name)
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
    def __init__(self, name, root):
        super().__init__(name)
        self.root = root
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        filters = []
        ids = DB.get_note_thread_ids(self.root)
        if ids is None:
            ids = [self.root]
        filters.append(Filter(ids=ids, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]))
        required_pow = Settings.get('pow_required')
        if required_pow is not None or required_pow > 0:
            pks = DB.get_following_pubkeys()
            difficulty = int(int(required_pow) / 4) * "0"
            subid = {"ids": [difficulty]}
            filters.append(Filter(tags={'#e': ids, '#p': pks}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]))
            filters.append(Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION], subid=subid))
        else:
            filters.append(Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]))  # event responses


        self.filters = Filters(filters)


class SubscribeFeed(Subscribe):
    def __init__(self, name, ids):
        super().__init__(name)
        self.ids = ids
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        self.filters = Filters([
            Filter(tags={'#e': self.ids}, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION]),  # event responses
            Filter(ids=self.ids, kinds=[EventKind.TEXT_NOTE, EventKind.REACTION])
        ])
