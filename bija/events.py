import json
import logging
import os
import ssl
import time
import traceback
from urllib.parse import urlparse

import requests as requests
from flask import render_template

from bija.app import socketio
from bija.helpers import timestamp_minus, TimePeriod, is_hex_key, validate_nip05, get_embeded_tag_indexes, \
    list_index_exists, get_urls_in_string
from python_nostr.nostr.event import EventKind, Event
from python_nostr.nostr.filter import Filters, Filter
from python_nostr.nostr.key import PrivateKey
from python_nostr.nostr.message_type import ClientMessageType
from python_nostr.nostr.relay_manager import RelayManager


class BijaEvents:
    subscriptions = []
    pool_handler_running = False
    page = {
        'page': None,
        'identifier': None
    }

    def __init__(self, db, session):
        self.should_run = True
        self.db = db
        self.session = session
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

            while self.relay_manager.message_pool.has_eose_notices():
                notice = self.relay_manager.message_pool.get_eose_notice()

            while self.relay_manager.message_pool.has_events():
                msg = self.relay_manager.message_pool.get_event()
                if msg.event.kind == EventKind.SET_METADATA:
                    self.handle_metadata_event(msg.event)

                if msg.event.kind == EventKind.CONTACTS:
                    self.handle_contact_list_event(msg.event, msg.subscription_id)

                if msg.event.kind == EventKind.TEXT_NOTE:
                    self.handle_note_event(msg.event, msg.subscription_id)

                if msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                    self.handle_private_message_event(msg.event)

                if msg.event.kind == EventKind.DELETE:
                    self.handle_deleted_event(msg.event)

                if msg.event.kind == EventKind.REACTION:
                    self.handle_deleted_event(msg.event)
            time.sleep(1)
            print('running')
            i += 1
            if i == 60:
                self.get_connection_status()
                i = 0

    def handle_deleted_event(self, event):
        pass

    def handle_metadata_event(self, event):
        s = json.loads(event.content)
        name = None
        nip05 = None
        about = None
        picture = None
        if 'name' in s:
            name = s['name']
        if 'nip05' in s:
            nip05 = s['nip05']
        if 'about' in s:
            about = s['about']
        if 'picture' in s:
            picture = s['picture']
        result = self.db.upd_profile(
            event.public_key,
            name,
            nip05,
            picture,
            about,
            event.created_at,
            json.dumps(event.to_json_object())
        )
        if result.nip05 is not None and result.nip05_validated == 0:
            if self.validate_nip05(result.nip05, result.public_key):
                self.db.set_valid_nip05(result.public_key)
        if self.page['page'] == 'profile' and self.page['identifier'] == event.public_key:
            if picture is None or len(picture.strip()) == 0:
                picture = '/identicon?id={}'.format(event.public_key)
            socketio.emit('profile_update', {
                'public_key': event.public_key,
                'name': name,
                'nip05': nip05,
                'nip05_validated': result.nip05_validated,
                'pic': picture,
                'about': about,
                'created_at': event.created_at
            })

    def validate_nip05(self, nip05, pk):
        validated_name = self.request_nip05(nip05)
        if validated_name is not None and validated_name == pk:
            return True
        return False

    @staticmethod
    def request_nip05(nip05):
        valid_parts = validate_nip05(nip05)
        if valid_parts:
            name = valid_parts[0]
            address = valid_parts[1]
            try:
                response = requests.get(
                    'https://{}/.well-known/nostr.json'.format(address), params={'name': name}, timeout=2
                )
                if response.status_code == 200:
                    try:
                        d = response.json()
                        if name in d['names']:
                            return d['names'][name]
                    except ValueError:
                        return None
                    except Exception as e:
                        logging.error(traceback.format_exc())
                else:
                    return None
            except ConnectionError:
                return None
            except Exception as e:
                logging.error(traceback.format_exc())
                return None
        else:
            return None

    def handle_note_event(self, event, subscription):
        response_to = None
        thread_root = None
        members = ""
        if len(event.tags) > 0:
            parents = []
            for item in event.tags:
                if item[0] == "p":
                    members += item[1] + ", "
                elif item[0] == "e":
                    if len(item) == 2:  # deprecate format
                        parents.append(item[1])
                    elif len(item) > 3 and item[3] in ["root", "reply"]:
                        if item[3] == "root":
                            thread_root = item[1]
                        elif item[3] == "reply":
                            response_to = item[1]
                if len(parents) == 1:
                    response_to = parents[0]
                elif len(parents) > 1:
                    thread_root = parents[0]
                    response_to = parents[1]
        is_known = self.db.is_known_pubkey(event.public_key)
        if is_known is None:
            self.db.add_profile(event.public_key, updated_at=0)
        content, media = self.process_note_content(event.content, event.tags)
        self.db.insert_note(
            event.id,
            event.public_key,
            content,
            response_to,
            thread_root,
            event.created_at,
            members,
            media,
            json.dumps(event.to_json_object())
        )
        if subscription == 'primary':
            unseen_posts = self.db.get_unseen_in_feed(self.get_key())
            if unseen_posts > 0:
                socketio.emit('unseen_posts_n', unseen_posts)
        elif subscription == 'profile':
            socketio.emit('new_profile_posts', True)
        elif subscription == 'note-thread':
            socketio.emit('new_in_thread', event.id)

    def process_note_content(self, content, tags):
        embeds = get_embeded_tag_indexes(content)
        for item in embeds:
            item = int(item)
            if list_index_exists(tags, item) and tags[item][0] == "p":
                pk = tags[item][1]
                profile = self.db.get_profile(pk)
                if profile is not None:
                    name = profile.name
                else:
                    name = '{}...{}'.format(pk[:3], pk[-5:])
                content = content.replace(
                    "#[{}]".format(item),
                    "<a class='uname' href='/profile?pk={}'>@{}</a>".format(pk, name))
        urls = get_urls_in_string(content)
        media = []
        for url in urls:
            parts = url.split('//')
            if len(parts) < 2:
                parts = ['', url]
                url = 'https://'+url
            if len(parts[1]) > 21:
                link_text = parts[1][:21]+'...'
            else:
                link_text = parts[1]
            content = content.replace(
                url,
                "<a href='{}'>{}</a>".format(url, link_text))
            path = urlparse(url).path
            extension = os.path.splitext(path)[1]
            if extension.lower() in ['.png', '.svg', '.gif', '.jpg', '.jpeg']:
                media.append((url, 'image'))
        return content, json.dumps(media)

    def submit_note(self, data):
        k = bytes.fromhex(self.get_key('private'))
        private_key = PrivateKey(k)
        r = self.db.get_preferred_relay()
        preferred_relay = r.name
        tags = [['client', 'BIJA']]
        response_to = None
        thread_root = None

        if 'new_post' in data:
            note = data['new_post']
        elif 'reply' in data:
            note = data['reply']
            if 'pubkey' in data and is_hex_key(data['pubkey']):
                tags.append(["p", data['pubkey'], preferred_relay])
            else:
                return False
            if 'parent_id' not in data or 'thread_root' not in data:
                return False
            elif data['thread_root'] == data['parent_id'] and is_hex_key(data['parent_id']):
                response_to = data['parent_id']
                tags.append(["e", data['parent_id'], preferred_relay, "reply"])
            elif is_hex_key(data['parent_id']) and is_hex_key(data['thread_root']):
                tags.append(["e", data['parent_id'], preferred_relay, "reply"])
                tags.append(["e", data['thread_root'], preferred_relay, "root"])
        else:
            return False

        created_at = int(time.time())
        event = Event(private_key.public_key.hex(), note, tags=tags, created_at=created_at)
        event.sign(private_key.hex())

        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        self.relay_manager.publish_message(message)
        self.db.insert_note(
            event.id,
            private_key.public_key.hex(),
            note,
            response_to,
            thread_root,
            created_at
        )
        return event.id

    def submit_follow_list(self):
        k = bytes.fromhex(self.get_key('private'))
        private_key = PrivateKey(k)
        pk_list = self.db.get_following_pubkeys()
        tags = []
        for pk in pk_list:
            tags.append(["p", pk])
        created_at = int(time.time())
        event = Event(private_key.public_key.hex(), "", tags=tags, created_at=created_at, kind=EventKind.CONTACTS)
        event.sign(private_key.hex())
        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        self.relay_manager.publish_message(message)

    def handle_contact_list_event(self, event, subscription):
        keys = []
        for p in event.tags:
            if p[0] == "p":
                keys.append(p[1])
        if event.public_key == self.get_key():
            following_pubkeys = self.db.get_following_pubkeys()
            new = set(keys) - set(following_pubkeys)
            removed = set(following_pubkeys) - set(keys)
            if len(new) > 0:
                self.db.set_following(new)
            if len(removed) > 0:
                self.db.set_following(removed, False)
            self.subscribe_primary()
        elif subscription == 'profile':  # we received another users contacts
            self.db.add_contact_list(event.public_key, keys)
            self.subscribe_profile(event.public_key, timestamp_minus(TimePeriod.WEEK))

    def handle_private_message_event(self, event):
        to = False
        for p in event.tags:
            if p[0] == "p":
                to = p[1]
        if to and [getattr(event, attr) for attr in ['id', 'public_key', 'content', 'created_at']]:
            pk = None
            is_sender = None
            if to == self.get_key():
                pk = event.public_key
                is_sender = 1
            elif event.public_key == self.get_key():
                pk = to
                is_sender = 0
            if pk is not None and is_sender is not None:
                self.db.insert_private_message(
                    event.id,
                    pk,
                    event.content,
                    is_sender,
                    event.created_at,
                    json.dumps(event.to_json_object())
                )
            is_known = self.db.is_known_pubkey(event.public_key)
            if is_known is None:
                self.db.add_profile(event.public_key, updated_at=0)

            if self.page['page'] == 'message' and self.page['identifier'] == pk:
                messages = self.db.get_unseen_messages(pk)
                if len(messages) > 0:
                    profile = self.db.get_profile(self.get_key())
                    self.db.set_message_thread_read(pk)
                    out = render_template("message_thread.items.html", me=profile, messages=messages)
                    socketio.emit('message', out)
            else:
                unseen_n = self.db.get_unseen_message_count()
                socketio.emit('unseen_messages_n', unseen_n)

    def handle_deleted_event(self, event):
        pass

    def close_subscription(self, name):
        self.subscriptions.remove(name)
        self.relay_manager.close_subscription(name)

    def close_secondary_subscriptions(self):
        for s in self.subscriptions:
            if s not in ['primary', 'following']:
                self.close_subscription(s)

    def subscribe_thread(self, root_id):
        subscription_id = 'note-thread'
        self.subscriptions.append(subscription_id)
        ids = self.db.get_note_thread_ids(root_id)
        if len(ids) < 1:
            ids = [root_id]

        print('thread subscription', ids)
        filters = Filters([
            Filter(tags={'#e': ids}, kinds=[EventKind.TEXT_NOTE]),  # event responses
            Filter(ids=ids, kinds=[EventKind.TEXT_NOTE])
        ])
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        self.relay_manager.add_subscription(subscription_id, filters)
        time.sleep(1.25)
        message = json.dumps(request)
        self.relay_manager.publish_message(message)

    def subscribe_profile(self, pubkey, since):
        subscription_id = 'profile'
        self.subscriptions.append(subscription_id)
        profile = self.db.get_profile(pubkey)

        f = [
            Filter(authors=[pubkey], kinds=[EventKind.SET_METADATA, EventKind.CONTACTS]),
            Filter(authors=[pubkey], kinds=[EventKind.TEXT_NOTE, EventKind.DELETE], since=since)
        ]
        if profile is not None and profile.contacts is not None:
            contacts_filter = Filter(authors=json.loads(profile.contacts), kinds=[EventKind.SET_METADATA])
            f.append(contacts_filter)

        filters = Filters(f)
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        self.relay_manager.add_subscription(subscription_id, filters)
        time.sleep(1.25)
        message = json.dumps(request)
        self.relay_manager.publish_message(message)

    # create site wide subscription
    def subscribe_primary(self):
        pubkey = self.get_key()
        self.subscriptions.append('primary')
        kinds = [EventKind.SET_METADATA,
                 EventKind.TEXT_NOTE,
                 EventKind.RECOMMEND_RELAY,
                 EventKind.CONTACTS,
                 EventKind.ENCRYPTED_DIRECT_MESSAGE,
                 EventKind.DELETE,
                 EventKind.REACTION]
        profile_filter = Filter(authors=[pubkey], kinds=kinds)
        kinds = [EventKind.TEXT_NOTE, EventKind.ENCRYPTED_DIRECT_MESSAGE, EventKind.REACTION]
        mentions_filter = Filter(tags={'#p': [pubkey]}, kinds=kinds)
        f = [profile_filter, mentions_filter]
        following_pubkeys = self.db.get_following_pubkeys()

        if len(following_pubkeys) > 0:
            following_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.TEXT_NOTE],
                since=timestamp_minus(TimePeriod.WEEK))  # TODO: should be configurable in user settings
            following_profiles_filter = Filter(
                authors=following_pubkeys,
                kinds=[EventKind.SET_METADATA, EventKind.DELETE, EventKind.REACTION],
            )
            f.append(following_filter)
            f.append(following_profiles_filter)

        filters = Filters(f)

        subscription_id = 'primary'
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        self.relay_manager.add_subscription(subscription_id, filters)
        time.sleep(1.25)
        message = json.dumps(request)
        self.relay_manager.publish_message(message)

    def decrypt(self, message, public_key):
        try:
            k = bytes.fromhex(self.get_key('private'))
            pk = PrivateKey(k)
            return pk.decrypt_message(message, public_key)
        except ValueError:
            return 'could not decrypt!'

    def encrypt(self, message, public_key):
        try:
            k = bytes.fromhex(self.get_key('private'))
            pk = PrivateKey(k)
            return pk.encrypt_message(message, public_key)
        except ValueError:
            return False

    def update_profile(self, profile):
        k = bytes.fromhex(self.get_key('private'))
        private_key = PrivateKey(k)
        created_at = int(time.time())

        event = Event(
            private_key.public_key.hex(),
            json.dumps(profile),
            kind=EventKind.SET_METADATA,
            created_at=created_at)
        event.sign(private_key.hex())

        message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
        self.relay_manager.publish_message(message)
        print(event.to_json_object())
        return event.id

    def submit_message(self, data):
        pk = None
        txt = None
        for v in data:
            if v[0] == "new_message":
                txt = v[1]
            elif v[0] == "new_message_pk":
                pk = v[1]
        if pk is not None and txt is not None:
            k = bytes.fromhex(self.session.get("keys")['private'])
            private_key = PrivateKey(k)
            tags = [['p', pk], ['client', 'BIJA']]
            created_at = int(time.time())
            enc = self.encrypt(txt, pk)
            event = Event(private_key.public_key.hex(), enc, tags=tags, created_at=created_at,
                          kind=EventKind.ENCRYPTED_DIRECT_MESSAGE)
            event.sign(private_key.hex())

            message = json.dumps([ClientMessageType.EVENT, event.to_json_object()], ensure_ascii=False)
            self.relay_manager.publish_message(message)
            return event.id
        else:
            return False

    def close(self):
        self.should_run = False
        self.relay_manager.close_connections()
