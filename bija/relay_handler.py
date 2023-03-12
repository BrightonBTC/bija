import math
import ssl

from flask import render_template

from bija.app import socketio, ACTIVE_EVENTS
from bija.deferred_tasks import TaskKind, DeferredTasks
from bija.events import BlockListEvent, BoostEvent, NoteEvent, ContactListEvent, FollowerListEvent, DirectMessageEvent, \
    MetadataEvent, ReactionEvent, DeleteEvent, PersonListEvent, BookmarkListEvent
from bija.helpers import is_json
from bija.nip5 import Nip5
from bija.ogtags import OGTags
from bija.subscriptions import *
from bija.submissions import *
from bija.alerts import *
from bija.settings import SETTINGS
from bija.ws.event import EventKind
from bija.ws.subscription_manager import SUBSCRIPTION_MANAGER

logger = logging.getLogger(__name__)
FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(format=FORMAT)
logger.setLevel(LOGGING_LEVEL)

D_TASKS = DeferredTasks()
DB = BijaDB(app.session)


class RelayHandler:
    pool_handler_running = False
    page = {
        'page': None,
        'identifier': None
    }
    processing = False
    new_on_primary = False
    notify_empty_queue = False

    contacts_batch = {
        'inserts': {},
        'objects': []
    }

    followers_batch = []

    reaction_batch = {
        'inserts': [],
        'objects': [],
        'ids': []
    }

    profile_batch = {
        'inserts': [],
        'objects': []
    }

    missing_profiles_batch = []

    blocked_profiles_batch = []

    note_batch = {
        'inserts': [],
        'objects': []
    }

    dm_batch = {
        'inserts': [],
        'objects': []
    }

    event_batch = []
    event_seen_on_batch = []

    unique_events = set()

    def __init__(self):
        self.should_run = True
        self.open_connections()

    def open_connections(self):
        relays = DB.get_relays()
        for r in relays:
            RELAY_MANAGER.add_relay(r.name, r.send, r.receive)
        if len(relays) > 0:
            RELAY_MANAGER.open_connections({"cert_reqs": ssl.CERT_NONE})

    # close existing connections, reopen, and start primary subscription
    # used after adding or removing relays
    def reset(self):
        RELAY_MANAGER.close_connections()
        time.sleep(1)
        RELAY_MANAGER.relays = {}
        time.sleep(1)
        self.open_connections()
        time.sleep(1)
        self.subscribe_primary()
        time.sleep(1)
        self.get_connection_status()

    def remove_relay(self, url):
        RELAY_MANAGER.remove_relay(url)

    def add_relay(self, url):
        RELAY_MANAGER.add_relay(url)

    def get_connection_status(self):
        status = RELAY_MANAGER.get_connection_status()
        out = []
        for s in status:
            if s[1] is not None:
                out.append([s[0], int(time.time() - s[1])])
            else:
                out.append([s[0], None])

        socketio.emit('conn_status', out)

    def set_page(self, page, identifier):
        self.page = {
            'page': page,
            'identifier': identifier
        }

    def check_messages(self):
        if self.processing:
            logger.log('Already processing messages. Wait')
            return
        self.processing = True
        while RELAY_MANAGER.message_pool.has_notices():
            notice = RELAY_MANAGER.message_pool.get_notice()
            print('NOTICE', notice.url, notice.content)

        while RELAY_MANAGER.message_pool.has_ok_notices():
            notice = RELAY_MANAGER.message_pool.get_ok_notice()
            print('OK', notice.url, notice.content)

        while RELAY_MANAGER.message_pool.has_eose_notices():
            notice = RELAY_MANAGER.message_pool.get_eose_notice()
            if hasattr(notice, 'url') and hasattr(notice, 'subscription_id'):
                print('EOSE', notice.url, notice.subscription_id)
                SUBSCRIPTION_MANAGER.next_batch(notice.url, notice.subscription_id)

        n_queued = RELAY_MANAGER.message_pool.events.qsize()
        if n_queued > 0 or self.notify_empty_queue:
            self.notify_empty_queue = True
            socketio.emit('events_processing', n_queued)
            if n_queued == 0:
                self.notify_empty_queue = False

        i = 0
        self.unique_events = set()
        blocklist = DB.get_blocked_pks()

        while RELAY_MANAGER.message_pool.has_events() and i < 500:
            msg = RELAY_MANAGER.message_pool.get_event()
            # ignore events from subscriptions we moved away from unless it's a follower list which needs to be processed
            # as it will cause loos of data if skipped
            if msg.subscription_id in SUBSCRIPTION_MANAGER.subscriptions or 'followers:' in msg.subscription_id:
                i += 1
                if msg.event.public_key not in blocklist:
                    if msg.event.id not in self.unique_events and DB.get_event(msg.event.id) is None:
                        logger.info('New event: {}'.format(msg.event.kind))
                        if msg.event.kind == EventKind.SET_METADATA:
                            self.receive_metadata_event(msg.event)

                        elif msg.event.kind == EventKind.CONTACTS:
                            self.receive_contact_list_event(msg.event, msg.subscription_id)

                        elif msg.event.kind == EventKind.TEXT_NOTE:
                            self.receive_note_event(msg.event, msg.subscription_id)

                        elif msg.event.kind == EventKind.BOOST:
                            self.receive_boost_event(msg.event)

                        elif msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                            self.receive_direct_message_event(msg.event)

                        elif msg.event.kind == EventKind.DELETE:
                            DeleteEvent(msg.event)

                        elif msg.event.kind == EventKind.REACTION:
                            self.receive_reaction_event(msg.event)

                        elif msg.event.kind == EventKind.BLOCK_LIST:
                            self.receive_block_list(msg.event)

                        elif msg.event.kind in [EventKind.RELAY_LIST, EventKind.BADGE_AWARD, EventKind.BADGE_DEF, EventKind.BADGES]:
                            print(msg.event.kind)

                        elif msg.event.kind == EventKind.PERSON_LIST:
                            self.receive_person_list(msg.event)

                        elif msg.event.kind == EventKind.BOOKMARK_LIST:
                            self.receive_bookmark_list(msg.event)

                        if 'followers:' not in msg.subscription_id:
                            self.event_batch.append({
                                'event_id': msg.event.id,
                                'public_key': msg.event.public_key,
                                'kind': int(msg.event.kind),
                                'ts': int(msg.event.created_at)
                            })

                    if msg.event.kind in [EventKind.TEXT_NOTE, EventKind.ENCRYPTED_DIRECT_MESSAGE]:
                        self.unique_events.add(msg.event.id)
                        self.event_seen_on_batch.append({
                            'event_id': msg.event.id,
                            'relay': msg.url
                        })

        self.do_batched_inserts()

        self.new_events_notify()

        self.handle_tasks()

        t = int(time.time())
        logger.info('Event loop {}'.format(t))
        if t % 60 == 0:
            self.get_connection_status()
            logger.info('Check for subscriptions that need refreshing')
            SUBSCRIPTION_MANAGER.next_round()
        self.processing = False

    def run_loop(self):
        while self.should_run:
            self.check_messages()
            time.sleep(1)

    def do_batched_inserts(self):
        n = len(self.profile_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched profiles'.format(n))
            self.process_profiles()

        n = len(self.missing_profiles_batch)
        if n > 0:
            logger.info('Insert {} batched missing profiles'.format(n))
            DB.add_profiles_if_not_exists(self.missing_profiles_batch)
            self.missing_profiles_batch.clear()

        n = len(self.blocked_profiles_batch)
        if n > 0:
            logger.info('Update blocked profiles')
            DB.update_block_list(self.blocked_profiles_batch)
            self.blocked_profiles_batch.clear()

        n = len(self.note_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched notes'.format(n))
            self.process_notes()

        n = len(self.contacts_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched contact lists'.format(n))
            self.process_contacts()

        n = len(self.followers_batch)
        if n > 0:
            logger.info('Insert {} batched followers'.format(n))
            DB.update_followers_list(SETTINGS.get('pubkey'), self.followers_batch)
            self.followers_batch.clear()

        n = len(self.reaction_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched reactions'.format(n))
            self.process_reactions()

        n = len(self.dm_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched direct messages'.format(n))
            self.process_direct_messages()

        n = len(self.event_batch)
        if n > 0:
            logger.info('Insert {} batched events'.format(n))
            DB.insert_events(self.event_batch)
            self.event_batch.clear()

        n = len(self.event_seen_on_batch)
        if n > 0:
            logger.info('Insert {} batched seen on events'.format(n))
            DB.insert_event_relay(self.event_seen_on_batch)
            self.event_seen_on_batch.clear()

    @staticmethod
    def handle_tasks():
        while not RELAY_MANAGER.message_pool.has_events() and D_TASKS.pool.has_tasks():
            t = D_TASKS.next()
            if t is not None:
                if t.kind == TaskKind.FETCH_OG:
                    OGTags(t.data)
                elif t.kind == TaskKind.VALIDATE_NIP5:
                    logger.info('Validate Nip05 {}'.format(t.data['pk']))
                    profile = DB.get_profile(t.data['pk'])
                    if profile is not None:
                        valid = False
                        if profile.nip05 is not None:
                            nip5 = Nip5(profile.nip05)
                            valid = nip5.match(profile.public_key)
                        DB.set_valid_nip05(profile.public_key, valid)
                        logger.info('Validated? {}'.format(valid))

    def new_events_notify(self):
        if self.new_on_primary:
            self.new_on_primary = False
            unseen_posts = DB.get_unseen_in_feed(SETTINGS.get('pubkey'))
            if unseen_posts > 0:
                socketio.emit('unseen_posts_n', unseen_posts)
            topics = DB.get_topics()
            if topics is not None:
                t = [x.tag for x in topics]
                unseen_in_topics = DB.get_unseen_in_topics(t)
                if unseen_in_topics is not None:
                    socketio.emit('unseen_in_topics', unseen_in_topics)

    def add_profile_if_not_exists(self, pk):
        if is_hex_key(pk):
            self.missing_profiles_batch.append(pk)

    def add_to_contacts_batch(self, e):
        insert = True
        if e.event.public_key in self.contacts_batch['inserts']:
            if e.event.created_at < self.contacts_batch['inserts'][e.event.public_key]['ts']:
                insert = False
        if insert:
            self.contacts_batch['inserts'][e.event.public_key] = {'ts': e.event.created_at, 'pks': e.keys}
            self.contacts_batch['objects'].append(e)

    def receive_block_list(self, event):
        e = BlockListEvent(event)
        for item in e.list:
            if len(item) > 1 and item[0] == 'p' and is_hex_key(item[1]):
                self.add_profile_if_not_exists(item[1])
                self.blocked_profiles_batch.append(item[1])

    def receive_person_list(self, event):
        e = PersonListEvent(event)

    def receive_bookmark_list(self, event):
        e = BookmarkListEvent(event)

    def receive_reaction_event(self, event):
        e = ReactionEvent(event, SETTINGS.get('pubkey'))
        if e.valid and e.event.id not in self.reaction_batch['ids']:
            self.add_profile_if_not_exists(e.event_pk)
            self.add_profile_if_not_exists(e.event.public_key)
            self.reaction_batch['inserts'].append(e.to_dict())
            self.reaction_batch['objects'].append(e)
            self.reaction_batch['ids'].append(e.event.id)

    def process_reactions(self):
        DB.add_note_reactions(self.reaction_batch['inserts'])
        self.reaction_batch['inserts'].clear()
        self.signal_on_reactions()
        logger.info('update {} notes referenced in reaction'.format(len(self.reaction_batch['objects'])))
        for e in self.reaction_batch['objects']:
            if e.event.content != "-":
                DB.increment_note_like_count(e.event_id)
        self.reaction_batch['ids'].clear()
        self.reaction_batch['objects'].clear()

    def signal_on_reactions(self):
        has_alerts = False
        ids = []
        for o in self.reaction_batch['objects']:
            ids.append(o.event_id)

        notes = DB.get_notes_by_id_list(ids)
        for e in self.reaction_batch['objects']:
            note = next((sub for sub in notes if sub.id == e.event_id), None)
            if note is not None:
                if e.event.content != '-' and len(ACTIVE_EVENTS.notes) > 0 and e.event_id in ACTIVE_EVENTS.notes:
                    socketio.emit('new_reaction', e.event_id)
                    logger.info('Reaction on active note detected, signal to UI')
                if e.event.public_key != SETTINGS.get('pubkey'):
                    if note is not None and note.public_key == SETTINGS.get('pubkey'):
                        has_alerts = True
                        logger.info('Get reaction from DB')
                        reaction = DB.get_reaction_by_id(e.event.id)
                        logger.info('Compose reaction alert')
                        Alert(AlertKind.REACTION, e.event.created_at, {
                            'public_key': e.event.public_key,
                            'referenced_event': e.event_id,
                            'reaction': reaction.content
                        })
        if has_alerts:
            logger.info('Get unread alert count')
            n = DB.get_unread_alert_count()
            if n > 0:
                socketio.emit('alert_n', n)

    def receive_metadata_event(self, event):
        meta = MetadataEvent(event)
        if meta.success:
            self.profile_batch['inserts'].append(meta.to_dict())
            self.profile_batch['objects'].append(meta)
            D_TASKS.pool.add(TaskKind.VALIDATE_NIP5, {'pk': meta.event.public_key})

    def process_profiles(self):
        DB.update_profiles(self.profile_batch['inserts'])
        self.profile_batch['inserts'].clear()
        for e in self.profile_batch['objects']:
            self.signal_on_profile_update(e)
        self.profile_batch['objects'].clear()

    def signal_on_profile_update(self, meta):
        if self.page['page'] == 'profile' and self.page['identifier'] == meta.event.public_key:
            if meta.picture is None or len(meta.picture.strip()) == 0:
                meta.picture = '/identicon?id={}'.format(meta.event.public_key)
            socketio.emit('profile_update', {
                'public_key': meta.event.public_key,
                'name': meta.name,
                'nip05': meta.nip05,
                'pic': meta.picture,
                'about': meta.about,
                'created_at': meta.event.created_at
            })

    def receive_boost_event(self, event):
        e = BoostEvent(event)
        if e.reshare_id is not None:
            res = next((sub for sub in self.note_batch['inserts'] if sub['id'] == e.event.id), None)
            if res is None:
                if is_json(e.note_content):
                    j = json.loads(e.note_content)
                    keys = ('id', 'pubkey', 'content', 'created_at', 'kind', 'tags', 'sig')
                    if set(keys).issubset(j):
                        n = DB.get_note(SETTINGS.get('pubkey'), j['id'])
                        if n is None:
                            parent_event = Event(j['pubkey'], j['content'], j['created_at'], j['kind'], j['tags'], j['id'],
                                                 j['sig'])
                            if parent_event.verify():
                                self.receive_note_event(parent_event, 'boost')
                self.add_profile_if_not_exists(e.event.public_key)
                self.note_batch['inserts'].append(e.to_dict())
                DB.increment_note_share_count(e.reshare_id)

    def receive_note_event(self, event, subscription):
        if subscription == 'boost':
            logger.info('NOTE FROM BOOST CONTENT')
        e = NoteEvent(event, SETTINGS.get('pubkey'), subscription)
        res = next((sub for sub in self.note_batch['inserts'] if sub['id'] == e.event.id), None)
        if res is None:
            self.add_profile_if_not_exists(e.event.public_key)
            self.note_batch['inserts'].append(e.to_dict())
            self.note_batch['objects'].append({'obj': e, 'sub': subscription})
        if e.fetch_og is not None:
            D_TASKS.pool.add(TaskKind.FETCH_OG, {'url': e.fetch_og, 'note_id': e.event.id})

    def process_notes(self):
        DB.insert_notes(self.note_batch['inserts'])
        self.note_batch['inserts'].clear()
        for e in self.note_batch['objects']:
            self.signal_on_note_inserted(e)
            self.update_referenced_in_note(e['obj'])
        self.note_batch['objects'].clear()

    def update_referenced_in_note(self, e):
        logger.info('update refs new note')
        # is this a reply to another note?
        if e.response_to is not None:
            DB.increment_note_reply_count(e.response_to)
        elif e.thread_root is not None:
            DB.increment_note_reply_count(e.thread_root)
        # is this a re-share of another note?
        elif e.reshare is not None:
            DB.increment_note_share_count(e.reshare)

    def signal_on_note_inserted(self, o):
        e = o['obj']
        subscription = o['sub']
        if e.mentions_me:
            self.alert_on_note_event(e)
        if subscription == 'primary':
            self.new_on_primary = True
        elif subscription == 'note-thread':
            socketio.emit('new_in_thread', e.event.id)
        elif subscription == 'topic':
            socketio.emit('new_in_topic', True)
        if self.page['page'] == 'profile' and self.page['identifier'] == e.event.public_key:
            socketio.emit('new_profile_posts', DB.get_most_recent_for_pk(e.event.public_key))

        if len(ACTIVE_EVENTS.notes) > 0:
            if e.event.id in ACTIVE_EVENTS.notes:
                logger.info('New required note {}'.format(e.event.id))
                socketio.emit('new_note', e.event.id)
            if e.response_to in ACTIVE_EVENTS.notes:
                logger.info('Detected response to active note {}'.format(e.response_to))
                socketio.emit('new_reply', e.response_to)
            elif e.response_to is None and e.thread_root in ACTIVE_EVENTS.notes:
                logger.info('Detected response to active note {}'.format(e.thread_root))
                socketio.emit('new_reply', e.thread_root)
            if e.reshare in ACTIVE_EVENTS.notes:
                logger.info('Detected reshare on active note {}'.format(e.reshare))
                socketio.emit('new_reshare', e.reshare)

    def alert_on_note_event(self, event):
        if event.response_to is not None:
            reply = DB.get_note(SETTINGS.get('pubkey'), event.response_to)
            if reply is not None and reply.public_key == SETTINGS.get('pubkey'):
                Alert(AlertKind.REPLY, event.event.created_at, {
                    'public_key': event.event.public_key,
                    'event': event.event.id,
                    'content': event.content
                })
        elif event.thread_root is not None:
            root = DB.get_note(SETTINGS.get('pubkey'), event.thread_root)
            if root is not None and root.public_key == SETTINGS.get('pubkey'):
                Alert(AlertKind.COMMENT_ON_THREAD, event.event.created_at, {
                    'public_key': event.event.public_key,
                    'event': event.event.id,
                    'content': event.content
                })

    def receive_contact_list_event(self, event, subscription):
        logger.info('Contact list received for: {}'.format(event.public_key))
        last_upd = DB.get_last_contacts_upd(event.public_key)
        logger.info('Contact list last update: {}'.format(last_upd))
        if last_upd is None or last_upd < event.created_at:
            logger.info('Contact list is newer than last upd: {}'.format(event.created_at))
            pk = SETTINGS.get('pubkey')
            if 'followers' in subscription:
                e = FollowerListEvent(event, subscription)
                if e.target_pk is not None:
                    self.followers_batch.append({
                        'pk_1': e.event.public_key,
                        'pk_2': e.target_pk,
                        'action': e.action
                    })
            else:
                e = ContactListEvent(event)
                self.add_to_contacts_batch(e)
            self.add_profile_if_not_exists(event.public_key)

    def process_contacts(self):
        follows, unfollows, is_mine = DB.add_contact_lists(SETTINGS.get('pubkey'), self.contacts_batch['inserts'])
        self.contacts_batch['inserts'].clear()
        if is_mine:
            logger.info('Contact list updated, restart primary subscription')
            self.subscribe_primary()
        for pk in follows:
            Alert(AlertKind.FOLLOW, int(time.time()), {
                'public_key': pk
            })
        for pk in unfollows:
            Alert(AlertKind.UNFOLLOW, int(time.time()), {
                'public_key': pk
            })

    def receive_direct_message_event(self, event):
        e = DirectMessageEvent(event, SETTINGS.get('pubkey'))
        if e.pubkey is not None and e.is_sender is not None:
            self.dm_batch['inserts'].append(e.to_dict())
            self.dm_batch['objects'].append(e)
            self.add_profile_if_not_exists(e.event.public_key)

    def process_direct_messages(self):
        DB.insert_direct_messages(self.dm_batch['inserts'])
        self.dm_batch['inserts'].clear()
        for e in self.dm_batch['objects']:
            self.signal_on_direct_message(e)
        self.dm_batch['objects'].clear()

    def signal_on_direct_message(self, e):
        if self.page['page'] == 'message' and self.page['identifier'] == e.pubkey:
            messages = DB.get_unseen_messages(e.pubkey)
            if len(messages) > 0:
                profile = DB.get_profile(SETTINGS.get('pubkey'))
                DB.set_message_thread_read(e.pubkey)
                out = render_template("messages/message_thread.items.html",
                                      me=profile, messages=messages, privkey=SETTINGS.get('privkey'))
                socketio.emit('message', out)
        elif self.page['page'] == 'messages':
            socketio.emit('new_message', e.event.id)
            unseen_n = DB.get_unseen_message_count()
            socketio.emit('unseen_messages_n', unseen_n)
        else:
            unseen_n = DB.get_unseen_message_count()
            socketio.emit('unseen_messages_n', unseen_n)

    def subscribe_thread(self, root_id, ids):
        ACTIVE_EVENTS.add_notes(ids)
        n_following = DB.get_following(SETTINGS.get('pubkey'), SETTINGS.get('pubkey'), count=True)
        n_batches = math.ceil(n_following / 256)
        SUBSCRIPTION_MANAGER.add_subscription('note-thread', n_batches, root=root_id)

    def subscribe_feed(self, ids):
        ACTIVE_EVENTS.add_notes(ids)
        SUBSCRIPTION_MANAGER.add_subscription('main-feed', 1, ids=ids)

    def subscribe_profile(self, pubkey, since, ids):
        ACTIVE_EVENTS.add_notes(ids)
        n_following = DB.get_following(SETTINGS.get('pubkey'), pubkey, count=True)
        n_batches = math.ceil(n_following / 256)
        p = DB.get_profile(pubkey)
        SUBSCRIPTION_MANAGER.add_subscription('profile:{}'.format(p.id), n_batches, pubkey=pubkey, since=since, ids=ids)
        n_following = DB.get_followers(SETTINGS.get('pubkey'), pubkey, count=True)
        n_batches = math.ceil(n_following / 256)
        followers_last_upd = DB.get_followers_last_upd(pubkey)
        DB.set_followers_last_upd(pubkey)
        SUBSCRIPTION_MANAGER.add_subscription('followers:{}'.format(p.id), n_batches, pubkey=pubkey, since=followers_last_upd)

    # create site wide subscription
    def subscribe_primary(self):
        n_following = DB.get_following(SETTINGS.get('pubkey'), SETTINGS.get('pubkey'), count=True)
        n_batches = math.ceil(n_following / 256)
        SUBSCRIPTION_MANAGER.add_subscription('primary', n_batches, pubkey=SETTINGS.get('pubkey'))

    def subscribe_topic(self, term):
        logger.info('Subscribe topic {}'.format(term))
        SUBSCRIPTION_MANAGER.add_subscription('topic', 1, term=term)

    def subscribe_messages(self, since):
        logger.info('Subscribe messages since {}'.format(since))
        SUBSCRIPTION_MANAGER.add_subscription('messages', 1, pubkey=SETTINGS.get('pubkey'), since=since)

    def close(self):
        self.should_run = False
        RELAY_MANAGER.close_connections()


