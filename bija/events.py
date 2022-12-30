import logging
import os
import ssl
import textwrap
import time
from urllib.parse import urlparse

import validators as validators
from flask import render_template

from bija.app import socketio
from bija.args import LOGGING_LEVEL
from bija.deferred_tasks import TaskKind, DeferredTasks
from bija.helpers import get_embeded_tag_indexes, \
    list_index_exists, get_urls_in_string, request_nip05, url_linkify, strip_tags, request_relay_data, is_nip05
from bija.subscriptions import *
from bija.submissions import *
from bija.alerts import *
from bija.settings import Settings
from python_nostr.nostr.event import EventKind
from python_nostr.nostr.pow import count_leading_zero_bits
from python_nostr.nostr.relay_manager import RelayManager

logger = logging.getLogger(__name__)
FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(format=FORMAT)
logger.setLevel(LOGGING_LEVEL)

D_TASKS = DeferredTasks()
DB = BijaDB(app.session)


class BijaEvents:
    subscriptions = set()
    pool_handler_running = False
    page = {
        'page': None,
        'identifier': None
    }
    active_events = {}  # events that are open in the current ui view

    def __init__(self):
        self.should_run = True
        self.relay_manager = RelayManager()
        self.open_connections()

    def open_connections(self):
        relays = DB.get_relays()
        n_relays = 0
        for r in relays:
            n_relays += 1
            self.relay_manager.add_relay(r.name)
        if n_relays > 0:
            self.relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})

    # close existing connections, reopen, and start primary subscription
    # used after adding or removing relays
    def reset(self):
        self.relay_manager.close_connections()
        time.sleep(1)
        self.relay_manager.relays = {}
        time.sleep(1)
        self.open_connections()
        time.sleep(1)
        self.subscribe_primary()
        time.sleep(1)
        self.get_connection_status()

    def remove_relay(self, url):
        self.relay_manager.remove_relay(url)

    def add_relay(self, url):
        self.relay_manager.add_relay(url)

    def get_connection_status(self):
        status = self.relay_manager.get_connection_status()
        out = []
        for s in status:
            if s[1] is not None:
                out.append([s[0], int(time.time() - s[1])])
            else:
                out.append([s[0], None])
        socketio.emit('conn_status', out)

    def set_page(self, page, identifier):
        self.active_events = {}
        self.page = {
            'page': page,
            'identifier': identifier
        }

    def get_key(self, k='public'):
        keys = Settings.get("keys")
        if keys is not None and k in keys:
            return keys[k]
        else:
            return False

    def message_pool_handler(self):
        if self.pool_handler_running:
            return
        self.pool_handler_running = True
        i = 0
        while self.should_run:
            try:
                while self.relay_manager.message_pool.has_notices():
                    notice = self.relay_manager.message_pool.get_notice()

                while self.relay_manager.message_pool.has_ok_notices():
                    notice = self.relay_manager.message_pool.get_ok_notice()

                while self.relay_manager.message_pool.has_eose_notices():
                    notice = self.relay_manager.message_pool.get_eose_notice()
                    print('EOSE', notice.url, notice.subscription_id)

                while self.relay_manager.message_pool.has_events():
                    msg = self.relay_manager.message_pool.get_event()
                    if DB.get_event(msg.event.id) is None:
                        logger.info('New event: {}'.format(msg.event.kind))
                        if msg.event.kind == EventKind.SET_METADATA:
                            self.receive_metadata_event(msg.event)

                        if msg.event.kind == EventKind.CONTACTS:
                            self.receive_contact_list_event(msg.event, msg.subscription_id)

                        if msg.event.kind == EventKind.TEXT_NOTE:
                            self.receive_note_event(msg.event, msg.subscription_id)

                        if msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                            self.receive_private_message_event(msg.event)

                        if msg.event.kind == EventKind.DELETE:
                            self.receive_del_event(msg.event)

                        if msg.event.kind == EventKind.REACTION:
                            self.receive_reaction_event(msg.event)

                        if msg.subscription_id != 'search':
                            DB.add_event(msg.event.id, msg.event.kind)
                DB.commit()
                D_TASKS.next()
                time.sleep(1)
                logger.info('Event loop {}'.format(int(time.time())))
                i += 1
                if i == 60:
                    self.get_connection_status()
                    socketio.emit('subscriptions', list(self.subscriptions))
                    i = 0
            except:
                pass

    def receive_del_event(self, event):
        DeleteEvent(event)

    def receive_reaction_event(self, event):
        e = ReactionEvent(event, self.get_key())
        if e.valid:
            note = DB.get_note(e.event_id)
            if e.event.content != '-' and 'notes' in self.active_events and e.event_id in self.active_events['notes']:
                socketio.emit('new_reaction', e.event_id)
                logger.info('Reaction on active note detected, signal to UI')
            if e.event.public_key != self.get_key():
                logger.info('Reaction is not from me')
                if note is not None and note.public_key == self.get_key():
                    logger.info('Get reaction from DB')
                    reaction = DB.get_reaction_by_id(e.event.id)
                    logger.info('Compose reaction alert')
                    Alert(
                        e.event.id,
                        e.event.created_at, AlertKind.REACTION, e.event.public_key, e.event_id, reaction.content)
                    logger.info('Get unread alert count')
                    n = DB.get_unread_alert_count()
                    if n > 0:
                        socketio.emit('alert_n', n)

    def receive_metadata_event(self, event):
        meta = MetadataEvent(event)
        if self.page['page'] == 'profile' and self.page['identifier'] == event.public_key:
            if meta.picture is None or len(meta.picture.strip()) == 0:
                meta.picture = '/identicon?id={}'.format(event.public_key)
            socketio.emit('profile_update', {
                'public_key': event.public_key,
                'name': meta.name,
                'nip05': meta.nip05,
                'nip05_validated': meta.nip05_validated,
                'pic': meta.picture,
                'about': meta.about,
                'created_at': event.created_at
            })

    def receive_note_event(self, event, subscription):
        if subscription == 'search':
            socketio.emit('search_result', {
                'id': event.id,
                'content': textwrap.shorten(
                    strip_tags(event.content),
                    width=200,
                    replace_whitespace=False,
                    break_long_words=True,
                    placeholder="...")
            })
            return
        e = NoteEvent(event, self.get_key())
        if e.mentions_me:
            self.alert_on_note_event(e)
        self.notify_on_note_event(event, subscription)

        if 'notes' in self.active_events:
            if e.event.id in self.active_events['notes']:
                logger.info('New required note {}'.format(e.event.id))
                socketio.emit('new_note', e.event.id)
            if e.response_to in self.active_events['notes']:
                logger.info('Detected response to active note {}'.format(e.response_to))
                socketio.emit('new_reply', e.response_to)
            elif e.response_to is None and e.thread_root in self.active_events['notes']:
                logger.info('Detected response to active note {}'.format(e.thread_root))
                socketio.emit('new_reply', e.thread_root)
            if e.reshare in self.active_events['notes']:
                logger.info('Detected reshare on active note {}'.format(e.reshare))
                socketio.emit('new_reshare', e.reshare)

    def alert_on_note_event(self, event):
        if event.response_to is not None:
            reply = DB.get_note(event.response_to)
            if reply is not None and reply.public_key == self.get_key():
                Alert(
                    event.event.id,
                    event.event.created_at, AlertKind.REPLY, event.event.public_key, event.response_to, event.content)
        elif event.thread_root is not None:
            root = DB.get_note(event.thread_root)
            if root is not None and root.public_key == self.get_key():
                Alert(
                    event.event.id,
                    event.event.created_at, AlertKind.COMMENT_ON_THREAD, event.event.public_key, event.thread_root,
                    event.content)

    def notify_on_note_event(self, event, subscription):
        if subscription == 'primary':
            unseen_posts = DB.get_unseen_in_feed()
            if unseen_posts > 0:
                socketio.emit('unseen_posts_n', unseen_posts)
        elif subscription == 'profile':
            DB.set_note_seen(event.id)
            socketio.emit('new_profile_posts', DB.get_most_recent_for_pk(event.public_key))
        elif subscription == 'note-thread':
            socketio.emit('new_in_thread', event.id)

    def receive_contact_list_event(self, event, subscription):
        e = ContactListEvent(event, self.get_key())
        DB.add_profile_if_not_exists(event.public_key)
        DB.add_contact_list(event.public_key, e.keys)
        if e.changed:
            self.subscribe_primary()
        if event.public_key != self.get_key() and subscription == 'profile':
            self.subscribe_profile(event.public_key, timestamp_minus(TimePeriod.WEEK), [])
        if self.get_key() in e.keys:
            DB.set_follower(event.public_key)

    def receive_private_message_event(self, event):

        e = EncryptedMessageEvent(event, self.get_key())
        if self.page['page'] == 'message' and self.page['identifier'] == e.pubkey:
            messages = DB.get_unseen_messages(e.pubkey)
            if len(messages) > 0:
                profile = DB.get_profile(self.get_key())
                DB.set_message_thread_read(e.pubkey)
                out = render_template("message_thread.items.html",
                                      me=profile, messages=messages, privkey=self.get_key('private'))
                socketio.emit('message', out)
        else:
            unseen_n = DB.get_unseen_message_count()
            socketio.emit('unseen_messages_n', unseen_n)

    def subscribe_thread(self, root_id, ids):
        self.active_events['notes'] = ids
        subscription_id = 'note-thread'
        self.subscriptions.add(subscription_id)
        SubscribeThread(subscription_id, self.relay_manager, root_id)

    def subscribe_feed(self, ids):
        if 'notes' in self.active_events:
            self.active_events['notes'] += ids
        else:
            self.active_events['notes'] = ids
        subscription_id = 'main-feed'
        self.subscriptions.add(subscription_id)
        SubscribeFeed(subscription_id, self.relay_manager, ids)

    def subscribe_profile(self, pubkey, since, ids):
        if 'notes' in self.active_events:
            self.active_events['notes'] += ids
        else:
            self.active_events['notes'] = ids
        subscription_id = 'profile'
        self.subscriptions.add(subscription_id)
        SubscribeProfile(subscription_id, self.relay_manager, pubkey, since)

    # create site wide subscription
    def subscribe_primary(self):
        self.subscriptions.add('primary')
        SubscribePrimary('primary', self.relay_manager, self.get_key())

    def subscribe_search(self, term):
        logger.info('Subscribe search {}'.format(term))
        self.subscriptions.add('search')
        SubscribeSearch('search', self.relay_manager, term)

    def submit_profile(self, profile):
        e = SubmitProfile(self.relay_manager, Settings.get("keys"), profile)
        return e.event_id

    def submit_message(self, data, pow_difficulty=None):
        e = SubmitEncryptedMessage(self.relay_manager, Settings.get("keys"), data, pow_difficulty)
        return e.event_id

    def submit_like(self, note_id):
        e = SubmitLike(self.relay_manager, Settings.get("keys"), note_id)
        return e.event_id

    def submit_note(self, data, members=None, pow_difficulty=None):
        e = SubmitNote(self.relay_manager, Settings.get("keys"), data, members, pow_difficulty)
        return e.event_id

    def submit_follow_list(self):
        SubmitFollowList(self.relay_manager, Settings.get("keys"))

    def submit_delete(self, event_ids: list, reason=""):
        e = SubmitDelete(self.relay_manager, Settings.get("keys"), event_ids, reason)
        return e.event_id

    def close_subscription(self, name):
        self.subscriptions.remove(name)
        self.relay_manager.close_subscription(name)

    def close_secondary_subscriptions(self):
        for s in self.subscriptions:
            if s not in ['primary', 'following']:
                self.close_subscription(s)

    def close(self):
        self.should_run = False
        self.relay_manager.close_connections()


class ReactionEvent:
    def __init__(self, event, my_pubkey):
        self.event = event
        self.pubkey = my_pubkey
        self.event_id = None
        self.event_pk = None
        self.event_members = []
        self.valid = False

        self.process()

    def process(self):
        self.process_tags()
        if self.event_id is not None and self.event_pk is not None:
            self.valid = True
            self.store()
            self.update_referenced()
        else:
            logger.debug('Invalid reaction event could not be stored.')

    def process_tags(self):
        for tag in self.event.tags:
            if tag[0] == "p" and is_hex_key(tag[1]):
                self.event_pk = tag[1]
                self.event_members.append(tag[1])
            if tag[0] == "e" and is_hex_key(tag[1]):
                self.event_id = tag[1]

    def store(self):
        DB.add_note_reaction(
            self.event.id,
            self.event.public_key,
            self.event_id,
            self.event_pk,
            strip_tags(self.event.content),
            json.dumps(self.event_members),
            json.dumps(self.event.to_json_object())
        )
        DB.add_profile_if_not_exists(self.event_pk)
        DB.add_profile_if_not_exists(self.event.public_key)
        if self.event.public_key == self.pubkey:
            DB.set_note_liked(self.event_id)

    def update_referenced(self):
        if self.event.content != "-":
            DB.increment_note_like_count(self.event_id)


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
        self.changed = False

        self.compile_keys()
        if event.public_key == self.pubkey:
            self.set_following()

    def compile_keys(self):
        for p in self.event.tags:
            if p[0] == "p":
                self.keys.append(p[1])

    def set_following(self):
        following = DB.get_following_pubkeys()
        new = set(self.keys) - set(following)
        removed = set(following) - set(self.keys)
        if len(new) > 0:
            self.changed = True
            DB.set_following(new, True)
        if len(removed) > 0:
            self.changed = True
            DB.set_following(removed, False)


class EncryptedMessageEvent:
    def __init__(self, event, my_pubkey):
        self.my_pubkey = my_pubkey
        self.event = event
        self.is_sender = None
        self.pubkey = None
        self.passed = False

        self.process_data()

    def check_pow(self):
        if self.is_sender == 1:
            f = DB.am_following(self.pubkey)
            if f is not None:
                self.passed = True
            else:
                req_pow = Settings.get('pow_required_enc')
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
        if self.pubkey is not None and self.is_sender is not None and self.passed:
            self.store()

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

    def store(self):
        DB.add_profile_if_not_exists(self.event.public_key)
        DB.insert_private_message(
            self.event.id,
            self.pubkey,
            self.event.content,
            self.is_sender,
            self.event.created_at,
            json.dumps(self.event.to_json_object())
        )


class MetadataEvent:
    def __init__(self, event):
        self.event = event
        self.name = None
        self.nip05 = None
        self.about = None
        self.picture = None
        self.nip05_validated = False
        if self.is_fresh():
            self.process_content()
            self.store()

    def is_fresh(self):
        ts = DB.get_profile_last_upd(self.event.public_key)
        if ts is None or ts.updated_at < self.event.created_at:
            return True
        return False

    def process_content(self):
        s = json.loads(self.event.content)
        if 'name' in s:
            self.name = strip_tags(s['name'].strip())
        if 'nip05' in s and is_nip05(s['nip05']):
            self.nip05 = s['nip05'].strip()
        if 'about' in s:
            self.about = strip_tags(s['about'])
        if 'picture' in s and validators.url(s['picture'].strip(), public=True):
            self.picture = s['picture'].strip()

        if self.nip05 is not None:
            current = DB.get_profile(self.event.public_key)
            if current is None or current.nip05 != self.nip05:
                if self.validate_nip05(self.nip05, self.event.public_key):
                    DB.set_valid_nip05(self.event.public_key)
                    self.nip05_validated = True
            elif current is not None:
                self.nip05_validated = current.nip05
            else:
                self.nip05_validated = False

    @staticmethod
    def validate_nip05(nip05, pk):
        validated_name = request_nip05(nip05)
        if validated_name is not None and validated_name == pk:
            return True
        return False

    def store(self):
        DB.upd_profile(
            self.event.public_key,
            self.name,
            self.nip05,
            self.picture,
            self.about,
            self.event.created_at,
            json.dumps(self.event.to_json_object())
        )


class NoteEvent:
    def __init__(self, event, my_pk):
        if DB.get_event(event.id) is None:
            logger.info('New note')
            self.event = event
            self.content = strip_tags(event.content)
            self.tags = event.tags
            self.media = []
            self.members = []
            self.thread_root = None
            self.response_to = None
            self.reshare = None
            self.used_tags = []
            self.my_pk = my_pk
            self.mentions_me = False

            self.process_content()
            self.tags = [x for x in self.tags if x not in self.used_tags]
            self.process_tags()
            self.update_db()
            self.update_referenced()

    def process_content(self):
        logger.info('process note content')
        self.process_embedded_tags()
        self.process_embedded_urls()

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
                path = urlparse(url).path
                extension = os.path.splitext(path)[1]
                if extension.lower() in ['.png', '.svg', '.gif', '.jpg', '.jpeg']:
                    logger.info('{} is image'.format(url))
                    self.media.append((url, 'image'))
                if extension.lower() in ['.mp4', '.mov', '.ogg', '.webm', '.avi']:
                    logger.info('{} is vid'.format(url))
                    self.media.append((url, 'video', extension.lower()[1:]))

        if len(self.media) < 1 and len(urls) > 0:
            logger.info('note has urls')
            note = DB.get_note(self.event.id)
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

    def process_tags(self):
        logger.info('process note tags')
        if len(self.tags) > 0:
            parents = []
            for item in self.tags:
                if item[0] == "p":
                    self.members.append(item[1])
                    if item[1] == self.my_pk and self.event.public_key != self.my_pk:
                        self.mentions_me = True
                elif item[0] == "e":
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

    def update_db(self):
        logger.info('update db new note')
        DB.add_profile_if_not_exists(self.event.public_key)
        DB.insert_note(
            self.event.id,
            self.event.public_key,
            self.content,
            self.response_to,
            self.thread_root,
            self.reshare,
            self.event.created_at,
            json.dumps(self.members),
            json.dumps(self.media),
            json.dumps(self.event.to_json_object())
        )

    def update_referenced(self):
        logger.info('update refs new note')
        # is this a reply to another note?
        if self.response_to is not None:
            DB.increment_note_reply_count(self.response_to)
        elif self.thread_root is not None:
            DB.increment_note_reply_count(self.thread_root)
        # is this a re-share of another note?
        elif self.reshare is not None:
            DB.increment_note_share_count(self.reshare)
