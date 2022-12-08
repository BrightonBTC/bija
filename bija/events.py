import os
import ssl
from urllib.parse import urlparse

from flask import render_template

from bija.app import socketio
from bija.helpers import get_embeded_tag_indexes, \
    list_index_exists, get_urls_in_string, request_nip05
from bija.subscriptions import *
from bija.submissions import *
from bija.alerts import *
from python_nostr.nostr.event import EventKind
from python_nostr.nostr.relay_manager import RelayManager


class BijaEvents:
    subscriptions = []
    pool_handler_running = False
    page = {
        'page': None,
        'identifier': None
    }

    def __init__(self, db, s):
        self.should_run = True
        self.db = db
        self.session = s
        self.relay_manager = RelayManager()
        self.open_connections()

    def open_connections(self):
        relays = self.db.get_relays()
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
        self.page = {
            'page': page,
            'identifier': identifier
        }

    def get_key(self, k='public'):
        keys = self.session.get("keys")
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
            while self.relay_manager.message_pool.has_notices():
                notice = self.relay_manager.message_pool.get_notice()

            while self.relay_manager.message_pool.has_ok_notices():
                notice = self.relay_manager.message_pool.get_ok_notice()
                print('OK:', notice)

            while self.relay_manager.message_pool.has_eose_notices():
                notice = self.relay_manager.message_pool.get_eose_notice()

            while self.relay_manager.message_pool.has_events():
                msg = self.relay_manager.message_pool.get_event()

                self.db.add_event(msg.event.id, msg.event.kind)

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
            self.db.commit()
            time.sleep(1)
            print('running')
            i += 1
            if i == 60:
                self.get_connection_status()
                i = 0

    def receive_del_event(self, event):
        DeleteEvent(self.db, event)

    def receive_reaction_event(self, event):
        e = ReactionEvent(self.db, event, self.get_key())
        note = self.db.get_note(e.event_id)
        if e.event.public_key != self.get_key():
            if note is not None and note.public_key == self.get_key():
                reaction = self.db.get_reaction_by_id(e.event.id)
                Alert(
                    e.event.id,
                    e.event.created_at, AlertKind.REACTION, e.event.public_key, e.event_id, reaction['content'])
                n = self.db.get_unread_alert_count()
                if n > 0:
                    socketio.emit('alert_n', n)

    def receive_metadata_event(self, event):
        meta = MetadataEvent(self.db, event)
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
        e = NoteEvent(self.db, event, self.get_key())
        if e.mentions_me:
            self.alert_on_note_event(e)
        self.notify_on_note_event(event, subscription)

    def alert_on_note_event(self, event):
        if event.response_to is not None:
            reply = self.db.get_note(event.response_to)
            if reply is not None and reply.public_key == self.get_key():
                Alert(
                    event.event.id,
                    event.event.created_at, AlertKind.REPLY, event.event.public_key, event.response_to, event.content)
        elif event.thread_root is not None:
            root = self.db.get_note(event.thread_root)
            if root is not None and root.public_key == self.get_key():
                Alert(
                    event.event.id,
                    event.event.created_at, AlertKind.COMMENT_ON_THREAD, event.event.public_key, event.thread_root, event.content)

    def notify_on_note_event(self, event, subscription):
        if subscription == 'primary':
            unseen_posts = self.db.get_unseen_in_feed()
            if unseen_posts > 0:
                socketio.emit('unseen_posts_n', unseen_posts)
        elif subscription == 'profile':
            socketio.emit('new_profile_posts', self.db.get_most_recent_for_pk(event.public_key))
        elif subscription == 'note-thread':
            socketio.emit('new_in_thread', event.id)

    def receive_contact_list_event(self, event, subscription):
        e = ContactListEvent(self.db, event, self.get_key())
        if e.changed:
            self.subscribe_primary()
        if e.pubkey != self.get_key() and subscription == 'profile':
            self.db.add_contact_list(event.public_key, e.keys)
            self.subscribe_profile(event.public_key, timestamp_minus(TimePeriod.WEEK))

    def receive_private_message_event(self, event):

        e = EncryptedMessageEvent(self.db, event, self.get_key())

        if self.page['page'] == 'message' and self.page['identifier'] == e.pubkey:
            messages = self.db.get_unseen_messages(e.pubkey)
            if len(messages) > 0:
                profile = self.db.get_profile(self.get_key())
                self.db.set_message_thread_read(e.pubkey)
                out = render_template("message_thread.items.html", me=profile, messages=messages)
                socketio.emit('message', out)
        else:
            unseen_n = self.db.get_unseen_message_count()
            socketio.emit('unseen_messages_n', unseen_n)

    def subscribe_thread(self, root_id):
        subscription_id = 'note-thread'
        self.subscriptions.append(subscription_id)
        SubscribeThread(subscription_id, self.relay_manager, self.db, root_id)

    def subscribe_feed(self, ids):
        subscription_id = 'main-feed'
        self.subscriptions.append(subscription_id)
        SubscribeFeed(subscription_id, self.relay_manager, self.db, ids)

    def subscribe_profile(self, pubkey, since):
        subscription_id = 'profile'
        self.subscriptions.append(subscription_id)
        SubscribeProfile(subscription_id, self.relay_manager, self.db, pubkey, since)

    # create site wide subscription
    def subscribe_primary(self):
        self.subscriptions.append('primary')
        SubscribePrimary('primary', self.relay_manager, self.db, self.get_key())

    def submit_profile(self, profile):
        e = SubmitProfile(self.relay_manager, self.db, self.session.get("keys"), profile)
        return e.event_id

    def submit_message(self, data):
        e = SubmitEncryptedMessage(self.relay_manager, self.db, self.session.get("keys"), data)
        return e.event_id

    def submit_like(self, note_id):
        e = SubmitLike(self.relay_manager, self.db, self.session.get("keys"), note_id)
        return e.event_id

    def submit_note(self, data, members=None):
        e = SubmitNote(self.relay_manager, self.db, self.session.get("keys"), data, members)
        return e.event_id

    def submit_follow_list(self):
        SubmitFollowList(self.relay_manager, self.db, self.session.get("keys"))

    def submit_delete(self, event_ids: list, reason):
        e = SubmitDelete(self.relay_manager, self.db, self.session.get("keys"), event_ids, reason)
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
    def __init__(self, db, event, my_pubkey):
        self.db = db
        self.event = event
        self.pubkey = my_pubkey
        self.event_id = None
        self.event_pk = None
        self.event_members = []

        self.process()

    def process(self):
        self.process_tags()
        if self.event_id is not None and self.event_pk is not None:
            self.store()

    def process_tags(self):
        for tag in self.event.tags:
            if tag[0] == "p":
                self.event_pk = tag[1]
                self.event_members.append(tag[1])
            if tag[0] == "e":
                self.event_id = tag[1]

    def store(self):
        self.db.add_note_reaction(
            self.event.id,
            self.event.public_key,
            self.event_id,
            self.event_pk,
            self.event.content,
            json.dumps(self.event_members),
            json.dumps(self.event.to_json_object())
        )
        if self.event.public_key == self.pubkey:
            self.db.set_note_liked(self.event_id)



class DeleteEvent:
    def __init__(self, db, event):
        self.db = db
        self.event = event
        self.process()

    def process(self):
        for tag in self.event.tags:
            if tag[0] == 'e':
                e = self.db.get_event(tag[1])
                if e is not None and e.kind == EventKind.REACTION:
                    self.db.delete_reaction(tag[1])
                if e is not None and e.kind == EventKind.TEXT_NOTE:
                    self.db.set_note_deleted(tag[1], self.event.content)


class ContactListEvent:
    def __init__(self, db, event, pubkey):
        self.db = db
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
        following = self.db.get_following_pubkeys()
        new = set(self.keys) - set(following)
        removed = set(following) - set(self.keys)
        if len(new) > 0:
            self.changed = True
            self.db.set_following(new, True)
        if len(removed) > 0:
            self.changed = True
            self.db.set_following(removed, False)


class EncryptedMessageEvent:
    def __init__(self, db, event, my_pubkey):
        self.my_pubkey = my_pubkey
        self.db = db
        self.event = event
        self.is_sender = None
        self.pubkey = None

        self.process_data()

    def process_data(self):
        self.set_receiver_sender()
        if self.pubkey is not None and self.is_sender is not None:
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
        self.db.add_profile_if_not_exists(self.event.public_key)
        self.db.insert_private_message(
            self.event.id,
            self.pubkey,
            self.event.content,
            self.is_sender,
            self.event.created_at,
            json.dumps(self.event.to_json_object())
        )


class MetadataEvent:
    def __init__(self, db, event):
        self.db = db
        self.event = event
        self.name = None
        self.nip05 = None
        self.about = None
        self.picture = None
        self.nip05_validated = False

        self.process_content()
        self.store()

    def process_content(self):
        s = json.loads(self.event.content)
        if 'name' in s:
            self.name = s['name']
        if 'nip05' in s:
            self.nip05 = s['nip05']
        if 'about' in s:
            self.about = s['about']
        if 'picture' in s:
            self.picture = s['picture']

        if self.nip05 is not None:
            current = self.db.get_profile(self.event.public_key)
            if current is None or current.nip05 != self.nip05:
                if self.validate_nip05(self.nip05, self.event.public_key):
                    self.db.set_valid_nip05(self.event.public_key)
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
        self.db.upd_profile(
            self.event.public_key,
            self.name,
            self.nip05,
            self.picture,
            self.about,
            self.event.created_at,
            json.dumps(self.event.to_json_object())
        )


class NoteEvent:
    def __init__(self, db, event, my_pk):
        self.db = db
        self.event = event
        self.content = event.content
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

    def process_content(self):
        self.process_embedded_tags()
        self.process_embedded_urls()

    def process_embedded_urls(self):
        urls = get_urls_in_string(self.content)
        for url in urls:
            parts = url.split('//')
            if len(parts) < 2:
                parts = ['', url]
                url = 'https://' + url
            if len(parts[1]) > 21:
                link_text = parts[1][:21] + '...'
            else:
                link_text = parts[1]
            self.content = self.content.replace(
                url,
                "<a href='{}'>{}</a>".format(url, link_text))
            path = urlparse(url).path
            extension = os.path.splitext(path)[1]
            if extension.lower() in ['.png', '.svg', '.gif', '.jpg', '.jpeg']:
                self.media.append((url, 'image'))

    def process_embedded_tags(self):
        embeds = get_embeded_tag_indexes(self.content)
        for item in embeds:
            self.process_embedded_tag(int(item))

    def process_embedded_tag(self, item):
        if list_index_exists(self.tags, item) and self.tags[item][0] == "p":
            self.used_tags.append(self.tags[item])
            self.process_p_tag(item)
        elif list_index_exists(self.tags, item) and self.tags[item][0] == "e":
            self.used_tags.append(self.tags[item])
            self.process_e_tag(item)

    def process_p_tag(self, item):
        pk = self.tags[item][1]
        profile = self.db.get_profile(pk)
        if profile is not None and profile.name is not None:
            name = profile.name
        else:
            name = '{}...{}'.format(pk[:3], pk[-5:])
        self.content = self.content.replace(
            "#[{}]".format(item),
            "<a class='uname' href='/profile?pk={}'>@{}</a>".format(pk, name))
        if pk == self.my_pk and self.event.public_key != self.my_pk:
            self.mentions_me = True

    def process_e_tag(self, item):
        event_id = self.tags[item][1]
        if self.reshare is None:
            self.reshare = event_id
            self.content = self.content.replace("#[{}]".format(item), "")
        else:
            self.content = self.content.replace(
                "#[{}]".format(item),
                "<a href='/note?id={}#{}'>event:{}...</a>".format(event_id, event_id, event_id[:21]))

    def process_tags(self):
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
                if len(parents) == 1:
                    self.response_to = parents[0]
                elif len(parents) > 1:
                    self.thread_root = parents[0]
                    self.response_to = parents[1]

    def update_db(self):
        self.db.add_profile_if_not_exists(self.event.public_key)
        self.db.insert_note(
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


