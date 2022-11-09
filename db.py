import time
from os.path import exists

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class BijaDB:

    def __init__(self):
        self.db_engine = create_engine("sqlite:///bija.sqlite", echo=True)
        s = sessionmaker(bind=self.db_engine)
        self.session = s()
        if not exists("bija.sqlite"):
            self.setup()

    def setup(self):
        Base.metadata.create_all(self.db_engine)

    def get_profile(self, public_key: String):
        return self.session.query(Profile).filter_by(public_key=public_key).first()

    def add_profile(self, p):
        self.session.add(p)


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
            self.private_key,
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


class Relay(Base):
    __tablename__ = "relay"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
