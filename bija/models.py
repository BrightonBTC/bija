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
    raw = Column(String)


class Profile(Base):
    __tablename__ = "profile"
    public_key = Column(String(64), primary_key=True)
    name = Column(String, nullable=True)
    nip05 = Column(String, nullable=True)
    pic = Column(String, nullable=True)
    about = Column(String, nullable=True)
    updated_at = Column(Integer, default=0)
    nip05_validated = Column(Boolean, default=False)
    raw = Column(String)

    # followers = relationship(
    #     "Follower",
    #     back_populates="followers"
    # )
    # following = relationship(
    #     "Follower",
    #     primaryjoin="Follower.pk_2 == Profile.public_key",
    #     back_populates="following"
    # )
    notes = relationship("Note", back_populates="profile")

class Follower(Base):
    __tablename__ = "follower"
    id = Column(Integer, primary_key=True)
    pk_1 = Column(Integer, ForeignKey("profile.public_key"))
    pk_2 = Column(Integer, ForeignKey("profile.public_key"))

    # followers = relationship("Profile", back_populates="followers", foreign_keys=[pk_1])
    # following = relationship("Profile", back_populates="following", foreign_keys=[pk_2])
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
    raw = Column(String)


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
    id = Column(String(64), primary_key=True)  # the id of the new event
    kind = Column(Integer)
    event = Column(String(64))  # id of the event being referenced (commented on, liked...)
    profile = Column(String(64))
    ts = Column(Integer)
    content = Column(String)
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
