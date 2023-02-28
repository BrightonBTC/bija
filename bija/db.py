import json
import logging
import time

from sqlalchemy import create_engine, text, func, or_, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, aliased
from sqlalchemy.sql import label
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy.sql.functions import coalesce
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from bija.args import args
from bija.helpers import is_hex_key
from bija.models import *

DB_ENGINE = create_engine("sqlite:///{}.sqlite".format(args.db), echo=False, poolclass=SingletonThreadPool, pool_size=10)
DB_SESSION = sessionmaker(autocommit=False, autoflush=False, bind=DB_ENGINE)

logging.basicConfig()
logger = logging.getLogger("sqlalchemy.engine")
logger.setLevel(logging.ERROR)
fh = logging.FileHandler('db.log')
logger.addHandler(fh)

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

    def get_relays(self, fav=None, send=None, receive=None):
        q = self.session.query(Relay)
        if fav is not None:
            q = q.filter(Relay.fav == True)
        if send is not None:
            q = q.filter(Relay.send == True)
        if receive is not None:
            q = q.filter(Relay.receive == True)
        return q.all()

    def get_relay_by_url(self, url):
        return self.session.query(Relay).filter_by(name=url).first()

    def insert_relay(self, url, fav=None, send=True, receive=True, data=""):
        self.session.merge(Relay(
            name=url,
            fav=fav,
            send=send,
            receive=receive,
            data=data
        ))
        self.session.commit()

    def update_relay(self, url, setting, state: bool):
        if setting in ['send', 'receive', 'fav']:
            self.session.query(Relay).filter_by(name=url).update({setting: state})
            self.session.commit()

    def remove_relay(self, url):
        self.session.query(Relay).filter_by(name=url).delete()
        self.session.commit()

    def get_preferred_relay(self):
        return self.session.query(Relay).first()

    def get_profile(self, public_key):
        return self.session.query(Profile).filter_by(public_key=public_key).first()

    def get_profile_detailed(self, my_pk, public_key):
        sq_following = self.session.query(func.count(Follower.id).label('count')) \
            .filter(Follower.pk_1 == my_pk) \
            .filter(Follower.pk_2 == Profile.public_key).scalar_subquery()
        return self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            Profile.blocked,
            label('following', sq_following)).filter_by(public_key=public_key).first()

    def get_profile_by_id(self, id):
        return self.session.query(Profile).filter_by(id=id).first()

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

    def add_contact_lists(self, my_pk, lists:dict):
        inserts = []
        new_follows = []
        new_unfollows = []
        is_mine = False
        for pk, item in lists.items():
            if is_hex_key(pk):
                following = self.get_following_pubkeys(pk)
                new = set(item['pks']) - set(following)
                removed = set(following) - set(item['pks'])
                for pk2 in new:
                    if is_hex_key(pk2):
                        inserts.append({'pk_1':pk, 'pk_2':pk2})
                self.session.query(Follower).filter(Follower.pk_1 == pk).filter(Follower.pk_2.in_(removed)).delete()
                self.session.commit()

                if pk == my_pk:
                    is_mine = True
                if my_pk in new:
                    new_follows.append(pk)
                if my_pk in removed:
                    new_unfollows.append(pk)
        if len(inserts) > 0:

            chunked_lists = [inserts[i:i + 999] for i in range(0, len(inserts), 999)]

            for l in chunked_lists:

                stmt = sqlite_upsert(Follower).values(l)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=[Follower.pk_1, Follower.pk_2]
                )
                try:
                    self.session.execute(stmt)
                    self.session.commit()
                except SQLAlchemyError as e:
                    print(str(e.__dict__['orig']))

        return new_follows, new_unfollows, is_mine

    def update_followers_list(self, my_pk, followers:list):

        inserts = []
        new_follows = []
        new_unfollows = []
        is_mine = False

        for item in list(followers):
            if item['action'] == 'del':
                self.session.query(Follower).filter(Follower.pk_1 == item['pk_1']).filter(Follower.pk_2 == item['pk_2']).delete()

                if item['pk_2'] == my_pk:
                    new_follows.append(item['pk_1'])
            elif item['action'] == 'add':
                inserts.append({'pk_1': item['pk_1'], 'pk_2': item['pk_2']})
                if item['pk_2'] == my_pk:
                    new_unfollows.append(item['pk_1'])

            if item['pk_1'] == my_pk:
                is_mine = True

        self.session.commit()

        if len(inserts) > 0:

            chunked_lists = [inserts[i:i + 999] for i in range(0, len(inserts), 999)]

            for l in chunked_lists:

                stmt = sqlite_upsert(Follower).values(l)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=[Follower.pk_1, Follower.pk_2]
                )
                try:
                    self.session.execute(stmt)
                    self.session.commit()
                except SQLAlchemyError as e:
                    print(str(e.__dict__['orig']))

        return new_follows, new_unfollows, is_mine

    def update_block_list(self, profiles: list):
        self.session.query(Profile).filter(Profile.public_key.in_(profiles)).update({'blocked': True})
        self.session.query(Profile).filter(Profile.blocked==True).filter(Profile.public_key.notin_(profiles)).update({'blocked': False})
        self.session.commit()

    def unblock(self, pubkey: str):
        self.session.query(Profile).filter(Profile.public_key == pubkey).update({'blocked': False})
        self.session.commit()

    def get_blocked(self):
        return self.session.query(Profile).filter(Profile.blocked == True).all()

    def get_blocked_pks(self):
        results = self.session.query(Profile.public_key).filter(Profile.blocked == True).all()
        return [x.public_key for x in results]

    def is_blocked(self, pubkey):
        q = self.session.query(Profile.blocked).filter(Profile.public_key==pubkey).first()
        return q.blocked

    def get_last_contacts_upd(self, public_key):
        result = self.session.query(Event.ts) \
            .filter(Event.public_key == public_key) \
            .filter(Event.kind == 3).order_by(Event.ts.desc()).first()
        if result is not None:
            return result.ts
        return None

    def set_following(self, my_pk, their_pk, following=True):
        if following:
            self.session.merge(Follower(
                pk_1=my_pk,
                pk_2=their_pk
            ))
        else:
            self.session.query(Follower).filter(Follower.pk_1==my_pk).filter(Follower.pk_2==their_pk).delete()
        self.session.commit()

    def get_following_pubkeys(self, public_key, start=None, end=None):
        if start is not None and end is not None:
            keys = self.session.query(Follower).filter_by(pk_1=public_key)[start:end]
        else:
            keys = self.session.query(Follower).filter_by(pk_1=public_key).all()
        out = []
        for k in keys:
            out.append(k.pk_2)
        return out

    def get_follower_pubkeys(self, public_key, start=None, end=None):
        if start is not None and end is not None:
            keys = self.session.query(Follower).filter_by(pk_2=public_key)[start:end]
        else:
            keys = self.session.query(Follower).filter_by(pk_2=public_key).all()
        out = []
        for k in keys:
            out.append(k.pk_1)
        return out

    def get_following(self, my_pk, public_key, page=0, count=False):
        following_counts = self.session.query(
            Follower.pk_1,
            Follower.pk_2,
            func.count(Follower.id).label('count')
        ).group_by(Follower.id).subquery()

        am_following = coalesce(
            following_counts.c.count, 0
        )
        profiles = self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            label('following', am_following)
        )
        profiles = profiles.join(Follower, Follower.pk_2==Profile.public_key)
        profiles = profiles.outerjoin(following_counts,
                        and_(following_counts.c.pk_1 == my_pk, following_counts.c.pk_2 == Profile.public_key))
        profiles = profiles.filter(Follower.pk_1==public_key)
        if count:
            return profiles.count()
        n = 20*page
        return profiles.all()[n:n+20]

    def get_followers(self, my_pk, public_key, page=0, count=False):
        following_counts = self.session.query(
            Follower.pk_1,
            Follower.pk_2,
            func.count(Follower.id).label('count')
        ).group_by(Follower.id).subquery()

        am_following = coalesce(
            following_counts.c.count, 0
        )
        profiles = self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            label('following', am_following)
        )
        profiles = profiles.join(Follower, Follower.pk_1==Profile.public_key)
        profiles = profiles.outerjoin(following_counts,
                        and_(following_counts.c.pk_1 == my_pk, following_counts.c.pk_2 == Profile.public_key))
        profiles = profiles.filter(Follower.pk_2==public_key)
        if count:
            return profiles.count()
        n = 20 * page
        return profiles.all()[n:n + 20]

    def get_followers_last_upd(self, public_key):
        q = self.session.query(Profile.followers_upd).filter(Profile.public_key == public_key).first()
        if q is not None:
            return q.followers_upd
        else:
            return 0

    def set_followers_last_upd(self, public_key):
        self.session.query(Profile).filter(Profile.public_key == public_key).update({'followers_upd': int(time.time())})
        self.session.commit()

    def a_follows_b(self, pk_a, pk_b):
        r = self.session.query(Follower).filter(Follower.pk_1==pk_a).filter(Follower.pk_2==pk_b)
        return r.first() is not None

    def get_profile_last_upd(self, public_key):
        return self.session.query(Profile.updated_at).filter_by(public_key=public_key).first()

    # get basic info for a list of pubkeys
    def get_profile_briefs(self, public_keys: list):
        profiles = self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated).filter(Profile.public_key.in_(public_keys)).all()
        out = []
        for p in profiles:
            out.append(dict(p))
        return out

    def update_profiles(self, profiles:list):
        chunked_lists = [profiles[i:i + 999] for i in range(0, len(profiles), 999)]

        for l in chunked_lists:
            stmt = sqlite_upsert(Profile).values(l)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Profile.public_key],
                set_=dict(
                    name=stmt.excluded.name,
                    display_name=stmt.excluded.display_name,
                    nip05=stmt.excluded.nip05,
                    pic=stmt.excluded.pic,
                    about=stmt.excluded.about,
                    updated_at=stmt.excluded.updated_at,
                    raw=stmt.excluded.raw
                )
            )
            try:
                self.session.execute(stmt)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))


    def upd_profile(self,
                    public_key,
                    name=None,
                    display_name=None,
                    nip05=None,
                    pic=None,
                    about=None,
                    updated_at=None,
                    raw=None):
        self.session.merge(Profile(
            public_key=public_key,
            name=name,
            display_name=display_name,
            nip05=nip05,
            pic=pic,
            about=about,
            updated_at=updated_at,
            raw=raw
        ))
        self.session.commit()

    def set_valid_nip05(self, public_key, validated=True):
        self.session.query(Profile).filter(Profile.public_key == public_key).update({'nip05_validated': validated})
        self.session.commit()

    def update_note_media(self, note_id, media):
        self.session.query(Note).filter(Note.id == note_id).update({'media': media})
        self.session.commit()

    def insert_notes(self, notes:list):
        chunked_lists = [notes[i:i + 999] for i in range(0, len(notes), 999)]

        for l in chunked_lists:
            stmt = sqlite_upsert(Note).values(l)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Note.id],
                set_=dict(
                    public_key=stmt.excluded.public_key,
                    content=stmt.excluded.content,
                    response_to=stmt.excluded.response_to,
                    thread_root=stmt.excluded.thread_root,
                    reshare=stmt.excluded.reshare,
                    created_at=stmt.excluded.created_at,
                    members=stmt.excluded.members,
                    media=stmt.excluded.media,
                    hashtags=stmt.excluded.hashtags,
                    seen=stmt.excluded.seen,
                    raw=stmt.excluded.raw
                )
            )
            try:
                self.session.execute(stmt)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))

        # a = []
        # for n in notes:
        #     print('RAW', n['raw'])
        #     a.append(Note(
        #         id=n['id'],
        #         public_key=n['public_key'],
        #         content=n['content'],
        #         response_to=n['response_to'],
        #         thread_root=n['thread_root'],
        #         reshare=n['reshare'],
        #         created_at=n['created_at'],
        #         members=n['members'],
        #         media=n['media'],
        #         hashtags=n['hashtags'],
        #         raw=n['raw']
        #     ))
        # print('attempt to insert {} notes'.format(len(a)))
        # self.session.bulk_save_objects(a)
        # print('inserted {} notes'.format(len(a)))
        # self.session.commit()

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
                    hashtags='[]'):
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
                hashtags=hashtags
            ))
            self.session.commit()

    def is_note(self, note_id):
        return self.session.query(Note.id).filter_by(id=note_id).first()

    def add_profiles_if_not_exists(self, pks:list):
        results = self.session.query(Profile.public_key).filter(Profile.public_key.in_(pks)).all()
        if results is not None:
            existing_pks = [x.public_key for x in results]
            pks = [x for x in pks if x not in existing_pks]
        items = []
        if len(pks) > 0:
            for pk in set(pks):
                items.append(Profile(public_key=pk))
            try:
                self.session.bulk_save_objects(items)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))


    def get_note(self, public_key, note_id):


        sq_following = self.session.query(func.count(Follower.id).label('count'))\
            .filter(Follower.pk_1 == public_key)\
            .filter(Follower.pk_2 == Profile.public_key).scalar_subquery()

        sq_follower = self.session.query(func.count(Follower.id).label('count'))\
            .filter(Follower.pk_2 == public_key)\
            .filter(Follower.pk_1 == Profile.public_key).scalar_subquery()

        q = self.session.query(Note.id,
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
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            label('is_follower', sq_follower),
            label('following', sq_following)
        )
        q = q.filter_by(id=note_id)
        q = q.join(Note.profile)
        q = q.outerjoin(ReactionTally, ReactionTally.event_id == Note.id)

        return q.first()

    def get_raw_note_data(self, note_id):
        return self.session.query(Note.raw).filter_by(id=note_id).first()

    def get_note_thread(self, public_key, note_id):


        sq_following = self.session.query(func.count(Follower.id).label('count'))\
            .filter(Follower.pk_1 == public_key)\
            .filter(Follower.pk_2 == Profile.public_key).scalar_subquery()

        sq_follower = self.session.query(func.count(Follower.id).label('count'))\
            .filter(Follower.pk_2 == public_key)\
            .filter(Follower.pk_1 == Profile.public_key).scalar_subquery()

        items = self.session.query(Note.id, Note.response_to) \
            .filter(
            text("note.id='{}' or note.response_to='{}' or note.thread_root='{}'".format(note_id, note_id, note_id))) \
            .join(Note.profile).all()

        q = self.session.query(
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
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            label('is_follower', sq_follower),
            label('following', sq_following)
        )
        q = q.join(Note.profile)
        q = q.outerjoin(ReactionTally, ReactionTally.event_id == Note.id)
        q = q.filter(or_(Note.id.in_([i.response_to for i in items]), Note.id.in_([i.id for i in items])))
        q = q.order_by(Note.created_at.asc())

        return q.all()

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

    def insert_direct_messages(self, msgs:list):
        chunked_lists = [msgs[i:i + 999] for i in range(0, len(msgs), 999)]
        for l in chunked_lists:
            stmt = sqlite_upsert(PrivateMessage).values(l)
            stmt = stmt.on_conflict_do_update(
                index_elements=[PrivateMessage.id],
                set_=dict(
                    public_key=stmt.excluded.public_key,
                    content=stmt.excluded.content,
                    is_sender=stmt.excluded.is_sender,
                    created_at=stmt.excluded.created_at,
                    seen=stmt.excluded.seen,
                    passed=stmt.excluded.passed,
                    raw=stmt.excluded.raw
                )
            )
            try:
                self.session.execute(stmt)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))

    def inbox_allowed(self, pk):
        q = self.session.query(PrivateMessage.id).filter(PrivateMessage.public_key == pk).filter(PrivateMessage.passed == True).first()
        if q is not None:
            return True
        else:
            return False

    def move_to_inbox(self, pk):
        self.session.query(PrivateMessage).filter(PrivateMessage.public_key == pk).update({'passed': True})
        self.session.commit()

    def purge_pubkey(self, pk):
        self.session.query(PrivateMessage).filter(PrivateMessage.public_key == pk).delete()
        self.session.query(Note).filter(Note.public_key == pk).delete()
        self.session.commit()

    def subscribed_to_topic(self, topic):
        r = self.session.query(Topic).filter_by(tag=topic).first()
        return r is not None

    def subscribe_to_topic(self, topic):
        self.session.merge(Topic(
            tag=topic
        ))
        self.session.commit()

    def unsubscribe_from_topic(self, topic):
        self.session.query(Topic).filter_by(tag=topic).delete()
        self.session.commit()

    def get_topics(self):
        return self.session.query(Topic.tag).all()

    def save_list(self, name, public_key, content):
        self.session.merge(List(
            name=name,
            public_key=public_key,
            list=content
        ))
        self.session.commit()

    def get_lists(self, pubkey):
        return self.session.query(List).filter(List.public_key == pubkey).order_by(List.id.desc()).all()

    def get_list(self, pubkey, name):
        return self.session.query(List).filter(List.public_key == pubkey).filter(List.name == name).first()

    def get_list_by_id(self, list_id):
        return self.session.query(List).filter(List.id == list_id).first()

    def get_list_members(self, list_id):
        l = self.get_list_by_id(list_id)
        if l is not None:
            pks = json.loads(l.list)
            pks = [x[1] for x in pks]
            return self.session.query(Profile).filter(Profile.public_key.in_(pks)).all()

    def empty_topics(self):
        self.session.query(Topic).delete()

    def get_unseen_in_topics(self, topics):
        out = {}
        for topic in topics:
            n = self.session.query(Note).filter(text("seen=0")).filter(Note.hashtags.like(f"%\"{topic}\"%")).count()
            out[topic] = n
        if len(out) > 0:
            return out
        return None

    def get_notes_by_id_list(self, note_ids):
        return self.session.query(Note).filter(Note.id.in_(note_ids)).all()

    def get_unseen_message_count(self):
        return self.session.query(PrivateMessage) \
            .filter(text("seen=0 AND passed=1")).count()

    def get_unseen_messages(self, public_key):
        out = []
        filter_string = """profile.public_key = private_message.public_key
         AND private_message.public_key='{}'
         AND seen=0
         AND passed=1""".format(public_key)
        result = self.session.query(
            PrivateMessage.id,
            PrivateMessage.public_key,
            PrivateMessage.created_at,
            PrivateMessage.content,
            PrivateMessage.is_sender,
            Profile.name,
            Profile.display_name,
            Profile.pic).join(Profile) \
            .filter(text(filter_string)).all()
        for item in result:
            out.append(dict(item))
        return out

    def get_unseen_in_feed(self, public_key):

        following_counts = self.session.query(
            Follower.pk_1,
            Follower.pk_2,
            func.count(Follower.id).label('count')
        ).group_by(Follower.id).subquery()

        am_following = coalesce(
            following_counts.c.count, 0
        )
        q = self.session.query(Note, Profile, label('following', am_following))
        q = q.join(Note.profile)
        q = q.outerjoin(following_counts,
                        and_(following_counts.c.pk_1 == public_key, following_counts.c.pk_2 == Profile.public_key))
        q = q.filter(text("following=1 and note.seen=0"))
        return q.count()

    def get_most_recent_for_pk(self, pubkey):
        q = self.session.query(Note.created_at).join(Note.profile) \
            .filter(text("profile.public_key='{}'".format(pubkey))).order_by(Note.created_at.desc()).first()
        if q is not None:
            return q['created_at']
        return None

    def latest_in_primary(self, pubkey):
        following_counts = self.session.query(
            Follower.pk_1,
            Follower.pk_2,
            func.count(Follower.id).label('count')
        ).group_by(Follower.id).subquery()

        am_following = coalesce(
            following_counts.c.count, 0
        )
        q = self.session.query(
            Note.created_at,
            label('following', am_following)
        )
        q = q.join(Note.profile)
        q = q.outerjoin(following_counts,
                        and_(following_counts.c.pk_1 == pubkey, following_counts.c.pk_2 == Profile.public_key))
        q = q.filter(text("(following=1 OR profile.public_key='{}')".format(pubkey))).order_by(Note.created_at.desc()).first()
        if q is not None:
            return q['created_at']
        return None


    def set_all_seen_in_feed(self, public_key):
        following_counts = self.session.query(
            Follower.pk_1,
            Follower.pk_2,
            func.count(Follower.id).label('count')
        ).group_by(Follower.id).subquery()

        am_following = coalesce(
            following_counts.c.count, 0
        )
        q = self.session.query(Note.id, Note.seen, label('following', am_following))
        q = q.join(Note.profile)
        q = q.outerjoin(following_counts,
                        and_(following_counts.c.pk_1 == public_key, following_counts.c.pk_2 == Profile.public_key))
        q = q.filter(text("(following=1 OR profile.public_key='{}') and note.seen=0".format(public_key))).all()

        self.session.query(Note).filter(Note.id.in_([x.id for x in q])).update({'seen': True})
        self.session.commit()

    def set_all_seen_in_topic(self, topic):
        notes = self.session.query(Note).filter(Note.hashtags.like(f"%\"{topic}\"%"))
        for note in notes:
            note.seen = True
        self.session.commit()

    def set_note_seen(self, note_id):
        self.session.query(Note).filter(Note.id == note_id).update({'seen': True})
        self.session.commit()

    def set_note_boosted(self, note_id):
        self.session.query(Note).filter(Note.id == note_id).update({'shared': True})
        self.session.commit()

    def search_profile_name(self, name_str):
        return self.session.query(Profile.name, Profile.nip05, Profile.public_key, Profile.pic).filter(
            or_(
                Profile.name.like(f"{name_str}%"),
                Profile.public_key.like(f"{name_str}%")
            )
        ).limit(10).all()

    def get_profile_by_name_or_pk(self, name_str):
        return self.session.query(Profile.public_key).filter(
            or_(
                Profile.name == name_str,
                Profile.public_key == name_str
            )
        ).first()

    def get_message_list(self, passed=True):
        PM2 = aliased(PrivateMessage)
        n_unseen = self.session.query(func.count(PM2.id).label('count')) \
            .filter(PM2.seen == False) \
            .filter(PM2.public_key == PrivateMessage.public_key).scalar_subquery()
        return self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.display_name,
            Profile.pic,
            func.max(PrivateMessage.created_at).label('last_message'),
            PrivateMessage.is_sender,
            PrivateMessage.content,
            label('n', n_unseen))\
            .outerjoin(Profile, Profile.public_key == PrivateMessage.public_key).filter(PrivateMessage.passed == passed)\
            .group_by(PrivateMessage.public_key).order_by(PrivateMessage.created_at.desc())

    def get_message_thread(self, public_key):
        self.set_message_thread_read(public_key)
        filter_text = "profile.public_key = private_message.public_key AND private_message.public_key='{}'"
        return self.session.query(
            PrivateMessage.is_sender,
            PrivateMessage.content,
            PrivateMessage.created_at,
            PrivateMessage.public_key,
            Profile.name,
            Profile.display_name,
            Profile.pic).join(Profile) \
            .filter(text(filter_text.format(public_key))) \
            .order_by(PrivateMessage.created_at.desc()).limit(100).all()

    def set_message_thread_read(self, public_key):
        self.session.query(PrivateMessage).filter(PrivateMessage.public_key == public_key).update({'seen': True})
        self.session.commit()

    def set_all_messages_read(self):
        self.session.query(PrivateMessage).update({'seen': True})
        self.session.commit()

    def get_junk_count(self):
        return self.session.query(PrivateMessage).filter(PrivateMessage.passed == 0).count()

    def empty_junk(self):
        ids = []
        q = self.session.query(Event.id).join(PrivateMessage, PrivateMessage.id == Event.event_id).filter(PrivateMessage.passed == 0).all()
        for row in q:
            ids.append(row.id)
        q = self.session.query(EventRelay).filter(EventRelay.event_id.in_(ids)).delete()
        q = self.session.query(PrivateMessage).filter(PrivateMessage.passed == 0).delete()
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

    def add_note_reactions(self, reactions:list):
        chunked_lists = [reactions[i:i + 999] for i in range(0, len(reactions), 999)]

        for l in chunked_lists:
            stmt = sqlite_upsert(NoteReaction).values(l)
            stmt = stmt.on_conflict_do_update(
                index_elements=[NoteReaction.id],
                set_=dict(
                    public_key=stmt.excluded.public_key,
                    event_id=stmt.excluded.event_id,
                    event_pk=stmt.excluded.event_pk,
                    content=stmt.excluded.content,
                    members=stmt.excluded.members
                )
            )
            try:
                self.session.execute(stmt)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))

        #
        # a = []
        # for r in reactions:
        #     a.append(NoteReaction(
        #         id=r['id'],
        #         public_key=r['public_key'],
        #         event_id=r['event_id'],
        #         event_pk=r['event_pk'],
        #         content=r['content'],
        #         members=r['members']
        #     ))
        # self.session.bulk_save_objects(a)
        # self.session.commit()

    def delete_reaction(self, reaction_id):
        self.session.query(Event).filter_by(event_id=reaction_id).delete()
        self.session.query(NoteReaction).filter_by(id=reaction_id).delete()
        self.session.commit()

    def set_note_liked(self, note_id, liked=True):
        self.session.merge(Note(
            id=note_id,
            liked=liked
        ))
        self.session.commit()

    def get_note_reactions(self, note_id):
        stmt = (
            self.session.query(
                Profile.name,
                Profile.public_key.label('pk')
            )
            .subquery()
        )
        return self.session.query(
            NoteReaction.content,
            NoteReaction.public_key,
            stmt.c.name
        ).outerjoin(stmt, NoteReaction.public_key == stmt.c.pk)\
            .filter(NoteReaction.event_id == note_id).all()

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

    def add_event(self, event_id, public_key, kind, ts):
        self.session.merge(Event(
            event_id=event_id,
            public_key=public_key,
            kind=kind,
            ts=ts
        ))
        self.session.commit()

    def insert_events(self, events:list):
        chunked_lists = [events[i:i + 999] for i in range(0, len(events), 999)]

        for l in chunked_lists:
            stmt = sqlite_upsert(Event).values(l)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Event.event_id],
                set_=dict(
                    public_key=stmt.excluded.public_key,
                    kind=stmt.excluded.kind,
                    ts=stmt.excluded.ts
                )
            )
            try:
                self.session.execute(stmt)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))

    def insert_event_relay(self, events: list):
        chunked_lists = [events[i:i + 999] for i in range(0, len(events), 999)]

        for l in chunked_lists:
            e = []
            for event in l:
                dber = self.get_event_relay(event)
                if dber is None:
                    relay = self.get_relay_by_url(event['relay'])
                    dbe = self.get_event(event['event_id'])
                    if relay is not None and dbe is not None:
                        e.append({'event_id':dbe.id, 'relay':relay.id})
            stmt = sqlite_upsert(EventRelay).values(e)
            try:
                self.session.execute(stmt)
                self.session.commit()
            except SQLAlchemyError as e:
                print(str(e.__dict__['orig']))

    def get_event_relay(self, e):
        return self.session.query(EventRelay.id).filter(EventRelay.event_id == e['event_id']).filter(EventRelay.relay == e['relay']).first()

    def get_event(self, event_id):
        return self.session.query(Event.id, Event.event_id, Event.kind).filter(Event.event_id == event_id).first()

    def latest_event(self):
        return self.session.query(Event.ts).order_by(Event.ts.desc()).first()

    def add_alert(self, kind, ts, data):

        self.session.merge(Alert(
            kind=kind,
            ts=ts,
            data=data
        ))
        self.session.commit()

    def get_alerts(self):
        return self.session.query(Alert).order_by(Alert.seen.asc()).order_by(Alert.ts.desc()).limit(10).all()

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

    def get_settings_by_keys(self, keys: list):
        return self.session.query(Settings.key, Settings.value).filter(Settings.key.in_(keys)).all()

    def get_settings(self):
        out = {}
        settings = self.session.query(Settings.key, Settings.value).all()
        for item in settings:
            out[item.key] = item.value
        return out

    def upd_settings_by_keys(self, settings: dict):
        for setting in settings.items():
            self.session.merge(Settings(
                key=setting[0],
                value=setting[1],
            ))
        self.session.commit()

    def upd_setting(self, k, v):
        self.session.merge(Settings(
            key=k,
            value=v,
        ))
        self.session.commit()

    def add_default_themes(self, data):
        for theme, setting in data.items():
            for k, v in setting.items():
                self.session.add(Theme(
                    var=k,
                    val=v,
                    theme=theme
                ))
        self.session.commit()

    def get_themes(self):
        return self.session.query(Theme.theme).distinct()

    def get_theme_vars(self,  theme):
        return self.session.query(Theme.val, Theme.var).filter(Theme.theme==theme).all()

    def commit(self):
        self.session.commit()

    def get_feed(self, before, public_key, filters):

        sq_following = self.session.query(func.count(Follower.id).label('count'))\
            .filter(Follower.pk_1 == public_key)\
            .filter(Follower.pk_2 == Profile.public_key).scalar_subquery()

        sq_follower = self.session.query(func.count(Follower.id).label('count'))\
            .filter(Follower.pk_2 == public_key)\
            .filter(Follower.pk_1 == Profile.public_key).scalar_subquery()

        q = self.session.query(
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
            Profile.display_name,
            Profile.pic,
            Profile.nip05,
            Profile.nip05_validated,
            label('is_follower', sq_follower),
            label('following', sq_following)
        )
        q = q.join(Note.profile)
        q = q.outerjoin(ReactionTally, ReactionTally.event_id == Note.id)
        q = q.filter(text("note.created_at<{}".format(before)))
        q = q.filter(text("note.deleted is not 1"))
        if 'main_feed' in filters:
            q = q.filter(text("(following=1 OR profile.public_key='{}')".format(public_key)))
        if 'profile' in filters:
            q = q.filter(Profile.public_key==filters['profile'])
        if 'topic' in filters:
            q = q.filter(Note.hashtags.like(f"%\"{filters['topic']}\"%"))
        if 'boost_id' in filters:
            q = q.filter(Note.reshare==filters['boost_id'])
        if 'id_list' in filters:
            q = q.filter(Note.id.in_(filters['id_list']))
        if 'search' in filters:
            q = q.filter(Note.content.like(f"%{filters['search']}%"))
        if 'pubkeys' in filters:
            q = q.filter(Profile.public_key.in_(filters['pubkeys']))
        if 'replies' in filters:
            q = q.filter(
                or_(
                    Note.response_to==filters['replies'],
                    Note.thread_root==filters['replies']
                )
            )
        q = q.order_by(Note.seen.asc(), Note.created_at.desc()).limit(50)
        return q.all()

    def get_url(self, url):
        return self.session.query(URL).filter(URL.address == url).first()

    def insert_url(self, address, ts, og):
        self.session.merge(URL(
            address=address,
            ts=ts,
            og=og
        ))
        self.session.commit()