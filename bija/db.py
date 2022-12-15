import json
import time

from sqlalchemy import create_engine, text, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, aliased
from sqlalchemy.sql import label

from bija.models import *

DB_ENGINE = create_engine("sqlite:///bija.sqlite", echo=False)
DB_SESSION = sessionmaker(autocommit=False, autoflush=False, bind=DB_ENGINE)


class BijaDB:

    def __init__(self, session):
        self.session = session
        Base.metadata.create_all(DB_ENGINE)

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

    def add_profile(self, public_key):
        self.session.add(Profile(
            public_key=public_key
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

    def set_follower(self, public_key, follower=True):
        self.session.merge(Profile(
            public_key=public_key,
            follower=follower
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

    # get basic info for a list of pubkeys
    def get_profile_briefs(self, public_keys: list):
        profiles = self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated).filter(Profile.public_key.in_(public_keys)).all()
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
        # return self.get_profile(public_key)

    def set_valid_nip05(self, public_key):
        self.session.query(Profile).filter(Profile.public_key == public_key).update({'nip05_validated': True})

    def update_note_media(self, note_id, media):
        self.session.query(Note).filter(Note.id == note_id).update({'media': media})
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
                    media='[]',
                    raw=None):
        note = self.session.query(Note.deleted).filter_by(id=note_id).first()
        if note is None or note.deleted is None:
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

    # def is_known_pubkey(self, pk):
    #     return self.session.query(Profile.public_key).filter_by(public_key=pk).first()

    def add_profile_if_not_exists(self, pk):
        self.session.merge(Profile(public_key=pk))
        self.session.commit()

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
                                  ReactionTally.likes,
                                  ReactionTally.replies,
                                  ReactionTally.shares,
                                  Note.liked,
                                  Note.shared,
                                  Note.deleted,
                                  Profile.name,
                                  Profile.pic,
                                  Profile.nip05,
                                  Profile.nip05_validated,
                                  Profile.following).filter_by(id=note_id) \
            .outerjoin(ReactionTally, ReactionTally.event_id == Note.id) \
            .join(Note.profile).first()

    def get_raw_note_data(self, note_id):
        return self.session.query(Note.raw).filter_by(id=note_id).first()

    def get_note_thread(self, note_id):

        like_counts = self.session.query(
            NoteReaction.id,
            NoteReaction.event_id,
            func.count(NoteReaction.id).label('likes')
        ).group_by(NoteReaction.event_id).subquery()

        items = self.session.query(Note.id, Note.response_to) \
            .filter(
            text("note.id='{}' or note.response_to='{}' or note.thread_root='{}'".format(note_id, note_id, note_id))) \
            .join(Note.profile).all()

        return self.session.query(Note.id,
                                  Note.public_key,
                                  Note.content,
                                  Note.response_to,
                                  Note.thread_root,
                                  Note.reshare,
                                  Note.created_at,
                                  Note.members,
                                  Note.media,
                                  Note.liked,
                                  Note.shared,
                                  Note.deleted,
                                  ReactionTally.likes,
                                  ReactionTally.replies,
                                  ReactionTally.shares,
                                  Profile.name,
                                  Profile.pic,
                                  Profile.nip05,
                                  Profile.nip05_validated,
                                  Profile.following) \
            .filter(or_(Note.id.in_([i.response_to for i in items]), Note.id.in_([i.id for i in items]))) \
            .outerjoin(ReactionTally, ReactionTally.event_id == Note.id) \
            .join(Note.profile).order_by(Note.created_at.asc()).all()

    def get_note_thread_ids(self, note_id):
        items = self.session.query(Note.id, Note.response_to, Note.thread_root, Note.reshare) \
            .filter(
            text("note.id='{}' or note.response_to='{}' or note.thread_root='{}'".format(note_id, note_id, note_id))) \
            .all()

        l1 = [i.id for i in items]
        l2 = [i.response_to for i in items]
        l3 = [i.thread_root for i in items]
        l4 = [i.reshare for i in items]

        out = list(dict.fromkeys(l1 + l2 + l3 + l4))
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
            Note.liked,
            Note.shared,
            Note.deleted,
            ReactionTally.likes,
            ReactionTally.replies,
            ReactionTally.shares,
            Profile.name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            Profile.following) \
            .outerjoin(ReactionTally, ReactionTally.event_id == Note.id) \
            .join(Note.profile) \
            .filter(text("note.created_at<{}".format(before))) \
            .filter(text("(profile.following=1 OR profile.public_key='{}')".format(public_key))) \
            .filter(text("note.deleted is not 1")) \
            .order_by(Note.created_at.desc()).limit(100).all()

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

        like_counts = self.session.query(
            NoteReaction.id,
            NoteReaction.event_id,
            func.count(NoteReaction.id).label('likes')
        ).group_by(NoteReaction.event_id).subquery()

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
            Note.liked,
            Note.shared,
            ReactionTally.likes,
            ReactionTally.replies,
            ReactionTally.shares,
            Note.deleted,
            Profile.name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            Profile.following) \
            .outerjoin(ReactionTally, ReactionTally.event_id == Note.id) \
            .join(Note.profile) \
            .filter(text("note.created_at<{}".format(before))) \
            .filter_by(public_key=public_key) \
            .filter(text("note.deleted is not 1")) \
            .order_by(Note.created_at.desc()).limit(100).all()

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

    def get_unseen_in_feed(self):
        return self.session.query(Note, Profile).join(Note.profile) \
            .filter(text("(profile.following=1) and note.seen=0")).count()

    def get_most_recent_for_pk(self, pubkey):
        q = self.session.query(Note.created_at).join(Note.profile) \
            .filter(text("profile.public_key='{}'".format(pubkey))).order_by(Note.created_at.desc()).first()
        if q is not None:
            return q['created_at']
        return None

    def set_all_seen_in_feed(self, public_key):
        notes = self.session.query(Note).join(Note.profile) \
            .filter(text("profile.following=1 OR profile.public_key='{}'".format(public_key)))
        for note in notes:
            note.seen = True
        self.session.commit()

    def set_note_seen(self, note_id):
        self.session.query(Note).filter(Note.id == note_id).update({'seen': True})
        self.session.commit()

    def get_profile_updates(self, public_key, last_update):
        return self.session.query(Profile).filter_by(public_key=public_key).filter(
            text("profile.updated_at>{}".format(last_update))).first()

    def search_profile_name(self, name_str):
        return self.session.query(Profile.name, Profile.nip05, Profile.public_key).filter(
            or_(
                Profile.name.like(f"{name_str}%"),
                Profile.public_key.like(f"{name_str}%")
            )
        ).order_by(Profile.following.desc()).limit(10).all()

    def get_profile_by_name_or_pk(self, name_str):
        return self.session.query(Profile.public_key).filter(
            or_(
                Profile.name == name_str,
                Profile.public_key == name_str
            )
        ).order_by(Profile.following.desc()).first()

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
        filter_text = "profile.public_key = private_message.public_key AND private_message.public_key='{}'"
        return self.session.query(
            PrivateMessage.is_sender,
            PrivateMessage.content,
            PrivateMessage.created_at,
            PrivateMessage.public_key,
            Profile.name,
            Profile.pic).join(Profile) \
            .filter(text(filter_text.format(public_key))) \
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

    def delete_reaction(self, reaction_id):
        self.session.query(Event).filter_by(id=reaction_id).delete()
        self.session.query(NoteReaction).filter_by(id=reaction_id).delete()
        self.session.commit()

    def set_note_liked(self, note_id, liked=True):
        self.session.merge(Note(
            id=note_id,
            liked=liked
        ))
        self.session.commit()

    def get_reaction_by_id(self, event_id):
        return self.session.query(NoteReaction.content).filter_by(id=event_id).first()

    def set_note_deleted(self, note_id, reason):
        self.session.merge(Note(
            id=note_id,
            content=reason,
            deleted=1
        ))
        self.session.commit()

    def get_like_count(self, note_id):
        return self.session.query(NoteReaction.event_id).filter(NoteReaction.event_id == note_id).filter(
            NoteReaction.content != '-').count()

    def get_like_events_for(self, note_id, public_key):
        return self.session.query(NoteReaction).filter(NoteReaction.event_id == note_id). \
            filter(NoteReaction.public_key == public_key).all()

    def add_event(self, event_id, kind):
        self.session.merge(Event(
            id=event_id,
            kind=kind
        ))
        self.session.commit()

    def get_event(self, event_id):
        return self.session.query(Event.id, Event.kind).filter(Event.id == event_id).first()

    def add_alert(self, event_id, kind, profile, event, ts, content):
        self.session.merge(Alert(
            id=event_id,
            kind=kind,
            profile=profile,
            event=event,
            ts=ts,
            content=content
        ))
        self.session.commit()

    def get_alerts(self):
        return self.session.query(
            Alert.id,
            Alert.kind,
            Alert.event,
            Alert.profile,
            Alert.content,
            Alert.seen,
            Profile.name,
            Profile.public_key,
            Profile.pic,
            label("note_id", Note.id),
            Note.thread_root,
            Note.response_to,
            label("note_content", Note.content)
        ) \
            .join(Note, Note.id == Alert.event) \
            .join(Profile, Profile.public_key == Alert.profile) \
            .order_by(Alert.ts.desc()).limit(50).all()

    def get_unread_alert_count(self):
        return self.session.query(Alert).filter(Alert.seen == 0).count()

    def set_alerts_read(self):
        self.session.query(Alert).filter(Alert.seen == 0).update({'seen': True})
        self.session.commit()

    def increment_note_reply_count(self, event_id):
        replies = 1
        tally = self.session.query(ReactionTally.replies).filter(ReactionTally.event_id == event_id).first()
        if tally is not None:
            replies = tally.replies + 1
        self.session.merge(ReactionTally(
            event_id=event_id,
            replies=replies
        ))
        self.session.commit()

    def increment_note_share_count(self, event_id):
        shares = 1
        tally = self.session.query(ReactionTally.shares).filter(ReactionTally.event_id == event_id).first()
        if tally is not None:
            shares = tally.shares + 1
        self.session.merge(ReactionTally(
            event_id=event_id,
            shares=shares
        ))
        self.session.commit()

    def increment_note_like_count(self, event_id):
        likes = 1
        tally = self.session.query(ReactionTally.likes).filter(ReactionTally.event_id == event_id).first()
        if tally is not None:
            likes = tally.likes + 1
        self.session.merge(ReactionTally(
            event_id=event_id,
            likes=likes
        ))
        self.session.commit()

    def commit(self):
        self.session.commit()
