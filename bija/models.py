from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Event(Base):
    __tablename__ = "event"
    id = Column(String(64), primary_key=True)
    kind = Column(Integer)


class Profile(Base):
    __tablename__ = "profile"
    public_key = Column(String(64), unique=True, primary_key=True)
    name = Column(String)
    nip05 = Column(String)
    pic = Column(String)
    about = Column(String)
    updated_at = Column(Integer, default=0)
    following = Column(Boolean)
    contacts = Column(String)
    nip05_validated = Column(Boolean, default=False)
    raw = Column(String)

    notes = relationship("Note", back_populates="profile")

    def __repr__(self):
        return {
            self.public_key,
            self.name,
            self.nip05,
            self.pic,
            self.about,
            self.updated_at,
            self.following,
            self.contacts,
            self.nip05_validated,
            self.raw
        }


class Note(Base):
    __tablename__ = "note"
    id = Column(String(64), unique=True, primary_key=True)
    public_key = Column(String(64), ForeignKey("profile.public_key"))
    content = Column(String)
    response_to = Column(String(64))
    thread_root = Column(String(64))
    reshare = Column(String(64))
    created_at = Column(Integer)
    members = Column(String)
    media = Column(String)
    seen = Column(Boolean, default=False)
    liked = Column(Boolean, default=False)
    shared = Column(Boolean, default=False)
    raw = Column(String)
    deleted = Column(Integer)

    profile = relationship("Profile", back_populates="notes")

    def __repr__(self):
        return {
            self.id,
            self.public_key,
            self.content,
            self.response_to,
            self.thread_root,
            self.reshare,
            self.created_at,
            self.members,
            self.media,
            self.seen,
            self.liked,
            self.shared,
            self.raw,
            self.deleted
        }


class PrivateMessage(Base):
    __tablename__ = "private_message"
    id = Column(String(64), unique=True, primary_key=True)
    public_key = Column(String(64), ForeignKey("profile.public_key"))
    content = Column(String)
    is_sender = Column(Boolean)  # true = public_key is sender, false I'm sender
    created_at = Column(Integer)
    seen = Column(Boolean, default=False)
    raw = Column(String)

    def __repr__(self):
        return {
            self.id,
            self.public_key,
            self.content,
            self.is_sender,
            self.created_at,
            self.seen,
            self.raw
        }


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
