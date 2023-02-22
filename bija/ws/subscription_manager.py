import logging
import time

from bija.app import app, RELAY_MANAGER
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.subscriptions import SubscribeThread, SubscribePrimary, SubscribeFeed, SubscribeProfile, SubscribeTopic, \
    SubscribeMessages, SubscribeFollowerList

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class SubscriptionManager:
    def __init__(self):
        self.should_run = True
        self.max_connected_relays = 5
        self.subscriptions = {}

    def add_subscription(self, name, batch_count, **kwargs):
        self.subscriptions[name] = {'batch_count': batch_count, 'kwargs': kwargs, 'paused': False}
        self.subscribe(name)

    def remove_subscription(self, name):
        del self.subscriptions[name]
        RELAY_MANAGER.close_subscription(name)

    def clear_subscriptions(self):
        remove_list = []
        for sub in self.subscriptions:
            if sub != 'primary':
                remove_list.append(sub)
        for sub in remove_list:
            self.remove_subscription(sub)

    def next_round(self):

        for relay in RELAY_MANAGER.relays:
            for s in RELAY_MANAGER.relays[relay].subscriptions:
                sub = RELAY_MANAGER.relays[relay].subscriptions[s]
                if sub.paused and sub.paused < int(time.time()) - 30:
                    sub.paused = False
                    self.subscribe(s, [relay], 0)

    def next_batch(self, relay, name):
        if name in self.subscriptions and self.subscriptions[name]['batch_count'] > 1:
            if relay in RELAY_MANAGER.relays and name in RELAY_MANAGER.relays[relay].subscriptions:

                if RELAY_MANAGER.relays[relay].subscriptions[name].batch >= self.subscriptions[name]['batch_count'] - 1:
                    RELAY_MANAGER.relays[relay].subscriptions[name].batch = 0
                    RELAY_MANAGER.relays[relay].subscriptions[name].paused = time.time()
                else:
                    self.subscribe(
                        name,
                        [relay],
                        RELAY_MANAGER.relays[relay].subscriptions[name].batch + 1
                    )


    def subscribe(self, name, relay=[], batch=0):
        if name == 'primary':
            SubscribePrimary(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['pubkey']
            )
        elif name == 'main-feed':
            SubscribeFeed(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['ids']
            )
        elif name == 'topic':
            SubscribeTopic(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['term']
            )
        elif 'profile:' in name:
            SubscribeProfile(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                self.subscriptions[name]['kwargs']['since'],
                self.subscriptions[name]['kwargs']['ids']
            )
        elif 'followers:' in name:
            SubscribeFollowerList(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                self.subscriptions[name]['kwargs']['since']
            )
        elif name == 'note-thread':
            SubscribeThread(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['root']
            )
        elif name == 'messages':
            SubscribeMessages(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                self.subscriptions[name]['kwargs']['since']
            )


SUBSCRIPTION_MANAGER = SubscriptionManager()
