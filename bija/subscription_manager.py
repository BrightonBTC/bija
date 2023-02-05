import logging
import time

from bija.app import app, RELAY_MANAGER
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.subscriptions import SubscribeThread, SubscribePrimary, SubscribeFeed, SubscribeProfile, SubscribeTopic

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

class SubscriptionManager:
    def __init__(self):
        self.should_run = True
        self.max_connected_relays = 5
        self.subscriptions = {}

    def add_subscription(self, name, batch_count, **kwargs):
        self.subscriptions[name] = {'batch_count':batch_count, 'kwargs': kwargs, 'paused':False}
        self.subscribe(name)

    def remove_subscription(self, name):
        self.subscriptions.pop(name)

    def clear_subscriptions(self):
        for sub in self.subscriptions:
            if sub != 'primary':
                self.subscriptions.pop(sub)

    def next_batch(self, relay, name):

        if name in self.subscriptions and self.subscriptions[name]['batch_count'] > 1 :
            if relay in RELAY_MANAGER.relays:
                r = RELAY_MANAGER.relays[relay]
                if name in r.subscriptions:
                    s = r.subscriptions[name]
                    if s.batch >= self.subscriptions[name]['batch_count'] - 1:
                        s.batch = 0
                        s.paused = time.time()
                    else:
                        s.batch += 1
                        self.subscribe(name, [relay], s.batch)


            # if self.subscriptions[name]['batch_pos'] >= self.subscriptions[name]['batch_count']-1:
            #     self.subscriptions[name]['batch_pos'] = 0
            #     self.subscriptions[name]['paused'] = time.time()
            # else:
            #     self.subscriptions[name]['batch_pos'] += 1
            #     self.subscribe(name)

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
        elif name == 'profile':
            SubscribeProfile(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                self.subscriptions[name]['kwargs']['since'],
                self.subscriptions[name]['kwargs']['ids']
            )
        elif name == 'note-thread':
            SubscribeThread(
                name,
                relay,
                batch,
                self.subscriptions[name]['kwargs']['root']
            )


SUBSCRIPTION_MANAGER = SubscriptionManager()


