import sys
from functools import wraps

import bip39
import pydenticon
import validators
from flask import request, redirect, make_response, url_for
from flask_executor import Executor

from bija.app import app, socketio, ACTIVE_EVENTS
from bija.args import SETUP_PK, SETUP_PW, LOGGING_LEVEL
from bija.config import DEFAULT_RELAYS, default_settings
from bija.emojis import emojis
from bija.nip5 import Nip5
from bija.relay_handler import RelayHandler, MetadataEvent
from bija.helpers import *
from bija.jinja_filters import *
from bija.notes import FeedThread, NoteThread, BoostsThread
from bija.password import encrypt_key, decrypt_key
from bija.search import Search
from bija.settings import SETTINGS
from bija.submissions import SubmitDelete, SubmitNote, SubmitProfile, SubmitEncryptedMessage, SubmitLike, \
    SubmitFollowList

logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

DB = BijaDB(app.session)
# app.config['EXECUTOR_TYPE'] = 'process'
EXECUTOR = Executor(app)
RELAY_HANDLER = RelayHandler()

foreground = ["rgb(45,79,255)",
              "rgb(254,180,44)",
              "rgb(226,121,234)",
              "rgb(30,179,253)",
              "rgb(232,77,65)",
              "rgb(49,203,115)",
              "rgb(141,69,170)"]
background = "rgb(224,224,224)"
ident_im_gen = pydenticon.Generator(6, 6, foreground=foreground, background=background)


class LoginState(IntEnum):
    SETUP = 0
    LOGGED_IN = 2
    WITH_KEY = 3
    WITH_PASSWORD = 4
    SET_RELAYS = 5
    NEW_KEYS = 6


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        login_state = get_login_state()
        if login_state is not LoginState.LOGGED_IN:
            logger.info('Do login')
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/')
@login_required
def index_page():
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.set_page('home', None))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    pk = SETTINGS.get('pubkey')
    notes = DB.get_feed(time.time(), pk, {'main_feed': True})
    DB.set_all_seen_in_feed(pk)
    t = FeedThread(notes)
    EXECUTOR.submit(RELAY_HANDLER.subscribe_feed(list(t.ids)))
    profile = DB.get_profile(pk)
    topics = DB.get_topics()
    return render_template("feed.html", page_id="home", title="Home", threads=t.threads, last=t.last_ts,
                           profile=profile, pubkey=pk, topics=topics)


@app.route('/feed', methods=['GET'])
def feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        pk = SETTINGS.get('pubkey')
        notes = DB.get_feed(before, pk, {'main_feed': True})
        if len(notes) > 0:
            t = FeedThread(notes)
            EXECUTOR.submit(RELAY_HANDLER.subscribe_feed(list(t.ids)))
            profile = DB.get_profile(pk)
            return render_template("feed.items.html", threads=t.threads, last=t.last_ts, profile=profile, pubkey=pk)
        else:
            return 'END'


@app.route('/alerts', methods=['GET'])
@login_required
def alerts_page():
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.set_page('alerts', None))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    alerts = DB.get_alerts()
    DB.set_alerts_read()
    return render_template("alerts.html", page_id="alerts", title="alerts", alerts=alerts)


@app.route('/logout', methods=['GET'])
def logout_page():
    RELAY_HANDLER.close()
    sys.exit()


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    EXECUTOR.submit(RELAY_HANDLER.set_page('login', None))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    login_state = get_login_state()
    message = None
    data = None
    if request.method == 'POST':
        if process_login():
            has_relays = DB.get_preferred_relay()
            if SETTINGS.get('new_keys') is not None:
                login_state = LoginState.NEW_KEYS
                data = {
                    'npub': hex64_to_bech32("npub", SETTINGS.get('pubkey')),
                    'mnem': bip39.encode_bytes(bytes.fromhex(SETTINGS.get('privkey')))
                }
                SETTINGS.set('new_keys', None)
            elif has_relays is None:
                login_state = LoginState.SET_RELAYS
                data = DEFAULT_RELAYS
            else:
                EXECUTOR.submit(RELAY_HANDLER.subscribe_primary)
                EXECUTOR.submit(RELAY_HANDLER.run_loop)
                return redirect("/")
        else:
            message = "Incorrect key or password"
    return render_template("login.html",
                           page_id="login", title="Login",
                           stage=login_state, message=message, data=data, LoginState=LoginState)


@app.route('/profile', methods=['GET'])
@login_required
def profile_page():

    data = ProfilePage()

    if data.page == 'profile':
        return render_template(
            "profile/profile.html",
            page_id=data.page_id,
            title="Profile",
            threads=data.data.threads,
            last=data.data.last_ts,
            latest=data.latest_in_feed,
            profile=data.profile,
            is_me=data.is_me,
            am_following=data.am_following,
            meta=data.meta,
            pubkey=SETTINGS.get('pubkey'),
            website=data.website,
            has_ln=data.has_ln,
            n_following=data.following_count,
            n_followers=data.follower_count
        )
    else:
        return render_template(
            "profile/following.html",
            page_id=data.page_id,
            title="Contacts",
            profile=data.profile,
            profiles=data.data,
            is_me=data.is_me,
            meta=data.meta,
            am_following=data.am_following,
            website=data.website,
            has_ln=data.has_ln,
            n_following=data.following_count,
            n_followers=data.follower_count
        )

class ProfilePage:

    def __init__(self):
        self.page = 'profile'
        self.is_me = False
        self.am_following = False
        self.follower_count = 0
        self.following_count = 0
        self.has_ln = False
        self.website = None
        self.pubkey = self.set_pubkey()
        self.page_id = self.set_page_id()
        self.profile = None
        self.meta = None
        self.data = None
        self.latest_in_feed = None
        self.subscription_ids = [] # active notes to passed to subscription manager

        set_subscription = False
        valid_pages = ['profile', 'following', 'followers']

        ACTIVE_EVENTS.clear()
        if RELAY_HANDLER.page['page'] not in valid_pages or RELAY_HANDLER.page['identifier'] != self.pubkey:
            set_subscription = True
            EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
        EXECUTOR.submit(RELAY_HANDLER.set_page(self.page, self.pubkey))

        self.set_profile()
        self.set_contact_counts()
        self.set_meta()
        self.get_data()

        if set_subscription:
            EXECUTOR.submit(
                RELAY_HANDLER.subscribe_profile,
                self.pubkey,
                timestamp_minus(TimePeriod.WEEK),
                self.subscription_ids
            )

    def set_pubkey(self):
        if 'pk' in request.args and is_hex_key(request.args['pk']) and request.args['pk'] != SETTINGS.get('pubkey'):
            return request.args['pk']
        else:
            self.is_me = True
            return SETTINGS.get('pubkey')

    def set_page_id(self):
        if 'view' in request.args:
            self.page = request.args['view']
            return request.args['view']
        elif self.pubkey == SETTINGS.get('pubkey'):
            return 'profile-me'
        else:
            return 'profile'

    def set_profile(self):
        self.profile = DB.get_profile(self.pubkey)
        if self.profile is None:
            DB.add_profile(self.pubkey)
            self.profile = DB.get_profile(self.pubkey)

    def set_contact_counts(self):
        self.follower_count = DB.get_followers(SETTINGS.get('pubkey'), self.pubkey, True)
        self.following_count = DB.get_following(SETTINGS.get('pubkey'), self.pubkey, True)

    def set_meta(self):
        metadata = {}
        if self.profile.raw is not None and len(self.profile.raw) > 0:
            raw = json.loads(self.profile.raw)
            meta = json.loads(raw['content'])
            for item in meta.keys():
                val = str(meta[item]).strip()
                if item in ['lud06', 'lud16'] and len(val) > 0:
                    self.has_ln = True
                    metadata[item] = val
                elif item == 'website' and len(val) > 0 and validators.url(val):
                    self.website = val
                    metadata[item] = val
        self.meta = metadata

    def get_data(self):
        self.am_following = DB.a_follows_b(SETTINGS.get('pubkey'), self.pubkey)
        if self.page == 'profile':
            notes = DB.get_feed(int(time.time()), SETTINGS.get('pubkey'), {'profile': self.pubkey})
            self.data = FeedThread(notes)
            self.subscription_ids = list(self.data.ids)
            self.latest_in_feed = DB.get_most_recent_for_pk(self.pubkey) or 0
        elif self.page == 'following':
            self.data = DB.get_following(SETTINGS.get('pubkey'), self.pubkey)
        elif self.page == 'followers':
            self.data = DB.get_followers(SETTINGS.get('pubkey'), self.pubkey)


@app.route('/fetch_archived', methods=['GET'])
def fetch_archived():
    pk = request.args['pk']
    ts = int(request.args['ts'])
    tf = request.args['tf']
    timeframe = TimePeriod.DAY
    tx = 1
    if tf == 'w':
        timeframe = TimePeriod.WEEK
        tx = 1
    elif tf == 'm':
        timeframe = TimePeriod.DAY
        tx = 30
    elif tf == 'y':
        timeframe = TimePeriod.WEEK
        tx = 52
    elif tf == 'a':
        timeframe = TimePeriod.WEEK
        tx = 10000

    EXECUTOR.submit(
        RELAY_HANDLER.subscribe_profile,
        pk,
        timestamp_minus(timeframe, tx, ts),
        []
    )
    return render_template("upd.json", data=json.dumps({'success': 1}))

@app.route('/get_profile_sharer', methods=['GET'])
def get_profile_sharer():
    pk = request.args['pk']
    return render_template("profile/profile.sharer.html", hex=pk, bech32=hex64_to_bech32("npub", pk))

@app.route('/get_ln_details', methods=['GET'])
def get_ln_details():
    pk = request.args['pk']
    profile = DB.get_profile(pk)
    d = json.loads(profile.raw)

    return render_template("profile/profile.lightning.html", data=json.loads(d['content']), name=profile.name)

@app.route('/get_share', methods=['GET'])
def get_share():
    note_id = request.args['id']
    k = hex64_to_bech32('note', note_id)
    return render_template("share.popup.html", key=k)


@app.route('/mark_read', methods=['GET'])
def mark_read():
    DB.set_all_messages_read()
    return render_template("upd.json", title="Home", data=json.dumps({'success':1}))


@app.route('/profile_feed', methods=['GET'])
def profile_feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        pk = SETTINGS.get('pubkey')
        notes = DB.get_feed(before, pk, {'profile': request.args['pk']})
        if len(notes) > 0:
            t = FeedThread(notes)
            profile = DB.get_profile(pk)
            EXECUTOR.submit(
                RELAY_HANDLER.subscribe_profile, request.args['pk'], t.last_ts - TimePeriod.WEEK, list(t.ids)
            )
            return render_template("feed.items.html", threads=t.threads, last=t.last_ts, profile=profile,
                                   pubkey=SETTINGS.get('pubkey'))
        else:
            return 'END'


@app.route('/note', methods=['GET'])
@login_required
def note_page():
    ACTIVE_EVENTS.clear()
    note_id = request.args['id']
    EXECUTOR.submit(RELAY_HANDLER.set_page('note', note_id))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)

    t = NoteThread(note_id)
    EXECUTOR.submit(RELAY_HANDLER.subscribe_thread, note_id, t.note_ids)

    profile = DB.get_profile(SETTINGS.get('pubkey'))
    return render_template("thread.html",
                           page_id="note",
                           title="Note",
                           notes=t.result_set,
                           members=t.profiles,
                           profile=profile,
                           root=note_id, pubkey=SETTINGS.get('pubkey'))

@app.route('/boosts', methods=['GET'])
@login_required
def boosts_page():
    ACTIVE_EVENTS.clear()
    note_id = request.args['id']
    EXECUTOR.submit(RELAY_HANDLER.set_page('boosts', note_id))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)

    t = BoostsThread(note_id)

    profile = DB.get_profile(SETTINGS.get('pubkey'))
    return render_template("boosts.html",
                           page_id="boosts",
                           title="Boosts",
                           notes=t.boosts,
                           profile=profile,
                           root=note_id, pubkey=SETTINGS.get('pubkey'))


@app.route('/quote_form', methods=['GET'])
def quote_form():
    note_id = request.args['id']
    note = DB.get_note(SETTINGS.get('pubkey'), note_id)
    profile = DB.get_profile(SETTINGS.get('pubkey'))
    return render_template("quote.form.html", item=note, id=note_id, profile=profile)


@app.route('/confirm_delete', methods=['GET'])
def confirm_delete():
    note_id = request.args['id']
    return render_template("delete.confirm.html", id=note_id, )


@app.route('/delete_note', methods=['POST'])
def delete_note():
    note_id = None
    reason = None
    event_id = None
    for r in request.json:
        if r[0] == 'note_id':
            note_id = r[1]
        elif r[0] == 'reason':
            reason = r[1]
    if note_id is not None:
        e = SubmitDelete([note_id], reason)
        event_id = e.event_id
        #event_id = EVENT_HANDLER.submit_delete([note_id], reason)
    return render_template("upd.json", data=json.dumps({'event_id': event_id}))


@app.route('/quote', methods=['POST'])
def quote_submit():
    out = {}
    if request.method == 'POST':
        data = {}
        for v in request.json:
            data[v[0]] = v[1]
        note = DB.get_note(SETTINGS.get('pubkey'), data['quote_id'])
        if note:
            members = json.loads(note.members)
            if note.public_key not in members:
                members.insert(0, note.public_key)
            if 'quote_id' not in data:
                out['error'] = 'Nothing to quote'
            else:
                pow_difficulty = SETTINGS.get('pow_default')
                e = SubmitNote(data, members, pow_difficulty)
                #event_id = EVENT_HANDLER.submit_note(data, members, pow_difficulty=pow_difficulty)
                out['event_id'] = e.event_id
        else:
            out['error'] = 'Quoted note not found at DB'
    return render_template("upd.json", title="Home", data=json.dumps(out))


@app.route('/thread_item', methods=['GET'])
def thread_item():
    note_id = request.args['id']
    note = DB.get_note(SETTINGS.get('pubkey'), note_id)
    profile = DB.get_profile(SETTINGS.get('pubkey'))
    return render_template("thread.item.html", item=note, profile=profile)


@app.route('/read_more', methods=['GET'])
def read_more():
    note_id = request.args['id']
    note = DB.get_note(SETTINGS.get('pubkey'), note_id)
    return render_template("note.content.html", note=note)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    ACTIVE_EVENTS.clear()
    if request.method == 'POST' and 'del_keys' in request.form.keys():
        print("RESET DB")
        RELAY_HANDLER.close()
        DB.reset()
        return redirect('/')
    else:
        EXECUTOR.submit(RELAY_HANDLER.set_page('settings', None))
        EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
        settings = SETTINGS.get_list([
            'cloudinary_cloud',
            'cloudinary_upload_preset',
            'pow_default',
            'pow_default_enc',
            'pow_required',
            'pow_required_enc'])

        relays = DB.get_relays()
        EXECUTOR.submit(RELAY_HANDLER.get_connection_status())
        pubkey = SETTINGS.get("pubkey")
        privkey = SETTINGS.get("privkey")
        keys = {
            "private": [
                privkey,
                hex64_to_bech32("nsec", privkey),
                bip39.encode_bytes(bytes.fromhex(privkey))
            ],
            "public": [
                pubkey,
                hex64_to_bech32("npub", pubkey)
            ]
        }
        themes = DB.get_themes()
        theme = SETTINGS.get('theme')

        theme_settings = SETTINGS.get_list([
            'spacing',
            'fs-base',
            'rnd',
            'icon',
            'pfp-dim'])

        return render_template(
            "settings.html",
            page_id="settings",
            title="Settings", relays=relays, settings=settings, k=keys, theme=theme, themes=themes, theme_settings=theme_settings)


@app.route('/update_settings', methods=['POST'])
def update_settings():
    for item in request.json:
        SETTINGS.set(item[0], item[1].strip())
    config_backup()
    return render_template("upd.json", data=json.dumps({'success': 1}))


@app.route('/default_styles', methods=['GET'])
def default_styles():
    defaults = default_settings
    vs = ['spacing','fs-base','rnd','icon','pfp-dim']
    for k in defaults:
        if k in vs:
            SETTINGS.set(k, defaults[k])
    return render_template("upd.json", data=json.dumps({'success': 1}))

def config_backup():
    topics = DB.get_topics()

    data = {
        'settings': DB.get_settings(),
        'topics': [x.tag for x in topics]
    }
    SubmitEncryptedMessage([
        ('new_message', '::BIJA_CFG_BACKUP::{}'.format(json.dumps(data))),
        ('new_message_pk', SETTINGS.get('pubkey'))
    ])

@app.route('/load_cfg', methods=['POST'])
def load_cfg():
    if len(request.json) > 0 and request.json[0][0] == 'cfg':
        data = json.loads(request.json[0][1])
        DB.upd_settings_by_keys(data['settings'])
        SETTINGS.set_from_db()
        DB.empty_topics()
        for t in data['topics']:
            DB.subscribe_to_topic(t)

    return render_template("upd.json", data=json.dumps({'success': 1}))

@app.route('/reload_relay_list', methods=['GET'])
def reload_relay_list():
    relays = DB.get_relays()
    return render_template("relays.list.html", relays=relays)


@app.route('/destroy_account')
def destroy_account():
    RELAY_HANDLER.close()
    DB.reset()
    if os.path.exists("bija.sqlite"):
        os.remove("bija.sqlite")
    return render_template("restart.html")


@app.route('/upd_profile', methods=['POST', 'GET'])
def update_profile():
    out = {'success': False}
    if request.method == 'POST':
        profile = {}
        for item in request.json:
            valid_vals = ['name', 'display_name', 'about', 'picture', 'nip05', 'website', 'lud06', 'lud16']
            if item[0] in valid_vals and len(item[1].strip()) > 0:
                profile[item[0]] = item[1].strip()
        if 'nip05' in profile and len(profile['nip05']) > 0:
            nip5 = Nip5(profile['nip05'])
            valid_nip5 = nip5.match(SETTINGS.get('pubkey'))
            out['nip05'] = valid_nip5
            if valid_nip5:
                e = SubmitProfile(profile)
                out['success'] = e.event_id
        else:
            e = SubmitProfile(profile)
            out['success'] = e.event_id
    return render_template("upd.json", data=json.dumps(out))


@app.route('/add_relay', methods=['POST', 'GET'])
def add_relay():
    success = False
    if request.method == 'POST':
        for item in request.json:
            ws = item[1].strip()
            if item[0] == 'newrelay' and is_valid_relay(ws):
                success = True
                DB.insert_relay(ws)
                EXECUTOR.submit(RELAY_HANDLER.add_relay(ws))
                EXECUTOR.submit(RELAY_HANDLER.reset)
    return render_template("upd.json", data=json.dumps({'add_relay': success}))


@app.route('/reset_relays', methods=['POST', 'GET'])
def reset_relays():
    EXECUTOR.submit(RELAY_HANDLER.reset)
    return render_template("upd.json", data=json.dumps({'reset_relays': True}))


@app.route('/validate_nip5', methods=['GET'])
def validate_nip5():
    profile = DB.get_profile(request.args['pk'])
    nip5 = Nip5(profile.nip05)
    match = nip5.match(profile.public_key)
    DB.set_valid_nip05(profile.public_key, match)
    return render_template("upd.json", data=json.dumps({'valid': match}))


@app.route('/messages', methods=['GET'])
@login_required
def private_messages_page():
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.set_page('messages', None))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)

    messages = DB.get_message_list()

    return render_template("messages.html", page_id="messages", title="Private Messages", messages=messages)


@app.route('/message', methods=['GET'])
@login_required
def private_message_page():
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.set_page('message', request.args['pk']))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    messages = []
    pk = ''
    if 'pk' in request.args and is_hex_key(request.args['pk']):
        messages = DB.get_message_thread(request.args['pk'])
        pk = request.args['pk']

    profile = DB.get_profile(SETTINGS.get('pubkey'))
    them = DB.get_profile(pk)

    messages.reverse()

    return render_template("message_thread.html", page_id="messages_from", title="Messages From", messages=messages,
                           me=profile, them=them, privkey=SETTINGS.get('privkey'))


@app.route('/submit_message', methods=['POST', 'GET'])
def submit_message():
    event_id = False
    if request.method == 'POST':
        pow_difficulty = SETTINGS.get('pow_default_enc')
        e = SubmitEncryptedMessage(request.json, pow_difficulty)
        event_id = e.event_id
        #event_id = EVENT_HANDLER.submit_message(request.json, pow_difficulty=pow_difficulty)
    return render_template("upd.json", title="Home", data=json.dumps({'event_id': event_id}))


@app.route('/like', methods=['GET'])
def submit_like():
    if 'id' in request.args:
        note_id = request.args['id']
        note = DB.get_note(SETTINGS.get('pubkey'), note_id)
        if note.liked is False:
            DB.set_note_liked(note_id)
            e = SubmitLike(note_id)
            return render_template('svg/liked.svg', class_name='icon liked')
        else:
            DB.set_note_liked(note_id, False)
            like_events = DB.get_like_events_for(note_id, SETTINGS.get('pubkey'))
            if like_events is not None:
                ids = []
                for event in like_events:
                    ids.append(event.id)
                e = SubmitDelete(ids, 'removing like')
                return render_template('svg/like.svg', class_name='icon')


@app.route('/search', methods=['GET'])
@login_required
def search_page():
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.set_page('search', request.args['search_term']))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    search = Search()
    results, goto, message, action = search.get()
    if goto is not None:
        return redirect(goto)
    if action is not None:
        if action == 'hash':
            EXECUTOR.submit(RELAY_HANDLER.subscribe_topic, request.args['search_term'][1:])
    return re


@app.route('/topic', methods=['GET'])
@login_required
def topic_page():
    ACTIVE_EVENTS.clear()
    topic = request.args['tag']
    EXECUTOR.submit(RELAY_HANDLER.set_page('topic', topic))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    EXECUTOR.submit(RELAY_HANDLER.subscribe_topic, topic)
    pk = SETTINGS.get('pubkey')

    notes = DB.get_feed(int(time.time()), pk, {'topic':topic})
    DB.set_all_seen_in_topic(topic)

    t = FeedThread(notes)
    profile = DB.get_profile(pk)

    subscribed = DB.subscribed_to_topic(topic)
    topics = DB.get_topics()

    return render_template("topic.html", page_id="topic", title="Topic", threads=t.threads, last=t.last_ts,
                           profile=profile, pubkey=pk, topic=topic, subscribed=int(subscribed), topics=topics)

@app.route('/topic_feed', methods=['GET'])
def topic_feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        pk = SETTINGS.get('pubkey')
        notes = DB.get_feed(before, pk, {'topic':request.args['topic']})
        if len(notes) > 0:
            t = FeedThread(notes)
            profile = DB.get_profile(pk)
            return render_template("feed.items.html", threads=t.threads, last=t.last_ts, profile=profile, pubkey=pk)
        else:
            return 'END'

@app.route('/subscribe_topic', methods=['GET'])
def subscribe_topic():
    if request.args['state'] == '0':
        DB.subscribe_to_topic(str(request.args['topic']).lower())
        out = {'state': '1', 'label': 'unsubscribe'}
    else:
        DB.unsubscribe_from_topic(str(request.args['topic']))
        out = {'state': '0', 'label': 'subscribe'}
    config_backup()
    return render_template("upd.json", data=json.dumps(out))


@app.route('/search_name', methods=['GET'])
def search_name():
    out = {}
    matches = DB.search_profile_name(request.args['name'])
    if matches is not None:
        out = [dict(row) for row in matches]
    return render_template("upd.json", data=json.dumps({'result': out}))


@app.route('/get_privkey', methods=['GET', 'POST'])
def get_privkey():
    passed = False
    pk = DB.get_saved_pk()
    keys = None
    if pk.enc == 0:
        passed = True
    elif request.method == 'POST' and pk.enc == 1:
        for item in request.json:
            if item[0] == 'pw':
                k = decrypt_key(item[1], pk.key)
                if k == SETTINGS.get('privkey'):
                    passed = True
    if passed:
        k = SETTINGS.get("privkey")
        keys = {
            "private": [
                k,
                hex64_to_bech32("nsec", k),
                bip39.encode_bytes(bytes.fromhex(k))
            ]
        }
    return render_template("privkey.html", passed=passed, k=keys)


@app.route('/identicon', methods=['GET'])
def identicon():
    im = ident_im_gen.generate(request.args['id'], 120, 120, padding=(10, 10, 10, 10), output_format="png")
    response = make_response(im)
    response.headers.set('Content-Type', 'image/png')
    return response


@app.route('/emojis', methods=['GET'])
def emojis_req():
    d = {
        'emojis': [],
        'categories': []
    }
    if 's' in request.args and len(request.args['s'].strip()) > 0:
        data = emojis
        n = 0
        for cat in data:
            d['categories'].append(cat['name'])
            for item in cat['emojis']:
                if n < 50 and request.args['s'] in item['name']:
                    d['emojis'].append(item['emoji'])
                    n += 1
    else:
        d = {
            'emojis': json.loads(SETTINGS.get('recent_emojis'))
        }
    return render_template("upd.json", data=json.dumps(d))

@app.route('/recent_emojis', methods=['GET'])
def recent_emojis():
    emoji = request.args['s']
    recent = SETTINGS.get('recent_emojis')
    emojis = json.loads(recent)
    if emoji in emojis:
        emojis.remove(emoji)
    emojis.insert(0, emoji)
    if len(emojis) > 8:
        emojis.pop()
    SETTINGS.set('recent_emojis', json.dumps(emojis))
    return '1'

@socketio.on('connect')
def io_connect(m):
    unseen_messages = DB.get_unseen_message_count()
    if unseen_messages > 0:
        socketio.emit('unseen_messages_n', unseen_messages)

    unseen_posts = DB.get_unseen_in_feed(SETTINGS.get('pubkey'))
    if unseen_posts > 0:
        socketio.emit('unseen_posts_n', unseen_posts)

    unseen_alerts = DB.get_unread_alert_count()
    socketio.emit('alert_n', unseen_alerts)

    topics = DB.get_topics()
    if topics is not None:
        t = [x.tag for x in topics]
        unseen_in_topics = DB.get_unseen_in_topics(t)
        if unseen_in_topics is not None:
            socketio.emit('unseen_in_topics', unseen_in_topics)

    EXECUTOR.submit(RELAY_HANDLER.get_connection_status)


@app.route('/refresh_connections', methods=['GET'])
def refresh_connections():
    EXECUTOR.submit(EXECUTOR.submit(RELAY_HANDLER.reset()))
    return render_template("upd.json", data=json.dumps({'reset': True}))


@app.route('/del_relay', methods=['GET'])
def del_relay():
    DB.remove_relay(request.args['url'])
    EXECUTOR.submit(RELAY_HANDLER.remove_relay(request.args['url']))
    EXECUTOR.submit(RELAY_HANDLER.reset)
    return render_template("upd.json", data=json.dumps({'del': True}))


@app.route('/follow', methods=['GET'])
def follow():
    DB.set_following(SETTINGS.get('pubkey'), request.args['id'], int(request.args['state']))

    EXECUTOR.submit(SubmitFollowList())
    profile = DB.get_profile(request.args['id'])
    is_me = request.args['id'] == SETTINGS.get('pubkey')
    upd = request.args['upd']
    if upd == "1":
        return render_template("profile/profile.tools.html", profile=profile, is_me=is_me, am_following=int(request.args['state']))
    else:
        return render_template("svg/following.svg", class_name="icon")


@app.route('/fetch_raw', methods=['GET'])
def fetch_raw():
    d = DB.get_raw_note_data(request.args['id'])
    return render_template("upd.json", data=json.dumps({'data': d.raw}))


@app.route('/get_reactions', methods=['GET'])
def get_reactions():
    d = DB.get_note_reactions(request.args['id'])
    results = []
    for r in d:
        r = dict(r)
        results.append(r)
    return render_template("upd.json", data=json.dumps({'data': results}))


@app.route('/timestamp_upd', methods=['GET'])
def timestamp_upd():
    t = request.args['ts'].split(',')
    results = {}
    for ts in t:
        dt = arrow.get(int(ts))
        results[ts] = dt.humanize()
    return render_template("upd.json", data=json.dumps({'data': results}))


@app.route('/submit_note', methods=['POST', 'GET'])
def submit_note():
    out = {}
    if request.method == 'POST':
        data = {}
        for v in request.json:
            data[v[0]] = v[1]
        if 'reply' not in data and 'new_post' not in data:
            out['error'] = 'Invalid message'
        elif 'reply' in data and len(data['reply']) < 1:
            out['error'] = 'Invalid or empty message'
        elif 'new_post' in data and len(data['new_post']) < 1:
            out['error'] = 'Invalid or empty message'
        elif 'reply' in data and 'parent_id' not in data:
            out['error'] = 'No parent id identified for response'
        else:
            members = []
            if 'parent_id' in data:
                note = DB.get_note(SETTINGS.get('pubkey'), data['parent_id'])
                if note:
                    members = json.loads(note.members)
                    if note.public_key not in members:
                        members.insert(0, note.public_key)
            pow_difficulty = SETTINGS.get('pow_default')
            e = SubmitNote(data, members, pow_difficulty)
            event_id = e.event_id
            # event_id = EVENT_HANDLER.submit_note(data, members, pow_difficulty=pow_difficulty)
            if 'thread_root' in data:
                out['root'] = data['thread_root']
            else:
                out['root'] = event_id
            out['event_id'] = event_id
    return render_template("upd.json", title="Home", data=json.dumps(out))


@app.teardown_appcontext
def remove_session(*args, **kwargs):
    app.session.remove()


@app.get('/shutdown')
def shutdown():
    RELAY_HANDLER.close()
    quit()


def get_login_state():
    logger.info('Getting login state')
    if SETUP_PK is not None and SETTINGS.get("privkey") is None:
        logger.info('New setup detected')
        DB.save_pk(encrypt_key(SETUP_PW, SETUP_PK), 1)
        redirect('/login')
    if SETTINGS.get("privkey") is not None:
        logger.info('Has session keys, is logged in {}'.format(SETTINGS.get('pubkey')))
        return LoginState.LOGGED_IN
    saved_pk = DB.get_saved_pk()
    if saved_pk is not None:
        logger.info('Has saved private key, use it to log in')
        if saved_pk.enc == 0:
            set_keypair(saved_pk.key)
            EXECUTOR.submit(RELAY_HANDLER.subscribe_primary)
            EXECUTOR.submit(RELAY_HANDLER.run_loop)
            return LoginState.LOGGED_IN
        else:
            return LoginState.WITH_PASSWORD
    return LoginState.SETUP


def process_login():
    if 'confirm_new_keys' in request.form.keys():
        return True
    elif 'login' in request.form.keys():
        saved_pk = DB.get_saved_pk()
        k = decrypt_key(request.form['pw'].strip(), saved_pk.key)
        if k and is_hex_key(k):
            set_keypair(k)
            return True
        else:
            return False

    elif 'load_private_key' in request.form.keys():
        if len(request.form['mnemonic'].strip()) > 0:
            if len(request.form['mnemonic'].split()) == 24 and bip39.check_phrase(request.form['mnemonic']):
                private_key = bip39.decode_phrase(request.form['mnemonic']).hex()
            else:
                return False
        elif len(request.form['private_key'].strip()) < 1:  # generate a new key
            private_key = None
            SETTINGS.set("new_keys", True)
        elif is_hex_key(request.form['private_key'].strip()):
            private_key = request.form['private_key'].strip()
        elif is_bech32_key('nsec', request.form['private_key'].strip()):
            private_key = bech32_to_hex64('nsec', request.form['private_key'].strip())
            if not private_key:
                return False
        else:
            return False
        set_keypair(private_key)
        return True

    elif 'add_relays' in request.form.keys():
        added = False
        for item in request.form.getlist('relay'):
            DB.insert_relay(item)
            added = True
        if 'custom_relay' in request.form.keys() and len(request.form['custom_relay'].strip()) > 0:
            DB.insert_relay(request.form['custom_relay'])
            added = True
        RELAY_HANDLER.open_connections()
        time.sleep(1)
        return added


def process_key_save(pk):
    if 'password' in request.form.keys():
        pw = request.form['password'].strip()
        enc = 0
        if len(pw) > 0:
            pk = encrypt_key(pw, pk)
            enc = 1
        DB.save_pk(pk, enc)


def set_keypair(k):
    global KEYS
    if k is None:
        pk = PrivateKey()
    else:
        pk = PrivateKey(bytes.fromhex(k))
    private_key = pk.hex()
    public_key = pk.public_key.hex()
    SETTINGS.set('pubkey', public_key, False)
    SETTINGS.set('privkey', private_key, False)
    process_key_save(private_key)
    if DB.get_profile(public_key) is None:
        DB.add_profile(public_key)


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
