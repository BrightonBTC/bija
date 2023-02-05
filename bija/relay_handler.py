import ssl

import validators as validators
from flask import render_template

from bija.app import socketio, ACTIVE_EVENTS
from bija.deferred_tasks import TaskKind, DeferredTasks
from bija.helpers import get_embeded_tag_indexes, \
    list_index_exists, get_urls_in_string, url_linkify, strip_tags, is_nip05, \
    request_url_head, is_json
from bija.nip5 import Nip5
from bija.ogtags import OGTags
from bija.subscriptions import *
from bija.submissions import *
from bija.alerts import *
from bija.settings import SETTINGS
from bija.ws.event import EventKind
from bija.ws.pow import count_leading_zero_bits
from bija.subscription_manager import SUBSCRIPTION_MANAGER

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

    note_batch = {
        'inserts': [],
        'objects': []
    }

    dm_batch = {
        'inserts': [],
        'objects': []
    }

    event_batch = []

    def __init__(self):
        self.should_run = True
        self.open_connections()

    def open_connections(self):
        relays = DB.get_relays()
        n_relays = 0
        for r in relays:
            n_relays += 1
            RELAY_MANAGER.add_relay(r.name)
        if n_relays > 0:
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
                if notice.subscription_id == 'note-thread':
                    print('------------------ next thread batch')
                    SUBSCRIPTION_MANAGER.next_batch(notice.url, notice.subscription_id)

        n_queued = RELAY_MANAGER.message_pool.events.qsize()
        if n_queued > 0 or self.notify_empty_queue:
            self.notify_empty_queue = True
            socketio.emit('events_processing', n_queued)
            if n_queued == 0:
                self.notify_empty_queue = False

        i = 0
        while RELAY_MANAGER.message_pool.has_events() and i < 500:
            i += 1
            msg = RELAY_MANAGER.message_pool.get_event()
            if DB.get_event(msg.event.id) is None:
                logger.info('New event: {}'.format(msg.event.kind))
                if msg.event.kind == EventKind.SET_METADATA:
                    self.receive_metadata_event(msg.event)

                if msg.event.kind == EventKind.CONTACTS:
                    self.receive_contact_list_event(msg.event)

                if msg.event.kind == EventKind.TEXT_NOTE:
                    self.receive_note_event(msg.event, msg.subscription_id)

                if msg.event.kind == EventKind.BOOST:
                    self.receive_boost_event(msg.event)

                if msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                    self.receive_direct_message_event(msg.event)

                if msg.event.kind == EventKind.DELETE:
                    self.receive_del_event(msg.event)

                if msg.event.kind == EventKind.REACTION:
                    self.receive_reaction_event(msg.event)

                self.event_batch.append({
                    'event_id':msg.event.id,
                    'public_key':msg.event.public_key,
                    'kind':int(msg.event.kind),
                    'ts':int(msg.event.created_at)
                })
        DB.commit()

        n = len(self.contacts_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched contact lists'.format(n))
            self.process_contacts()

        n = len(self.event_batch)
        if n > 0:
            logger.info('Insert {} batched events'.format(n))
            DB.insert_events(self.event_batch)
            self.event_batch.clear()

        n = len(self.profile_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched profiles'.format(n))
            self.process_profiles()

        n = len(self.missing_profiles_batch)
        if n > 0:
            logger.info('Insert {} batched missing profiles'.format(n))
            DB.add_profiles_if_not_exists(self.missing_profiles_batch)
            self.missing_profiles_batch.clear()

        n = len(self.note_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched notes'.format(n))
            self.process_notes()

        n = len(self.reaction_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched reactions'.format(n))
            self.process_reactions()

        n = len(self.dm_batch['inserts'])
        if n > 0:
            logger.info('Insert {} batched direct messages'.format(n))
            self.process_direct_messages()


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

        if RELAY_MANAGER.message_pool.events.qsize() == 0:
            self.handle_tasks()

        t = int(time.time())
        logger.info('Event loop {}'.format(t))
        if t % 60 == 0:
            self.get_connection_status()
            i = 0
        self.processing = False

    def run_loop(self):
        while self.should_run:
            self.check_messages()
            time.sleep(1)

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

    def receive_del_event(self, event):
        DeleteEvent(event)

    def add_profile_if_not_exists(self, pk):
        if is_hex_key(pk):
            self.missing_profiles_batch.append(pk)

    def add_to_contacts_batch(self, e):
        insert = True
        if e.event.public_key in self.contacts_batch['inserts']:
            if e.event.created_at < self.contacts_batch['inserts'][e.event.public_key]['ts']:
                insert = False
        if insert:
            self.contacts_batch['inserts'][e.event.public_key] = {'ts':e.event.created_at, 'pks': e.keys}
            self.contacts_batch['objects'].append(e)

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
        for e in self.reaction_batch['objects']:
            #self.signal_on_reaction(e)
            self.increment_reaction_counts(e)
        self.reaction_batch['ids'].clear()
        self.reaction_batch['objects'].clear()

    def increment_reaction_counts(self, e):
        logger.info('update referenced in reaction')
        if e.event.content != "-":
            DB.increment_note_like_count(e.event_id)

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
                        has_alerts =True
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
                    parent_event = Event(j['pubkey'], j['content'], j['created_at'], j['kind'], j['tags'], j['id'], j['sig'])
                    if parent_event.verify():
                        self.receive_note_event(parent_event, 'bija')
                self.add_profile_if_not_exists(e.event.public_key)
                self.note_batch['inserts'].append(e.to_dict())
                DB.increment_note_share_count(e.reshare_id)

    def receive_note_event(self, event, subscription):
        if subscription == 'bija':
            print('NOTE FROM BOOST CONTENT', event.id)
        e = NoteEvent(event, SETTINGS.get('pubkey'))
        print(e)
        res = next((sub for sub in self.note_batch['inserts'] if sub['id'] == e.event.id), None)
        if res is None:
            self.add_profile_if_not_exists(e.event.public_key)
            self.note_batch['inserts'].append(e.to_dict())
            self.note_batch['objects'].append({'obj':e, 'sub':subscription})

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
        self.notify_on_note_event(e.event, subscription)

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

    def notify_on_note_event(self, event, subscription):
        if subscription == 'primary':
            self.new_on_primary = True
        if self.page['page'] == 'profile' and self.page['identifier'] == event.public_key:
            DB.set_note_seen(event.id)
            socketio.emit('new_profile_posts', DB.get_most_recent_for_pk(event.public_key))
        elif subscription == 'note-thread':
            socketio.emit('new_in_thread', event.id)
        elif subscription == 'topic':
            socketio.emit('new_in_topic', True)

    def receive_contact_list_event(self, event):
        logger.info('Contact list received for: {}'.format(event.public_key))
        last_upd = DB.get_last_contacts_upd(event.public_key)
        logger.info('Contact list last update: {}'.format(last_upd))
        if last_upd is None or last_upd < event.created_at:
            logger.info('Contact list is newer than last upd: {}'.format(event.created_at))
            # D_TASKS.pool.add(TaskKind.CONTACT_LIST, event)
            pk = SETTINGS.get('pubkey')
            e = ContactListEvent(event, pk)
            self.add_to_contacts_batch(e)
            self.add_profile_if_not_exists(e.event.public_key)

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
        if e.pubkey is not None and e.is_sender is not None and e.passed:
            self.dm_batch['inserts'].append(e.to_dict())
            self.dm_batch['objects'].append(e)
            self.add_profile_if_not_exists(e.event.public_key)
            
    def process_direct_messages(self):
        DB.insert_direct_messages(self.dm_batch['inserts'])
        self.dm_batch['inserts'].clear()
        for e in self.note_batch['objects']:
            self.signal_on_direct_message(e)
        self.dm_batch['objects'].clear()

    def signal_on_direct_message(self, e):
        if self.page['page'] == 'message' and self.page['identifier'] == e.pubkey:
            messages = DB.get_unseen_messages(e.pubkey)
            if len(messages) > 0:
                profile = DB.get_profile(SETTINGS.get('pubkey'))
                DB.set_message_thread_read(e.pubkey)
                out = render_template("message_thread.items.html",
                                      me=profile, messages=messages, privkey=SETTINGS.get('privkey'))
                socketio.emit('message', out)
        else:
            unseen_n = DB.get_unseen_message_count()
            socketio.emit('unseen_messages_n', unseen_n)

    def subscribe_thread(self, root_id, ids):
        ACTIVE_EVENTS.add_notes(ids)
        subscription_id = 'note-thread'
        SUBSCRIPTION_MANAGER.add_subscription(subscription_id, 2, root=root_id)

    def subscribe_feed(self, ids):
        ACTIVE_EVENTS.add_notes(ids)
        subscription_id = 'main-feed'
        SUBSCRIPTION_MANAGER.add_subscription(subscription_id, 1, ids=ids)

    def subscribe_profile(self, pubkey, since, ids):
        ACTIVE_EVENTS.add_notes(ids)
        subscription_id = 'profile'
        SUBSCRIPTION_MANAGER.add_subscription(subscription_id, 1, pubkey=pubkey, since=since, ids=ids)

    # create site wide subscription
    def subscribe_primary(self):
        SUBSCRIPTION_MANAGER.add_subscription('primary', 1, pubkey=SETTINGS.get('pubkey'))

    def subscribe_topic(self, term):
        logger.info('Subscribe topic {}'.format(term))
        SUBSCRIPTION_MANAGER.add_subscription('topic', 1, term=term)

    def close_subscription(self, name):
        SUBSCRIPTION_MANAGER.remove_subscription(name)

    def close_secondary_subscriptions(self):
        SUBSCRIPTION_MANAGER.clear_subscriptions()

    def close(self):
        self.should_run = False
        RELAY_MANAGER.close_connections()


class ReactionEvent:
    def __init__(self, event, my_pubkey):
        logger.info('REACTION EVENT {}'.format(event.id))
        self.event = event
        self.pubkey = my_pubkey
        self.event_id = None
        self.event_pk = None
        self.event_members = []
        self.valid = False
        self.process()
        logger.info('REACTION processed')

    def process(self):
        logger.info('process reaction')
        self.process_tags()
        if self.event_id is not None and self.event_pk is not None:
            self.valid = True
            self.store()
        else:
            logger.debug('Invalid reaction event could not be stored.')

    def process_tags(self):
        logger.info('process reaction tags')
        for tag in self.event.tags:
            if tag[0] == "p" and is_hex_key(tag[1]):
                self.event_pk = tag[1]
                self.event_members.append(tag[1])
            if tag[0] == "e" and is_hex_key(tag[1]):
                self.event_id = tag[1]

    def to_dict(self) -> dict:
        return {
            "id": self.event.id,
            "public_key": self.event.public_key,
            "event_id": self.event_id,
            "event_pk": self.event_pk,
            "content": strip_tags(self.event.content),
            "members": json.dumps(self.event_members)
        }

    def store(self):
        logger.info('store reaction')
        if self.event.public_key == self.pubkey:
            DB.set_note_liked(self.event_id)


class DeleteEvent:
    def __init__(self, event):
        self.event = event
        self.process()

    def process(self):
        for tag in self.event.tags:
            if tag[0] == 'e':
                e = DB.get_event(tag[1])
                if e is not None and e.kind == EventKind.REACTION:
                    DB.delete_reaction(tag[1])
                if e is not None and e.kind == EventKind.TEXT_NOTE:
                    DB.set_note_deleted(tag[1], self.event.content)


class ContactListEvent:
    def __init__(self, event, pubkey):
        self.event = event
        self.pubkey = pubkey
        self.keys = []

        self.compile_keys()

    def compile_keys(self):
        for p in self.event.tags:
            if p[0] == "p":
                self.keys.append(p[1])


class DirectMessageEvent:
    def __init__(self, event, my_pubkey):
        self.my_pubkey = my_pubkey
        self.event = event
        self.is_sender = None
        self.pubkey = None
        self.passed = False

        self.process_data()

    def check_pow(self):
        if self.is_sender == 1:
            f = DB.a_follows_b(SETTINGS.get('pubkey'), self.pubkey)
            if f:
                self.passed = True
            else:
                req_pow = SETTINGS.get('pow_required_enc')
                actual_pow = count_leading_zero_bits(self.event.id)
                logger.info('required proof of work: {} {}'.format(type(req_pow), req_pow))
                logger.info('actual proof of work: {} {}'.format(type(actual_pow), actual_pow))
                if req_pow is None or actual_pow >= int(req_pow):
                    logger.info('passed')
                    self.passed = True
                else:
                    logger.info('failed')
        else:
            self.passed = True

    def process_data(self):
        self.set_receiver_sender()
        self.check_pow()

    def set_receiver_sender(self):
        to = None
        for p in self.event.tags:
            if p[0] == "p":
                to = p[1]
        if to is not None and [getattr(self.event, attr) for attr in ['id', 'public_key', 'content', 'created_at']]:
            if to == self.my_pubkey:
                self.pubkey = self.event.public_key
                self.is_sender = 1
            elif self.event.public_key == self.my_pubkey:
                self.pubkey = to
                self.is_sender = 0

    def to_dict(self) -> dict:
        seen = False
        if self.is_sender == 1 and self.pubkey == self.my_pubkey:  # sent to self
            seen = True
        return {
            "id": self.event.id,
            "public_key": self.pubkey,
            "content": strip_tags(self.event.content),
            "is_sender": self.is_sender,
            "created_at": self.event.created_at,
            "seen": seen,
            "raw": json.dumps(self.event.to_json_object())
        }


class MetadataEvent:
    def __init__(self, event):
        self.event = event
        self.name = None
        self.display_name = None
        self.nip05 = None
        self.about = None
        self.picture = None
        self.success = True
        if self.is_fresh():
            self.process_content()

    def is_fresh(self):
        ts = DB.get_profile_last_upd(self.event.public_key)
        if ts is None or ts.updated_at < self.event.created_at:
            return True
        self.success = False
        return False

    def process_content(self):
        try:
            s = json.loads(self.event.content)
        except ValueError as e:
            self.success = False
            return
        if 'name' in s and s['name'] is not None:
            self.name = strip_tags(s['name'].strip())
        if 'display_name' in s and s['display_name'] is not None:
            self.display_name = strip_tags(s['display_name'].strip())
        if 'nip05' in s and s['nip05'] is not None and is_nip05(s['nip05']):
            self.nip05 = s['nip05'].strip()
        if 'about' in s and s['about'] is not None:
            self.about = strip_tags(s['about'])
        if 'picture' in s and s['picture'] is not None and validators.url(s['picture'].strip(), public=True):
            self.picture = s['picture'].strip()
        D_TASKS.pool.add(TaskKind.VALIDATE_NIP5, {'pk': self.event.public_key})

    def to_dict(self):
        return {
            'public_key':self.event.public_key,
            'name':self.name,
            'display_name':self.display_name,
            'nip05':self.nip05,
            'pic':self.picture,
            'about':self.about,
            'updated_at':self.event.created_at,
            'raw':json.dumps(self.event.to_json_object())
        }


class NoteEvent:
    def __init__(self, event, my_pk):
        logger.info('New note')
        self.event = event
        self.content = strip_tags(event.content)
        self.tags = event.tags
        self.media = []
        self.members = []
        self.hashtags = []
        self.thread_root = None
        self.response_to = None
        self.reshare = None
        self.used_tags = []
        self.my_pk = my_pk
        self.mentions_me = False

        self.process_content()


    def process_content(self):
        logger.info('process note content')
        self.process_embedded_tags()
        self.process_embedded_urls()
        self.tags = [x for x in self.tags if x not in self.used_tags]
        self.process_tags()

    def process_embedded_urls(self):
        logger.info('process note urls')
        urls = get_urls_in_string(self.content)
        logger.info(urls)
        self.content = url_linkify(self.content)
        logger.info(self.content)
        for url in urls:
            logger.info('process {}'.format(url))
            if validators.url(url):
                logger.info('{} validated'.format(url))
                h = request_url_head(url)
                if h:
                    ct = h.get('content-type')
                    if ct in ['image/apng', 'image/png', 'image/avif', 'image/gif', 'image/jpeg', 'image/svg+xml', 'image/webp']:
                        logger.info('{} is image'.format(url))
                        self.media.append((url, 'image'))
                    elif ct in ["video/webm", "video/ogg", "video/mp4"]:
                        logger.info('{} is vid'.format(url))
                        ext = ct.split('/')
                        self.media.append((url, 'video', ext[1]))

        if len(self.media) < 1 and len(urls) > 0:
            logger.info('note has urls')
            note = DB.get_note(SETTINGS.get('pubkey'), self.event.id)
            already_scraped = False
            scrape_fail_attempts = 0
            if note is not None:
                logger.info('note {} already in db'.format(self.event.id))
                media = json.loads(note['media'])
                for item in media:
                    if item[1] == 'og':
                        already_scraped = True
                    elif item[1] == 'scrape_failed':
                        scrape_fail_attempts = int(item[0])

            if (note is None or not already_scraped) and validators.url(urls[0]) and scrape_fail_attempts < 4:
                logger.info('add {} to tasks for scraping'.format(urls[0]))
                D_TASKS.pool.add(TaskKind.FETCH_OG, {'url': urls[0], 'note_id': self.event.id})

    def process_embedded_tags(self):
        logger.info('process note embedded tags')
        embeds = get_embeded_tag_indexes(self.content)
        for item in embeds:
            self.process_embedded_tag(int(item))

    def process_embedded_tag(self, item):
        logger.info('process note tag {}'.format(item))
        if list_index_exists(self.tags, item) and self.tags[item][0] == "p":
            self.used_tags.append(self.tags[item])
            self.process_p_tag(item)
        elif list_index_exists(self.tags, item) and self.tags[item][0] == "e":
            self.used_tags.append(self.tags[item])
            self.process_e_tag(item)
        elif list_index_exists(self.tags, item) and self.tags[item][0] == "t":
            self.used_tags.append(self.tags[item])
            self.hashtags.append(self.tags[item][1])
            self.process_t_tag(item)

    def process_p_tag(self, item):
        logger.info('process note p tag')
        pk = self.tags[item][1]
        self.content = self.content.replace(
            "#[{}]".format(item),
            "@{}".format(pk))
        if pk == self.my_pk and self.event.public_key != self.my_pk:
            self.mentions_me = True

    def process_e_tag(self, item):
        logger.info('process note e tag')
        event_id = self.tags[item][1]
        if self.reshare is None:
            self.reshare = event_id
            self.content = self.content.replace("#[{}]".format(item), "")
        else:
            self.content = self.content.replace(
                "#[{}]".format(item),
                "<a href='/note?id={}#{}'>event:{}&#8230;</a>".format(event_id, event_id, event_id[:21]))

    def process_t_tag(self, item):
        logger.info('process note t tag')
        tag = self.tags[item][1]
        self.content = self.content.replace(
            "#[{}]".format(item),
            "#{}".format(tag))


    def process_tags(self):
        logger.info('process note tags')
        if len(self.tags) > 0:
            parents = []
            for item in self.tags:
                if item[0] == "t" and len(item) > 1:
                    self.hashtags.append(item[1])
                if item[0] == "p" and len(item) > 1:
                    self.members.append(item[1])
                    if item[1] == self.my_pk and self.event.public_key != self.my_pk:
                        self.mentions_me = True
                elif item[0] == "e" and len(item) > 1:
                    if len(item) < 4 > 1:  # deprecate format
                        parents.append(item[1])
                    elif len(item) > 3 and item[3] in ["root", "reply"]:
                        if item[3] == "root":
                            self.thread_root = item[1]
                        elif item[3] == "reply":
                            self.response_to = item[1]

            if self.thread_root is None and self.response_to is not None:
                self.thread_root = self.response_to
                self.response_to = None
            elif self.thread_root is not None and self.thread_root == self.response_to:
                self.response_to = None

            if self.thread_root is None:
                if len(parents) == 1:
                    self.thread_root = parents[0]
                elif len(parents) > 1:
                    self.thread_root = parents[0]
                    self.response_to = parents[1]

    def to_dict(self):
        return {
            'id': self.event.id,
            'public_key': self.event.public_key,
            'content': self.content,
            'response_to': self.response_to,
            'thread_root': self.thread_root,
            'reshare': self.reshare,
            'created_at': self.event.created_at,
            'members': json.dumps(self.members),
            'media': json.dumps(self.media),
            'hashtags': json.dumps(self.hashtags),
            'raw':json.dumps(self.event.to_json_object())
        }


class BoostEvent:
    def __init__(self, event):
        logger.info('New boost')
        self.event = event
        self.reshare_id = None
        self.get_boosted_event()
        self.note_content = event.content
        # if self.reshare_id is not None:
        #     DB.increment_note_share_count(self.reshare_id)

    def get_boosted_event(self):
        for tag in self.event.tags:
            if tag[0] == "e" and len(tag) > 1:
                self.reshare_id = tag[1]


    def to_dict(self):
        return {
            'id': self.event.id,
            'public_key': self.event.public_key,
            'content': '',
            'response_to': None,
            'thread_root': None,
            'reshare': self.reshare_id,
            'created_at': self.event.created_at,
            'members': json.dumps([]),
            'media': json.dumps([]),
            'hashtags': json.dumps([]),
            'raw':json.dumps(self.event.to_json_object())
        }