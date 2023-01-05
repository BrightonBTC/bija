from bija.app import app
from bija.db import BijaDB

DB = BijaDB(app.session)

default_settings = {
    'pow_default': '12',
    'pow_default_enc': '12',
    'pow_required': '8',
    'pow_required_enc': '16'
}

class BijaSettings:

    items = {}

    def set_from_db(self):
        r = DB.get_settings()
        if len(r) < 1:
            self.set_defaults()
        for k in r.keys():
            self.set(k, r[k])

    def set(self, k, v):
        self.items[k] = v

    def get(self, k):
        if k in self.items:
            return self.items[k]
        return None

    def set_defaults(self):
        DB.upd_settings_by_keys(default_settings)


Settings = BijaSettings()
Settings.set_from_db()
