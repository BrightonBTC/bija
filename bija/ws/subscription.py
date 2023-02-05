from bija.ws.filter import Filters

class Subscription:
    def __init__(self, id: str, filters: Filters=None, batch=0) -> None:
        self.id = id
        self.filters = filters
        self.batch = batch
        self.paused = False

    def to_json_object(self):
        return { 
            "id": self.id, 
            "filters": self.filters.to_json_array(),
            "batch": self.batch ,
            "paused": self.paused
        }
