import json
from enum import IntEnum

from bija.app import app
from bija.db import BijaDB

DB = BijaDB(app.session)


class AlertKind(IntEnum):
    REPLY = 0
    MENTION = 1
    REACTION = 3
    COMMENT_ON_THREAD = 4
    FOLLOW = 5
    UNFOLLOW = 6


class Alert:

    def __init__(self, kind: AlertKind, ts, data):
        self.kind = kind
        self.ts = ts
        self.data = data
        self.store()


    def store(self):
        DB.add_alert(self.kind, self.ts, json.dumps(self.data))
