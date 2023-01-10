from bija.app import app
from bija.config import default_settings, themes
from bija.db import BijaDB

DB = BijaDB(app.session)

class BijaSettings:

    items = {}

    def set_from_db(self):
        r = DB.get_settings()
        if len(r) < 1:
            self.set_defaults()
        for k in r.keys():
            self.set(k, r[k])

    def set(self, k, v, store_to_db=True):
        if store_to_db:
            DB.upd_setting(k, v)
        self.items[k] = v

    def get(self, k):
        if k in self.items:
            return self.items[k]
        return None

    def get_list(self, l:list[str]):
        out = {}
        for item in l:
            out[item] = self.get(item)
        return out


    def set_defaults(self):
        DB.upd_settings_by_keys(default_settings)
        DB.add_default_themes(themes)
        self.set_from_db()


Settings = BijaSettings()
Settings.set_from_db()
