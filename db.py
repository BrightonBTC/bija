import time
from os.path import exists

from sqlalchemy import create_engine, Column, Integer, String, Time
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
DB_ENGINE = create_engine("sqlite:///bija.sqlite", echo=True)
DB_SESSION = sessionmaker(autocommit=False, autoflush=False, bind=DB_ENGINE)

DEFAULT_RELAYS = [
    'wss://nostr.drss.io',
    'wss://nostr-pub.wellorder.net',
    'wss://nostr-relay.wlvs.space'
]


class BijaDB:

    def __init__(self, session):
        # self.db_engine = create_engine("sqlite:///2.sqlite", echo=True)
        # s = sessionmaker(bind=self.db_engine)
        self.session = session
        if not exists("bija.sqlite"):
            self.setup()

    def setup(self):
        Base.metadata.create_all(DB_ENGINE)
        relays = []
        for r in DEFAULT_RELAYS:
            relays.append(Relay(name=r))
        self.session.add_all(relays)
        self.session.commit()

    def get_relays(self):
        return self.session.query(Relay)

    def get_profile(self, public_key: String):
        return self.session.query(Profile).filter_by(public_key=public_key).first()

    def get_saved_pk(self):
        print("GET SAVED")
        pk = self.session.query(PK).first()
        return pk

    def save_pk(self, key, enc):
        self.session.add(PK(
            key=key,
            enc=enc
        ))
        self.session.commit()

    def add_profile(self,
                    public_key,
                    name=None,
                    nip05=None,
                    pic=None,
                    about=None,
                    updated_at=None):
        if updated_at is None:
            updated_at = int(time.time())
        self.session.add(Profile(
            public_key=public_key,
            name=name,
            nip05=nip05,
            pic=pic,
            about=about,
            updated_at=updated_at
        ))
        self.session.commit()

    def upd_profile(self,
                    public_key,
                    name=None,
                    nip05=None,
                    pic=None,
                    about=None,
                    updated_at=None):
        print("UPDATING PROFILE: ", public_key)
        self.session.merge(Profile(
            public_key=public_key,
            name=name,
            nip05=nip05,
            pic=pic,
            about=about,
            updated_at=updated_at
        ))
        self.session.commit()

    def insert_note(self,
                    note_id,
                    public_key,
                    content,
                    response_to=None,
                    thread_root=None,
                    created_at=None,
                    members=None):
        self.session.merge(Note(
            id=note_id,
            public_key=public_key,
            content=content,
            response_to=response_to,
            thread_root=thread_root,
            created_at=created_at,
            members=members
        ))
        self.session.commit()

    def insert_private_message(self,
                               msg_id,
                               public_key,
                               content,
                               to,
                               created_at):
        self.session.merge(PrivateMessage(
            id=msg_id,
            public_key=public_key,
            content=content,
            to=to,
            created_at=created_at,
        ))
        self.session.commit()

    def get_feed(self):
        return self.session.query(Note).order_by(Note.created_at.desc()).limit(50).all()

    def get_notes_by_pubkey(self, public_key):
        return self.session.query(Note).filter_by(public_key=public_key).order_by(Note.created_at.desc()).limit(
            50).all()

    def test(self):
        print("===============================================")


class Profile(Base):
    __tablename__ = "profile"
    public_key = Column(String(64), unique=True, primary_key=True)
    # private_key = Column(String(64))
    # ^ we'll keep the account owner here alongside follows but store priv encrypted elsewhere
    name = Column(String)
    nip05 = Column(String)
    pic = Column(String)
    about = Column(String)
    updated_at = Column(Integer)

    def __repr__(self):
        return {
            self.public_key,
            self.name,
            self.nip05,
            self.pic,
            self.about,
            self.updated_at
        }


class Note(Base):
    __tablename__ = "note"
    id = Column(String(64), unique=True, primary_key=True)
    public_key = Column(String(64))
    content = Column(String)
    response_to = Column(String(64))
    thread_root = Column(String(64))
    created_at = Column(Integer)
    members = Column(String)

    def __repr__(self):
        return {
            self.id,
            self.public_key,
            self.content,
            self.response_to,
            self.thread_root,
            self.about,
            self.created_at,
            self.members
        }


class PrivateMessage(Base):
    __tablename__ = "private_message"
    id = Column(String(64), unique=True, primary_key=True)
    public_key = Column(String(64))
    content = Column(String)
    to = Column(String(64))
    created_at = Column(Integer)

    def __repr__(self):
        return {
            self.id,
            self.public_key,
            self.content,
            self.to,
            self.created_at
        }


# Private keys
class PK(Base):
    __tablename__ = "PK"
    id = Column(Integer, primary_key=True)
    key = Column(String)
    enc = Column(Integer)  # boolean


class Relay(Base):
    __tablename__ = "relay"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
