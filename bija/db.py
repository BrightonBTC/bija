import json
import time
from os.path import exists

from sqlalchemy import create_engine, Column, Integer, String, Time, ForeignKey, Boolean, text, distinct, func, or_
from sqlalchemy.orm import declarative_base, sessionmaker, join, relationship, subqueryload, aliased

Base = declarative_base()
DB_ENGINE = create_engine("sqlite:///bija.sqlite", echo=False)
DB_SESSION = sessionmaker(autocommit=False, autoflush=False, bind=DB_ENGINE)

DEFAULT_RELAYS = [
    'wss://nostr.drss.io',
    'wss://nostr-pub.wellorder.net',
    'wss://nostr-relay.wlvs.space'
]


class BijaDB:

    def __init__(self, session):
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

    def reset(self):
        self.session.query(Profile).delete()
        self.session.query(PrivateMessage).delete()
        self.session.query(Note).delete()
        self.session.query(PK).delete()
        self.session.commit()

    def get_relays(self):
        return self.session.query(Relay)

    def insert_relay(self, url):
        self.session.add(Relay(
            name=url
        ))
        self.session.commit()

    def remove_relay(self, url):
        self.session.query(Relay).filter_by(name=url).delete()
        self.session.commit()

    def get_preferred_relay(self):
        return self.session.query(Relay).first()

    def get_profile(self, public_key):
        return self.session.query(Profile).filter_by(public_key=public_key).first()

    def get_pk_by_nip05(self, nip05):
        return self.session.query(Profile.public_key).filter_by(nip05=nip05).first()

    def get_saved_pk(self):
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

    def add_contact_list(self, public_key, keys: list):
        self.session.merge(Profile(
            public_key=public_key,
            contacts=json.dumps(keys)
        ))
        self.session.commit()

    def set_following(self, keys_list, following=True):
        for public_key in keys_list:
            self.session.merge(Profile(
                public_key=public_key,
                following=following
            ))
        self.session.commit()

    def get_following_pubkeys(self):
        keys = self.session.query(Profile).filter_by(following=1).all()
        out = []
        for k in keys:
            out.append(k.public_key)
        return out

    def get_following(self):
        profiles = self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated).filter_by(following=1).all()
        out = []
        for p in profiles:
            out.append(dict(p))
        return out

    def upd_profile(self,
                    public_key,
                    name=None,
                    nip05=None,
                    pic=None,
                    about=None,
                    updated_at=None,
                    raw=None):
        self.session.merge(Profile(
            public_key=public_key,
            name=name,
            nip05=nip05,
            pic=pic,
            about=about,
            updated_at=updated_at,
            raw=raw
        ))
        self.session.commit()
        return self.session.query(Profile).filter_by(public_key=public_key).first()

    def set_valid_nip05(self, public_key):
        self.session.query(Profile).filter(Profile.public_key == public_key).update({'nip05_validated': True})
        self.session.commit()

    def insert_note(self,
                    note_id,
                    public_key,
                    content,
                    response_to=None,
                    thread_root=None,
                    reshare=None,
                    created_at=None,
                    members=None,
                    media=None,
                    raw=None):
        self.session.merge(Note(
            id=note_id,
            public_key=public_key,
            content=content,
            response_to=response_to,
            thread_root=thread_root,
            reshare=reshare,
            created_at=created_at,
            members=members,
            media=media,
            raw=raw
        ))
        self.session.commit()

    def is_note(self, note_id):
        return self.session.query(Note.id).filter_by(id=note_id).first()

    def is_known_pubkey(self, pk):
        return self.session.query(Profile.public_key).filter_by(public_key=pk).first()

    def get_note(self, note_id):
        return self.session.query(Note.id,
                                  Note.public_key,
                                  Note.content,
                                  Note.response_to,
                                  Note.thread_root,
                                  Note.reshare,
                                  Note.created_at,
                                  Note.members,
                                  Note.media,
                                  Profile.name,
                                  Profile.pic,
                                  Profile.nip05).filter_by(id=note_id).join(Note.profile).first()

    def get_raw_note_data(self, note_id):
        return self.session.query(Note.raw).filter_by(id=note_id).first()

    def get_note_thread(self, note_id):
        items = self.session.query(Note.id,
                                   Note.public_key,
                                   Note.content,
                                   Note.response_to,
                                   Note.thread_root,
                                   Note.reshare,
                                   Note.created_at,
                                   Note.members,
                                   Note.media,
                                   Profile.name,
                                   Profile.pic,
                                   Profile.nip05,
                                   Profile.nip05_validated) \
            .filter(
            text("note.id='{}' or note.response_to='{}' or note.thread_root='{}'".format(note_id, note_id, note_id))) \
            .join(Note.profile).order_by(Note.created_at.asc()).all()

        return self.session.query(Note.id,
                                  Note.public_key,
                                  Note.content,
                                  Note.response_to,
                                  Note.thread_root,
                                  Note.reshare,
                                  Note.created_at,
                                  Note.members,
                                  Note.media,
                                  Profile.name,
                                  Profile.pic,
                                  Profile.nip05,
                                  Profile.nip05_validated) \
            .filter(
            or_(
                Note.id.in_([i.response_to for i in items]),
                Note.id.in_([i.id for i in items])
            )
        ) \
            .join(Note.profile).order_by(Note.created_at.asc()).all()

    def get_note_thread_ids(self, note_id):
        items = self.session.query(Note.id, Note.response_to, Note.thread_root) \
            .filter(
            text("note.id='{}' or note.response_to='{}' or note.thread_root='{}'".format(note_id, note_id, note_id))) \
            .all()

        l1 = [i.id for i in items]
        l2 = [i.response_to for i in items]
        l3 = [i.thread_root for i in items]

        out = list(dict.fromkeys(l1 + l2 + l3))
        if None in out:
            out.remove(None)
            return out

    def insert_private_message(self,
                               msg_id,
                               public_key,
                               content,
                               is_sender,
                               created_at,
                               raw):
        self.session.merge(PrivateMessage(
            id=msg_id,
            public_key=public_key,
            content=content,
            is_sender=is_sender,
            created_at=created_at,
            raw=raw
        ))
        self.session.commit()

    def get_feed(self, before, public_key):
        return self.session.query(
            Note.id,
            Note.public_key,
            Note.content,
            Note.response_to,
            Note.thread_root,
            Note.reshare,
            Note.created_at,
            Note.members,
            Note.media,
            Profile.name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated).join(Note.profile).filter(text("note.created_at<{}".format(before))) \
            .filter(text("(profile.following=1 OR profile.public_key='{}')".format(public_key))) \
            .order_by(Note.created_at.desc()).limit(50).all()

    def get_note_by_id_list(self, note_ids):
        return self.session.query(
            Note.id,
            Note.public_key,
            Note.content,
            Note.created_at,
            Note.members,
            Note.media,
            Profile.name,
            Profile.pic,
            Profile.nip05).join(Note.profile).filter(Note.id.in_(note_ids)).all()

    def get_notes_by_pubkey(self, public_key, before, after):
        return self.session.query(
            Note.id,
            Note.public_key,
            Note.content,
            Note.response_to,
            Note.thread_root,
            Note.reshare,
            Note.created_at,
            Note.members,
            Note.media,
            Profile.name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated).join(Note.profile).filter(text("note.created_at<{}".format(before))).filter_by(
            public_key=public_key).order_by(Note.created_at.desc()).limit(50).all()

    def get_unseen_message_count(self):
        return self.session.query(PrivateMessage) \
            .filter(text("seen=0")).count()

    def get_unseen_messages(self, public_key):
        out = []
        filter_string = """profile.public_key = private_message.public_key
         AND private_message.public_key='{}'
         AND seen=0""".format(public_key)
        result = self.session.query(
            PrivateMessage.id,
            PrivateMessage.public_key,
            PrivateMessage.created_at,
            PrivateMessage.content,
            PrivateMessage.is_sender,
            Profile.name,
            Profile.pic).join(Profile) \
            .filter(text(filter_string)).all()
        for item in result:
            out.append(dict(item))
        return out

    def get_unseen_in_feed(self, public_key):
        return self.session.query(Note, Profile).join(Note.profile) \
            .filter(text("(profile.following=1 OR profile.public_key='{}') and note.seen=0".format(public_key))).count()

    def set_all_seen_in_feed(self, public_key):
        notes = self.session.query(Note).join(Note.profile) \
            .filter(text("profile.following=1 OR profile.public_key='{}'".format(public_key)))
        for note in notes:
            note.seen = True
        self.session.commit()

    def get_profile_updates(self, public_key, last_update):
        return self.session.query(Profile).filter_by(public_key=public_key).filter(
            text("profile.updated_at>{}".format(last_update))).first()

    def get_message_list(self):
        return DB_ENGINE.execute(text("""SELECT 
                max(PM2.created_at) AS last_message, 
                profile.public_key AS public_key, 
                profile.name AS name, 
                profile.pic AS pic, 
                PM2.is_sender AS is_sender, 
                (select count(id) from private_message PM where PM.seen=0 AND PM.public_key=PM2.public_key) AS n 
                FROM private_message PM2 JOIN profile ON profile.public_key = PM2.public_key GROUP BY PM2.public_key 
                ORDER BY PM2.created_at DESC"""))

    def get_message_thread(self, public_key):
        self.set_message_thread_read(public_key)
        return self.session.query(
            PrivateMessage.is_sender,
            PrivateMessage.content,
            PrivateMessage.created_at,
            PrivateMessage.public_key,
            Profile.name,
            Profile.pic).join(Profile) \
            .filter(text(
            "profile.public_key = private_message.public_key AND private_message.public_key='{}'".format(public_key))) \
            .order_by(PrivateMessage.created_at.desc()).limit(100).all()

    def set_message_thread_read(self, public_key):
        self.session.query(PrivateMessage).filter(PrivateMessage.public_key == public_key).update({'seen': True})
        self.session.commit()

    def add_note_reaction(self, eid, public_key, event_id, event_pk, content, members, raw):
        self.session.merge(NoteReaction(
            id=eid,
            public_key=public_key,
            event_id=event_id,
            event_pk=event_pk,
            content=content,
            members=members,
            raw=raw
        ))
        self.session.commit()

    def get_like_count(self, note_id):
        return self.session.query(NoteReaction.event_id).filter(NoteReaction.event_id == note_id).filter(NoteReaction.content != '-').count()


class Profile(Base):
    __tablename__ = "profile"
    public_key = Column(String(64), unique=True, primary_key=True)
    name = Column(String)
    nip05 = Column(String)
    pic = Column(String)
    about = Column(String)
    updated_at = Column(Integer)
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
    raw = Column(String)

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
            self.raw
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
