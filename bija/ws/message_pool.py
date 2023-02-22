import json
from queue import Queue
from threading import Lock
from bija.ws.message_type import RelayMessageType
from bija.ws.event import Event

class EventMessage:
    def __init__(self, event: Event, subscription_id: str, url: str) -> None:
        self.event = event
        self.subscription_id = subscription_id
        self.url = url

class NoticeMessage:
    def __init__(self, content: str, url: str) -> None:
        self.content = content
        self.url = url

class EndOfStoredEventsMessage:
    def __init__(self, subscription_id: str, url: str) -> None:
        self.subscription_id = subscription_id
        self.url = url

class OkMessage:
    def __init__(self, content: str, url: str) -> None:
        self.content = content
        self.url = url


class MessagePool:
    def __init__(self) -> None:
        self.events: Queue[EventMessage] = Queue()
        self.notices: Queue[NoticeMessage] = Queue()
        self.eose_notices: Queue[EndOfStoredEventsMessage] = Queue()
        self.ok_notices: Queue[OkMessage] = Queue()
        # self._unique_events: set = set()
        self.lock: Lock = Lock()
    
    def add_message(self, message: str, url: str):
        self._process_message(message, url)

    def get_event(self):
        return self.events.get()

    def get_notice(self):
        return self.notices.get()

    def get_eose_notice(self):
        return self.eose_notices.get()

    def get_ok_notice(self):
        return self.ok_notices.get()

    def has_events(self):
        return self.events.qsize() > 0

    def has_notices(self):
        return self.notices.qsize() > 0

    def has_eose_notices(self):
        return self.eose_notices.qsize() > 0

    def has_ok_notices(self):
        return self.ok_notices.qsize() > 0

    def _process_message(self, message: str, url: str):
        message_json = json.loads(message)
        message_type = message_json[0]
        if message_type == RelayMessageType.EVENT:
            subscription_id = message_json[1]
            e = message_json[2]
            event = Event(e['pubkey'], e['content'], e['created_at'], e['kind'], e['tags'], e['id'], e['sig'])
            self.events.put(EventMessage(event, subscription_id, url))
            # with self.lock:
            #     uid = subscription_id+event.id
            #     if not uid in self._unique_events:
            #         self.events.put(EventMessage(event, subscription_id, url))
            #         self._unique_events.add(uid)

        elif message_type == RelayMessageType.NOTICE:
            self.notices.put(NoticeMessage(message_json[1], url))
        elif message_type == RelayMessageType.END_OF_STORED_EVENTS:
            self.eose_notices.put(EndOfStoredEventsMessage(message_json[1], url))
        elif message_type == RelayMessageType.OK:
            self.ok_notices.put(OkMessage(message, url))


