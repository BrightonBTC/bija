import threading
from bija.ws.filter import Filters
from bija.ws.message_pool import MessagePool
from bija.ws.relay import Relay, RelayPolicy

class RelayManager:
    def __init__(self) -> None:
        self.relays: dict[str, Relay] = {}
        self.message_pool = MessagePool()

    def add_relay(self, url: str, read: bool=True, write: bool=True, subscriptions={}):
        policy = RelayPolicy(read, write)
        relay = Relay(url, policy, self.message_pool, subscriptions)
        self.relays[url] = relay

    def remove_relay(self, url: str):
        self.relays.pop(url)

    def add_subscription(self, id: str, filters: Filters, batch=0):
        for relay in self.relays.values():
            relay.add_subscription(id, filters, batch)

    def close_subscription(self, id: str):
        for relay in self.relays.values():
            relay.close_subscription(id)

    def open_connections(self, ssl_options: dict=None):
        for relay in self.relays.values():
            threading.Thread(
                target=relay.connect,
                args=(ssl_options,),
                name=f"{relay.url}-thread"
            ).start()

    def close_connections(self):
        for relay in self.relays.values():
            relay.close()

    def publish_message(self, message: str):
        for relay in self.relays.values():
            if relay.policy.should_write:
                relay.publish(message)

    def get_connection_status(self):
        out = []
        for relay in self.relays.values():
            out.append([relay.url, relay.active])
        return out

            
