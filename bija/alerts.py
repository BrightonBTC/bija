import json
import time
from enum import IntEnum

from bija.app import app
from bija.db import BijaDB

DB = BijaDB(app.session)


class AlertKind(IntEnum):
    REPLY = 0
    MENTION = 1
    MENTION_IN_REPLY = 2
    REACTION = 3
    COMMENT_ON_THREAD = 4


class Alert:

    def __init__(self, eid, ts, kind: AlertKind, profile, event, content):
        self.eid = eid
        self.kind = kind
        self.profile = profile
        self.event = event
        self.ts = ts
        self.content = content

        self.store()

    # def get_unseen(self):
    #     unseen = DB.get_unseen_alerts(self.kind)
    #     if unseen is not None:
    #         for item in unseen:
    #             profiles = json.load(item.profiles)
    #             events = json.load(item.profiles)

    def store(self):
        DB.add_alert(self.eid, self.kind, self.profile, self.event, self.ts, self.content)

