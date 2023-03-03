from bija.ws.filter import Filters


class Subscription:
    def __init__(self, sub_id: str, filters: Filters = None, relay=None, batch=0) -> None:
        self.id = sub_id
        self.filters = filters
        self.relay = relay
        self.batch = batch
        self.paused = False

    def pause(self, b):
        self.paused = b

    def to_json_object(self):
        return {
            "id": self.id,
            "filters": self.filters.to_json_array(),
            "relay": self.relay,
            "batch": self.batch,
            "paused": self.paused
        }
