import json
import logging
import time

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import timestamp_minus, TimePeriod
from bija.settings import SETTINGS
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
        logger.info('publish subscription: {}'.format(message))
        RELAY_MANAGER.publish_message(message)

    @staticmethod
    def required_pow(setting: str = 'pow_required'):
        required_pow = SETTINGS.get(setting)
        if required_pow is not None and int(required_pow) > 0:
            return int(int(required_pow)/4) * "0"
        return None


class SubscribePrimary(Subscribe):
    def __init__(self, name, pubkey):
        super().__init__(name)
        self.pubkey = pubkey
        self.since = 0
        self.set_since()
        self.build_filters()
        self.send()

    def set_since(self):
        latest = DB.latest_in_primary(SETTINGS.get('pubkey'))
        if latest is not None:
            self.since = timestamp_minus(TimePeriod.HOUR, start=latest)
        else:
            self.since = timestamp_minus(TimePeriod.WEEK)

    def build_filters(self):
        logger.info('build subscription filters')
        kinds = [EventKind.SET_METADATA,
                 EventKind.TEXT_NOTE, EventKind.BOOST,
                 EventKind.RECOMMEND_RELAY,
                 EventKind.CONTACTS,
                 EventKind.ENCRYPTED_DIRECT_MESSAGE,
                 EventKind.DELETE,
                 EventKind.REACTION]
        profile_filter = Filter(authors=[self.pubkey], kinds=kinds, since=self.since)
        kinds = [EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.ENCRYPTED_DIRECT_MESSAGE, EventKind.REACTION, EventKind.CONTACTS]
        mentions_filter = Filter(tags={'#p': [self.pubkey]}, kinds=kinds, since=self.since)
        f = [profile_filter, mentions_filter]
        following_pubkeys = DB.get_following_pubkeys(SETTINGS.get('pubkey'))

        if len(following_pubkeys) > 0:
            following_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION, EventKind.DELETE],
                since=self.since  # TODO: should be configurable in user settings
            )
            following_profiles_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.SET_METADATA, EventKind.CONTACTS],
            )
            f.append(following_filter)
            f.append(following_profiles_filter)

        topics = DB.get_topics()
        if len(topics) > 0:
            difficulty = self.required_pow()
            t = []
            for topic in topics:
                t.append(topic.tag)
            topics_filter = Filter(
                kinds=[EventKind.TEXT_NOTE, EventKind.BOOST],
                subid={"ids": [difficulty]},
                tags={"#t": t},
                since=self.since
            )
            f.append(topics_filter)

        self.filters = Filters(f)


class SubscribeTopic(Subscribe):
    def __init__(self, name, term):
        super().__init__(name)
        self.term = term
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        difficulty = self.required_pow()
        subid = None
        if difficulty is not None:
            logger.info('calculated difficulty {}'.format(difficulty))
            subid = {"ids": [difficulty]}
        f = [
            Filter(kinds=[EventKind.TEXT_NOTE, EventKind.BOOST], tags={'#t': [self.term]}, since=timestamp_minus(TimePeriod.WEEK*4), subid=subid)
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
            Filter(authors=[self.pubkey], kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.DELETE, EventKind.REACTION],
                   since=self.since),
            Filter(tags={'#p': [self.pubkey]}, kinds=[EventKind.CONTACTS])
        ]
        followers = DB.get_following_pubkeys(self.pubkey)
        if followers is not None and len(followers) > 0:
            contacts_filter = Filter(authors=followers, kinds=[EventKind.SET_METADATA])
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
        filters.append(Filter(ids=ids, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]))
        difficulty = self.required_pow()
        if difficulty is not None:
            pks = DB.get_following_pubkeys(SETTINGS.get('pubkey'))
            subid = {"ids": [difficulty]}
            filters.append(Filter(tags={'#e': ids, '#p': pks}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]))
            filters.append(Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION], subid=subid))
        else:
            filters.append(Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]))  # event responses


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
            Filter(tags={'#e': self.ids}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]),  # event responses
            Filter(ids=self.ids, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION])
        ])
