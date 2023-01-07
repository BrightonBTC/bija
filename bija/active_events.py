
class ActiveEvents:

    def __init__(self):
        self.notes = set()
        self.profiles = set()

    def add_notes(self, notes: list):
        self.notes = self.notes.union(notes)

    def add_profiles(self, profiles: list):
        self.profiles = self.profiles.union(profiles)

    def clear(self):
        self.notes = set()
        self.profiles = set()

