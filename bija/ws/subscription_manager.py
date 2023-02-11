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
        self.subscriptions[name] = {'batch_count': batch_count, 'kwargs': kwargs, 'paused': False}
        self.subscribe(name)

    def remove_subscription(self, name):
        self.subscriptions.pop(name)
        RELAY_MANAGER.close_subscription(name)

    def clear_subscriptions(self):
        for sub in self.subscriptions:
            if sub != 'primary':
                self.remove_subscription(sub)

    def next_round(self):

        for relay in RELAY_MANAGER.relays:
            print('-------------', relay)
            for s in RELAY_MANAGER.relays[relay].subscriptions:
                print(RELAY_MANAGER.relays[relay].subscriptions[s].to_json_object())
                # print(relay, '>>> ', RELAY_MANAGER.relays[relay].subscriptions[s].relay)
                sub = RELAY_MANAGER.relays[relay].subscriptions[s]
                print('subs in relay', len(RELAY_MANAGER.relays[relay].subscriptions))
                # print(sub.id, sub.relay, sub.paused, sub.batch)
                if sub.paused and sub.paused < int(time.time()) - 30:
                    print('SUBSCRIBE >>>>>', sub.id, sub.relay, sub.paused, sub.batch)
                    sub.paused = False
                    self.subscribe(s, [relay], 0)
            print('-------------')

    def next_batch(self, relay, name):

        if name in self.subscriptions and self.subscriptions[name]['batch_count'] > 1:
            print('==================')
            print('NEXT Batched Subscription', relay, name)
            if relay in RELAY_MANAGER.relays and name in RELAY_MANAGER.relays[relay].subscriptions:

                if RELAY_MANAGER.relays[relay].subscriptions[name].batch >= self.subscriptions[name]['batch_count'] - 1:
                    print('Batch limit reached, setting to 0 and pausing')
                    RELAY_MANAGER.relays[relay].subscriptions[name].batch = 0
                    RELAY_MANAGER.relays[relay].subscriptions[name].paused = time.time()
                else:
                    print('Resetting Subscription', name, relay, RELAY_MANAGER.relays[relay].subscriptions[name].batch + 1)
                    self.subscribe(
                        name,
                        [relay],
                        RELAY_MANAGER.relays[relay].subscriptions[name].batch + 1
                    )
            print('// ==================')


            # if relay in RELAY_MANAGER.relays:
            #     r = RELAY_MANAGER.relays[relay]
            #     if name in r.subscriptions:
            #         s = r.subscriptions[name]
            #         if s.batch >= self.subscriptions[name]['batch_count'] - 1:
            #             s.batch = 0
            #             r.subscriptions[name].paused = time.time()
            #             print('------------- PAUSED', r.subscriptions[name].id, r.subscriptions[name].relay, r.subscriptions[name].paused, r.subscriptions[name].batch)
            #         else:
            #             s.batch += 1
            #             self.subscribe(name, [relay], s.batch)

            # if self.subscriptions[name]['batch_pos'] >= self.subscriptions[name]['batch_count']-1:
            #     self.subscriptions[name]['batch_pos'] = 0
            #     self.subscriptions[name]['paused'] = time.time()
            # else:
            #     self.subscriptions[name]['batch_pos'] += 1
            #     self.subscribe(name)

    def subscribe(self, name, relay=[], batch=0):
        print('>>>> SUB', name, relay)
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
