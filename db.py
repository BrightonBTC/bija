import time
from os.path import exists

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

DEFAULT_RELAYS = [
    'wss://nostr.drss.io',
    'wss://nostr-pub.wellorder.net',
    'wss://nostr-relay.wlvs.space'
]


class BijaDB:

    def __init__(self):
        self.db_engine = create_engine("sqlite:///bija.sqlite", echo=True)
        s = sessionmaker(bind=self.db_engine)
        self.session = s()
        if not exists("bija.sqlite"):
            self.setup()

    def setup(self):
        Base.metadata.create_all(self.db_engine)
        relays = []
        for r in DEFAULT_RELAYS:
            relays.append(Relay(name=r))
        self.session.add_all(relays)
        self.session.commit()

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
