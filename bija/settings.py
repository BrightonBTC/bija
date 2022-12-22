from bija.app import app
from bija.db import BijaDB

DB = BijaDB(app.session)


class BijaSettings:

    items = {}

    def set_from_db(self):
        r = DB.get_settings()
        for k in r.keys():
            self.set(k, r[k])

    def set(self, k, v):
        self.items[k] = v

    def get(self, k):
        if k in self.items:
            return self.items[k]
        return None


Settings = BijaSettings()
Settings.set_from_db()
