import json
import logging

import validators as validators

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import get_embeded_tag_indexes, \
    list_index_exists, get_urls_in_string, url_linkify, strip_tags, is_nip05, \
    request_url_head, is_hex_key
from bija.settings import SETTINGS
from bija.ws.event import EventKind
from bija.ws.key import PrivateKey
from bija.ws.pow import count_leading_zero_bits

logger = logging.getLogger(__name__)
FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(format=FORMAT)
logger.setLevel(LOGGING_LEVEL)

DB = BijaDB(app.session)


class NoteEvent:
    def __init__(self, event, my_pk, subscription):
        logger.info('New note')
        self.event = event
        self.subscription = subscription
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
        self.fetch_og = None

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
                    if ct in ['image/apng', 'image/png', 'image/avif', 'image/gif', 'image/jpeg', 'image/svg+xml',
                              'image/webp']:
                        logger.info('{} is image'.format(url))
                        self.media.append((url, 'image'))
                    elif ct in ["video/webm", "video/ogg", "video/mp4"]:
                        logger.info('{} is vid'.format(url))
                        ext = ct.split('/')
                        self.media.append((url, 'video', ext[1]))

        if len(self.media) < 1 and len(urls) > 0:
            logger.info('note has urls')
            if validators.url(urls[0]):
                logger.info('add {} to tasks for scraping'.format(urls[0]))
                self.fetch_og = urls[0]
                # D_TASKS.pool.add(TaskKind.FETCH_OG, {'url': urls[0], 'note_id': self.event.id})

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
        seen = False
        if 'profile' in self.subscription :
            seen = True
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
            'seen': seen,
            'raw': json.dumps(self.event.to_json_object())
        }

class BoostEvent:
    def __init__(self, event):
        logger.info('New boost')
        self.event = event
        self.reshare_id = None
        self.get_boosted_event()
        self.note_content = event.content

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
            'raw': json.dumps(self.event.to_json_object())
        }

class BlockListEvent:
    def __init__(self, event):
        self.event = event
        self.list = []
        self.set_list()

    def set_list(self):
        k = bytes.fromhex(SETTINGS.get('privkey'))
        pk = PrivateKey(k)
        raw = pk.decrypt_message(self.event.content, SETTINGS.get('pubkey'))
        try:
            self.list = json.loads(raw)
        except ValueError:
            print("unable to decode json")

class PersonListEvent:
    def __init__(self, event):
        self.event = event
        self.list = []
        self.name = None
        self.set_list()
        self.get_name()
        if self.name is not None and len(self.list) > 0:
            self.save()

    def set_list(self):
        k = bytes.fromhex(SETTINGS.get('privkey'))
        pk = PrivateKey(k)
        raw = pk.decrypt_message(self.event.content, SETTINGS.get('pubkey'))
        try:
            self.list = json.loads(raw)
        except ValueError:
            print("unable to decode json")

    def get_name(self):
        for tag in self.event.tags:
            if tag[0] == "d":
                self.name = tag[1]

    def save(self):
        DB.save_list(self.name, self.event.public_key, json.dumps(self.list))

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
    def __init__(self, event):
        self.event = event
        self.keys = []
        self.compile_keys()

    def compile_keys(self):
        for p in self.event.tags:
            if p[0] == "p":
                self.keys.append(p[1])

class FollowerListEvent:
    def __init__(self, event, subscription: str):
        self.event = event
        self.subscription = subscription
        self.action = 'del'
        self.target_pk = None
        self.get_target()
        if self.target_pk is not None:
            self.get_action()

    def get_action(self):
        for p in self.event.tags:
            if p[0] == "p" and p[1] == self.target_pk:
                self.action = 'add'

    def get_target(self):
        parts = self.subscription.split(':')
        if len(parts) > 1:
            p = DB.get_profile_by_id(parts[1])
            if p is not None:
                self.target_pk = p.public_key

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
            elif DB.inbox_allowed(self.pubkey):
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
            "passed": self.passed,
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
        s = {}
        try:
            s = json.loads(self.event.content)
        except ValueError as e:
            self.success = False
        if self.success:
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
            # D_TASKS.pool.add(TaskKind.VALIDATE_NIP5, {'pk': self.event.public_key})

    def to_dict(self):
        return {
            'public_key': self.event.public_key,
            'name': self.name,
            'display_name': self.display_name,
            'nip05': self.nip05,
            'pic': self.picture,
            'about': self.about,
            'updated_at': self.event.created_at,
            'raw': json.dumps(self.event.to_json_object())
        }


