import json
import logging

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import timestamp_minus, TimePeriod
from bija.settings import SETTINGS
from bija.ws.event import EventKind
from bija.ws.filter import Filter, Filters
from bija.ws.message_type import ClientMessageType
from bija.app import RELAY_MANAGER

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class Subscribe:
    def __init__(self, name, relays=[], batch=0):
        self.name = name
        self.relays = relays
        self.batch = batch
        logger.info('SUBSCRIBE: {} | Relays {} | Batch {}'.format(name, relays, batch))
        self.filters = None

    def send(self):
        request = [ClientMessageType.REQUEST, self.name]
        request.extend(self.filters.to_json_array())
        logger.info('add subscription to relay manager')

        if len(self.relays) < 1:  # publish to all
            for r in RELAY_MANAGER.relays.keys():
                self.relays.append(r)
        for r in self.relays:
            if r in RELAY_MANAGER.relays:
                logger.info(
                    'publish subscription {}  | Relay {} | Batch {}'.format(self.name, r, self.batch))
                RELAY_MANAGER.relays[r].add_subscription(self.name, self.filters, self.batch)
                message = json.dumps(request)
                RELAY_MANAGER.relays[r].publish(message)


    @staticmethod
    def required_pow(setting: str = 'pow_required'):
        required_pow = SETTINGS.get(setting)
        if required_pow is not None and int(required_pow) > 0:
            return int(int(required_pow) / 4) * "0"
        return None


class SubscribePrimary(Subscribe):
    def __init__(self, name, relay, batch, pubkey):
        super().__init__(name, relay, batch)
        self.pubkey = pubkey
        self.since = 0
        self.set_since()
        self.build_filters()
        self.send()

    def set_since(self):
        latest_event = DB.latest_event()
        if latest_event is not None:
            self.since = timestamp_minus(TimePeriod.HOUR, start=latest_event.ts)
        else:
            self.since = timestamp_minus(TimePeriod.DAY)

    def build_filters(self):
        logger.info('build subscription filters')
        kinds = [EventKind.TEXT_NOTE, EventKind.BOOST,
                 EventKind.RECOMMEND_RELAY,
                 EventKind.ENCRYPTED_DIRECT_MESSAGE,
                 EventKind.DELETE,
                 EventKind.REACTION]
        profile_filter = Filter(authors=[self.pubkey], kinds=kinds, since=self.since)
        contacts_filter = Filter(authors=[self.pubkey], kinds=[EventKind.CONTACTS], limit=1)
        blocked_filter = Filter(authors=[self.pubkey], kinds=[EventKind.BLOCK_LIST], limit=1)
        md_filter = Filter(authors=[self.pubkey], kinds=[EventKind.SET_METADATA], limit=1)
        kinds = [EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION, EventKind.ENCRYPTED_DIRECT_MESSAGE]
        mentions_filter = Filter(tags={'#p': [self.pubkey]}, kinds=kinds, since=self.since)
        followers_filter = Filter(tags={'#p': [self.pubkey]}, kinds=[EventKind.CONTACTS])
        messages_filter = Filter(authors=[self.pubkey], kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE],
                                 since=self.since)
        f = [profile_filter, contacts_filter, md_filter, mentions_filter, messages_filter, blocked_filter, followers_filter]
        start = int(self.batch * 256)
        end = start + 256
        following_pubkeys = DB.get_following_pubkeys(SETTINGS.get('pubkey'), start, end)

        if len(following_pubkeys) > 0:
            following_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.SET_METADATA, EventKind.CONTACTS, EventKind.ENCRYPTED_DIRECT_MESSAGE, EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION, EventKind.DELETE],
                since=self.since
            )
            f.append(following_filter)

        topics = DB.get_topics()
        if len(topics) > 0:
            difficulty = self.required_pow()
            t = []
            for topic in topics:
                t.append(topic.tag)
            topics_filter = Filter(
                kinds=[EventKind.TEXT_NOTE, EventKind.BOOST],
                ids=[difficulty],
                tags={"#t": t},
                since=self.since
            )
            f.append(topics_filter)

        self.filters = Filters(f)


class SubscribeTopic(Subscribe):
    def __init__(self, name, relay, batch, term):
        super().__init__(name, relay, batch)
        self.term = term
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        difficulty = self.required_pow()
        ids = None
        if difficulty is not None:
            logger.info('calculated difficulty {}'.format(difficulty))
            ids = [difficulty]
        f = [
            Filter(kinds=[EventKind.TEXT_NOTE, EventKind.BOOST], tags={'#t': [self.term]},
                   since=timestamp_minus(TimePeriod.WEEK * 4), ids=ids)
        ]
        self.filters = Filters(f)


class SubscribeProfile(Subscribe):
    def __init__(self, name, relay, batch, pubkey, since, ids):
        super().__init__(name, relay, batch)
        self.ids = ids
        self.pubkey = pubkey
        if not DB.is_blocked(pubkey):
            self.since = since
            self.build_filters()
            self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        f = [
            Filter(authors=[self.pubkey], kinds=[EventKind.RELAY_LIST], limit=1),
            Filter(authors=[self.pubkey], kinds=[EventKind.SET_METADATA, EventKind.CONTACTS]),
            # Filter(tags={'#p': [self.pubkey]}, kinds=[EventKind.CONTACTS]),
            Filter(ids=self.ids, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION])
        ]
        if self.since is None:
            main_filter = Filter(authors=[self.pubkey],
                   kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.DELETE, EventKind.REACTION],
                   limit=100)
        else:
            main_filter = Filter(authors=[self.pubkey],
                   kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.DELETE, EventKind.REACTION],
                   since=self.since)
        f.append(main_filter)
        start = int(self.batch * 256)
        end = start + 256
        followers = DB.get_following_pubkeys(self.pubkey, start, end)
        if followers is not None and len(followers) > 0:
            contacts_filter = Filter(authors=followers, kinds=[EventKind.SET_METADATA])
            f.append(contacts_filter)
        self.filters = Filters(f)

class SubscribeFollowerList(Subscribe):
    def __init__(self, name, relay, batch, pubkey, since):
        super().__init__(name, relay, batch)
        self.pubkey = pubkey
        self.since = since
        self.build_filters()
        self.send()

    def build_filters(self):
        f = [Filter(tags={'#p': [self.pubkey]}, kinds=[EventKind.CONTACTS], since=self.since)]
        start = int(self.batch * 256)
        end = start + 256
        followers = DB.get_follower_pubkeys(self.pubkey, start, end)
        if followers is not None and len(followers) > 0:
            f.append(Filter(authors=followers, kinds=[EventKind.CONTACTS], since=self.since))
        self.filters = Filters(f)

class SubscribeThread(Subscribe):
    def __init__(self, name, relay, batch, root):
        super().__init__(name, relay, batch)
        self.batch = batch
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
            start = int(self.batch * 256)
            end = start + 256
            pks = DB.get_following_pubkeys(SETTINGS.get('pubkey'), start, end)
            filters.append(
                Filter(tags={'#e': ids, '#p': pks}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]))
            filters.append(
                Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION], ids=[difficulty]))
        else:
            filters.append(Filter(tags={'#e': ids},
                                  kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]))  # event responses
        self.filters = Filters(filters)


class SubscribeFeed(Subscribe):
    def __init__(self, name, relay, batch, ids):
        super().__init__(name, relay, batch)
        self.ids = ids
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        self.filters = Filters([
            Filter(tags={'#e': self.ids}, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION]),
            # event responses
            Filter(ids=self.ids, kinds=[EventKind.TEXT_NOTE, EventKind.BOOST, EventKind.REACTION])
        ])



class SubscribeMessages(Subscribe):
    def __init__(self, name, relay, batch, pubkey, since):
        super().__init__(name, relay, batch)
        self.pubkey = pubkey
        self.since = since
        self.build_filters()
        self.send()

    def build_filters(self):
        logger.info('build subscription filters')
        self.filters = Filters([
            Filter(authors=[self.pubkey], kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], since=self.since),
            Filter(tags={'#p': [self.pubkey]}, kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], since=self.since)
        ])
