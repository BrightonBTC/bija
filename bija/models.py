from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Event(Base):
    __tablename__ = "event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True)
    public_key = Column(String(64))
    kind = Column(Integer)
    ts = Column(Integer)


class EventRelay(Base):
    __tablename__ = "event_relay"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("event.id"))
    relay = Column(Integer, ForeignKey("relay.id"))

    UniqueConstraint(event_id, relay, name='uix_1', sqlite_on_conflict='IGNORE')


class Profile(Base):
    __tablename__ = "profile"
    id = Column(Integer, primary_key=True)
    public_key = Column(String(64), unique=True)
    name = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    nip05 = Column(String, nullable=True)
    pic = Column(String, nullable=True)
    about = Column(String, nullable=True)
    updated_at = Column(Integer, default=0)
    followers_upd = Column(Integer)
    nip05_validated = Column(Boolean, default=False)
    blocked = Column(Boolean, default=False)
    relays = Column(String)
    raw = Column(String)

    notes = relationship("Note", back_populates="profile")

class Follower(Base):
    __tablename__ = "follower"
    id = Column(Integer, primary_key=True)
    pk_1 = Column(Integer, ForeignKey("profile.public_key"))
    pk_2 = Column(Integer, ForeignKey("profile.public_key"))

    UniqueConstraint(pk_1, pk_2, name='uix_1', sqlite_on_conflict='IGNORE')


class Note(Base):
    __tablename__ = "note"
    id = Column(String(64), primary_key=True)
    public_key = Column(String(64), ForeignKey("profile.public_key"))
    content = Column(String)
    response_to = Column(String(64))
    thread_root = Column(String(64))
    reshare = Column(String(64))
    created_at = Column(Integer)
    members = Column(String)
    media = Column(String)
    hashtags = Column(String)
    seen = Column(Boolean, default=False)
    liked = Column(Boolean, default=False)
    shared = Column(Boolean, default=False)
    deleted = Column(Integer)
    raw = Column(String)

    profile = relationship("Profile", back_populates="notes")

class PrivateMessage(Base):
    __tablename__ = "private_message"
    id = Column(String(64), primary_key=True)
    public_key = Column(String(64), ForeignKey("profile.public_key"))
    content = Column(String)
    is_sender = Column(Boolean)  # true = public_key is sender, false I'm sender
    created_at = Column(Integer)
    seen = Column(Boolean, default=False)
    raw = Column(String)

class Topic(Base):
    __tablename__ = "topic"
    id = Column(Integer, primary_key=True)
    tag = Column(String, unique=True)

class Settings(Base):
    __tablename__ = "settings"
    key = Column(String(20), primary_key=True)
    name = Column(String)
    value = Column(String)


class NoteReaction(Base):
    __tablename__ = "note_reactions"
    id = Column(String, primary_key=True)
    public_key = Column(String)
    event_id = Column(Integer)
    event_pk = Column(Integer)
    content = Column(String(7))
    members = Column(String)


class MessageReaction(Base):
    __tablename__ = "message_reactions"
    id = Column(Integer, primary_key=True)
    public_key = Column(String)
    event = Column(Integer, ForeignKey("private_message.id"))
    content = Column(String(7))


class ReactionTally(Base):
    __tablename__ = "reaction_tally"
    event_id = Column(String(64), primary_key=True)
    likes = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    replies = Column(Integer, default=0)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    kind = Column(Integer)
    ts = Column(Integer)
    data = Column(String)
    seen = Column(Boolean, default=False)

class Theme(Base):
    __tablename__ = "theme"
    id = Column(Integer, primary_key=True)  # the id of the new event
    var = Column(String)
    val = Column(String)
    theme = Column(String)

# Private keys
class PK(Base):
    __tablename__ = "PK"
    id = Column(Integer, primary_key=True)
    key = Column(String)
    enc = Column(Boolean)  # boolean


class Relay(Base):
    __tablename__ = "relay"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    fav = Column(Boolean)
    send = Column(Boolean)
    receive = Column(Boolean)
    data = Column(String)


class URL(Base):
    __tablename__ = "url"
    address = Column(String, primary_key=True)
    ts = Column(Integer)
    og = Column(String)
