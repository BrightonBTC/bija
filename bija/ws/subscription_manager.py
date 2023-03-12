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
        self.subscriptions[name] = {'batch_count': batch_count, 'kwargs': kwargs, 'relays': {}}
        self.subscribe(name, [])

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
        print('-------- NEXT ROUND')
        for relay in RELAY_MANAGER.relays:
            for s in RELAY_MANAGER.relays[relay].subscriptions:
                sub = RELAY_MANAGER.relays[relay].subscriptions[s]
                print('>>>>>>>>>> SUB', relay, s, sub.paused, sub.batch)
                if sub.paused and sub.paused < int(time.time()) - 30:
                    print('-------- SUBSCRIBE', relay, s)
                    sub.pause(False)
                    self.subscribe(s, [relay], 0, self.get_last_batch_upd(s, relay, 0))
                elif sub.ts < int(time.time()) - 180:
                    print('-------- REFRESH STALE', relay, s)
                    self.next_batch(relay, s)

    def next_batch(self, relay, name):
        print('-------- NEXT BATCH', relay, name)
        if name in self.subscriptions and self.subscriptions[name]['batch_count'] > 1:
            if relay in RELAY_MANAGER.relays and name in RELAY_MANAGER.relays[relay].subscriptions:

                if RELAY_MANAGER.relays[relay].subscriptions[name].batch >= self.subscriptions[name]['batch_count'] - 1:
                    RELAY_MANAGER.relays[relay].subscriptions[name].batch = 0
                    RELAY_MANAGER.relays[relay].subscriptions[name].pause(time.time())
                    print('>>>>>>>>>>>>>> PAUSE SUB', relay, name)
                else:
                    batch = RELAY_MANAGER.relays[relay].subscriptions[name].batch + 1
                    self.subscribe(
                        name,
                        [relay],
                        batch,
                        self.get_last_batch_upd(name, relay, batch)
                    )
                    print('>>>>>>>>>>>>>> DO SUB', relay, name)

    def get_last_batch_upd(self, sub, relay, batch):
        if sub in self.subscriptions and relay in self.subscriptions[sub]['relays']:
            if batch in self.subscriptions[sub]['relays'][relay]:
                return self.subscriptions[sub]['relays'][relay][batch]
        return None

    def subscribe(self, name, relays, batch=0, ts=None):

        for relay in relays:
            if relay not in self.subscriptions[name]['relays']:
                self.subscriptions[name]['relays'][relay] = {}
            self.subscriptions[name]['relays'][relay][batch] = int(time.time())

        if name == 'primary':
            SubscribePrimary(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                ts
            )
        elif name == 'main-feed':
            SubscribeFeed(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['ids'],
                ts
            )
        elif name == 'topic':
            SubscribeTopic(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['term'],
                ts
            )
        elif 'profile:' in name:
            if ts is not None:
                since = ts
            else:
                since = self.subscriptions[name]['kwargs']['since']
            SubscribeProfile(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                since,
                self.subscriptions[name]['kwargs']['ids']
            )
        elif 'followers:' in name:
            if ts is not None:
                since = ts
            else:
                since = self.subscriptions[name]['kwargs']['since']
            SubscribeFollowerList(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                since
            )
        elif name == 'note-thread':
            SubscribeThread(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['root']
            )
        elif name == 'messages':
            if ts is not None:
                since = ts
            else:
                since = self.subscriptions[name]['kwargs']['since']
            SubscribeMessages(
                name,
                relays,
                batch,
                self.subscriptions[name]['kwargs']['pubkey'],
                since
            )


SUBSCRIPTION_MANAGER = SubscriptionManager()
