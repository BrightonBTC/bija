import sys
from functools import wraps

import bip39
import pydenticon
from flask import request, redirect, make_response, url_for
from flask_executor import Executor

from bija.app import app, socketio, ACTIVE_EVENTS
from bija.args import SETUP_PK, SETUP_PW, LOGGING_LEVEL
from bija.config import DEFAULT_RELAYS
from bija.emojis import emojis
from bija.relay_handler import RelayHandler, MetadataEvent
from bija.helpers import *
from bija.jinja_filters import *
from bija.notes import FeedThread, NoteThread
from bija.password import encrypt_key, decrypt_key
from bija.search import Search
from bija.settings import Settings
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
    pk = Settings.get('pubkey')
    DB.set_all_seen_in_feed(pk)
    notes = DB.get_feed(time.time(), pk)
    t = FeedThread(notes)
    EXECUTOR.submit(RELAY_HANDLER.subscribe_feed(list(t.ids)))
    profile = DB.get_profile(pk)
    return render_template("feed.html", page_id="home", title="Home", threads=t.threads, last=t.last_ts,
                           profile=profile, pubkey=pk)


@app.route('/feed', methods=['GET'])
def feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        pk = Settings.get('pubkey')
        notes = DB.get_feed(before, pk)
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
            if Settings.get('new_keys') is not None:
                login_state = LoginState.NEW_KEYS
                data = {
                    'npub': hex64_to_bech32("npub", Settings.get('pubkey')),
                    'mnem': bip39.encode_bytes(bytes.fromhex(Settings.get('privkey')))
                }
                Settings.set('new_keys', None)
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
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    page_id = 'profile'
    if 'pk' in request.args and is_hex_key(request.args['pk']) and request.args['pk'] != Settings.get('pubkey'):
        EXECUTOR.submit(RELAY_HANDLER.set_page('profile', request.args['pk']))
        k = request.args['pk']
        is_me = False
    else:
        k = Settings.get('pubkey')
        EXECUTOR.submit(RELAY_HANDLER.set_page('profile', k))
        is_me = True
        page_id = 'profile-me'
    notes = DB.get_notes_by_pubkey(k, int(time.time()), timestamp_minus(TimePeriod.DAY))
    t = FeedThread(notes)
    profile = DB.get_profile(k)
    latest = DB.get_most_recent_for_pk(k)
    if latest is None:
        latest = 0
    if profile is None:
        DB.add_profile(k)
        profile = DB.get_profile(k)

    EXECUTOR.submit(RELAY_HANDLER.subscribe_profile, k, timestamp_minus(TimePeriod.WEEK), list(t.ids))

    metadata = {}
    if profile.raw is not None and len(profile.raw) > 0:
        raw = json.loads(profile.raw)
        meta = json.loads(raw['content'])
        for item in meta.keys():
            if item in ['website', 'lud06', 'lud16']:
                metadata[item] = meta[item]
    return render_template(
        "profile.html",
        page_id=page_id,
        title="Profile",
        threads=t.threads,
        last=t.last_ts,
        latest=latest,
        profile=profile,
        is_me=is_me,
        meta=metadata,
        pubkey=get_key(),
    )


@app.route('/profile_feed', methods=['GET'])
def profile_feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        notes = DB.get_notes_by_pubkey(request.args['pk'], before, None)
        if len(notes) > 0:
            t = FeedThread(notes)
            profile = DB.get_profile(Settings.get('pubkey'))
            EXECUTOR.submit(
                RELAY_HANDLER.subscribe_profile, request.args['pk'], t.last_ts - TimePeriod.WEEK, list(t.ids)
            )
            return render_template("feed.items.html", threads=t.threads, last=t.last_ts, profile=profile,
                                   pubkey=Settings.get('pubkey'))
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

    profile = DB.get_profile(Settings.get('pubkey'))
    return render_template("thread.html",
                           page_id="note",
                           title="Note",
                           notes=t.result_set,
                           members=t.profiles,
                           profile=profile,
                           root=note_id, pubkey=Settings.get('pubkey'))


@app.route('/quote_form', methods=['GET'])
def quote_form():
    note_id = request.args['id']
    note = DB.get_note(note_id)
    profile = DB.get_profile(Settings.get('pubkey'))
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
        note = DB.get_note(data['quote_id'])
        if note:
            members = json.loads(note.members)
            if note.public_key not in members:
                members.insert(0, note.public_key)
            if 'quote_id' not in data:
                out['error'] = 'Nothing to quote'
            else:
                pow_difficulty = Settings.get('pow_default')
                e = SubmitNote(data, members, pow_difficulty)
                #event_id = EVENT_HANDLER.submit_note(data, members, pow_difficulty=pow_difficulty)
                out['event_id'] = e.event_id
        else:
            out['error'] = 'Quoted note not found at DB'
    return render_template("upd.json", title="Home", data=json.dumps(out))


@app.route('/thread_item', methods=['GET'])
def thread_item():
    note_id = request.args['id']
    note = DB.get_note(note_id)
    profile = DB.get_profile(Settings.get('pubkey'))
    return render_template("thread.item.html", item=note, profile=profile)


@app.route('/read_more', methods=['GET'])
def read_more():
    note_id = request.args['id']
    note = DB.get_note(note_id)
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
        settings = {
            'cloudinary_cloud': '',
            'cloudinary_upload_preset': '',
            'pow_default': '',
            'pow_default_enc': '',
            'pow_required': '',
            'pow_required_enc': ''
        }
        cs = DB.get_settings_by_keys([
            'cloudinary_cloud',
            'cloudinary_upload_preset',
            'pow_default',
            'pow_default_enc',
            'pow_required',
            'pow_required_enc'])
        if cs is not None:
            for item in cs:
                item = dict(item)
                settings[item['key']] = item['value']

        relays = DB.get_relays()
        EXECUTOR.submit(RELAY_HANDLER.get_connection_status())
        pubkey = Settings.get("pubkey")
        privkey = Settings.get("privkey")
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
        return render_template(
            "settings.html",
            page_id="settings",
            title="Settings", relays=relays, settings=settings, k=keys)


@app.route('/update_settings', methods=['POST'])
def update_settings():
    items = {}
    for item in request.json:
        items[item[0]] = item[1].strip()
    DB.upd_settings_by_keys(items)
    Settings.set_from_db()
    return render_template("upd.json", data=json.dumps({'success': 1}))


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
            valid_vals = ['name', 'about', 'picture', 'nip05', 'website', 'lud06', 'lud16']
            if item[0] in valid_vals and len(item[1].strip()) > 0:
                profile[item[0]] = item[1].strip()
        if 'nip05' in profile and len(profile['nip05']) > 0:
            valid_nip5 = MetadataEvent.validate_nip05(profile['nip05'], Settings.get('pubkey'))
            out['nip05'] = valid_nip5
            if valid_nip5:
                e = SubmitProfile(profile)
                out['success'] = e.event_id
                #out['success'] = EVENT_HANDLER.submit_profile(profile)
        else:
            e = SubmitProfile(profile)
            out['success'] = e.event_id
            #out['success'] = EVENT_HANDLER.submit_profile(profile)
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
    return render_template("upd.json", data=json.dumps({'add_relay': success}))


@app.route('/reset_relays', methods=['POST', 'GET'])
def reset_relays():
    EXECUTOR.submit(RELAY_HANDLER.reset)
    return render_template("upd.json", data=json.dumps({'reset_relays': True}))


@app.route('/validate_nip5', methods=['GET'])
def validate_nip5():
    profile = DB.get_profile(request.args['pk'])
    valid_nip5 = MetadataEvent.validate_nip05(profile.nip05, profile.public_key)
    if valid_nip5:
        DB.set_valid_nip05(profile.public_key)
    return render_template("upd.json", data=json.dumps({'valid': valid_nip5}))


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

    profile = DB.get_profile(Settings.get('pubkey'))
    them = DB.get_profile(pk)

    messages.reverse()

    return render_template("message_thread.html", page_id="messages_from", title="Messages From", messages=messages,
                           me=profile, them=them, privkey=Settings.get('privkey'))


@app.route('/submit_message', methods=['POST', 'GET'])
def submit_message():
    event_id = False
    if request.method == 'POST':
        pow_difficulty = Settings.get('pow_default_enc')
        e = SubmitEncryptedMessage(request.json, pow_difficulty)
        event_id = e.event_id
        #event_id = EVENT_HANDLER.submit_message(request.json, pow_difficulty=pow_difficulty)
    return render_template("upd.json", title="Home", data=json.dumps({'event_id': event_id}))


@app.route('/like', methods=['GET'])
def submit_like():
    event_id = False
    if 'id' in request.args:
        note_id = request.args['id']
        note = DB.get_note(note_id)
        if note.liked is False:
            DB.set_note_liked(note_id)
            e = SubmitLike(note_id)
            event_id = e.event_id
            #event_id = EVENT_HANDLER.submit_like(note_id)
        else:
            DB.set_note_liked(note_id, False)
            like_events = DB.get_like_events_for(note_id, Settings.get('pubkey'))
            if like_events is not None:
                ids = []
                for event in like_events:
                    ids.append(event.id)
                e = SubmitDelete(ids, 'removing like')
                event_id = e.event_id
                #event_id = EVENT_HANDLER.submit_delete(ids)

    return render_template("upd.json", data=json.dumps({'event_id': event_id}))


@app.route('/following', methods=['GET'])
@login_required
def following_page():
    ACTIVE_EVENTS.clear()
    EXECUTOR.submit(RELAY_HANDLER.set_page('following', request.args.get('pk')))
    EXECUTOR.submit(RELAY_HANDLER.close_secondary_subscriptions)
    if 'pk' in request.args and is_hex_key(request.args['pk']):
        EXECUTOR.submit(RELAY_HANDLER.subscribe_profile, request.args['pk'], timestamp_minus(TimePeriod.WEEK), [])
        k = request.args['pk']
        is_me = False
        p = DB.get_profile(k)
        profiles = []
        if p is not None and p.contacts is not None:
            for key in json.loads(p.contacts):
                profile = DB.get_profile(key)
                if profile is not None:
                    profiles.append(profile)
    else:
        k = Settings.get('pubkey')
        is_me = True
        profiles = DB.get_following()
    profile = DB.get_profile(k)
    return render_template("following.html", page_id="following", title="Following", profile=profile, profiles=profiles,
                           is_me=is_me)


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
            EXECUTOR.submit(RELAY_HANDLER.subscribe_search, request.args['search_term'][1:])
    return render_template("search.html", page_id="search", title="Search", message=message, results=results)


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
                if k == Settings.get('privkey'):
                    passed = True
    if passed:
        k = Settings.get("privkey")
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
            'emojis': ['😄', '🤣', '🙃', '🤩', '🥲', '😝', '👍', '👎']
        }
    return render_template("upd.json", data=json.dumps(d))


@socketio.on('connect')
def io_connect(m):
    unseen_messages = DB.get_unseen_message_count()
    if unseen_messages > 0:
        socketio.emit('unseen_messages_n', unseen_messages)

    unseen_posts = DB.get_unseen_in_feed()
    if unseen_posts > 0:
        socketio.emit('unseen_posts_n', unseen_posts)

    unseen_alerts = DB.get_unread_alert_count()
    socketio.emit('alert_n', unseen_alerts)

    EXECUTOR.submit(RELAY_HANDLER.get_connection_status)


@app.route('/refresh_connections', methods=['GET'])
def refresh_connections():
    EXECUTOR.submit(EXECUTOR.submit(RELAY_HANDLER.reset()))
    return render_template("upd.json", data=json.dumps({'reset': True}))


@app.route('/del_relay', methods=['GET'])
def del_relay():
    DB.remove_relay(request.args['url'])
    EXECUTOR.submit(RELAY_HANDLER.remove_relay(request.args['url']))
    return render_template("upd.json", data=json.dumps({'del': True}))


@app.route('/follow', methods=['GET'])
def follow():
    DB.set_following([request.args['id']], int(request.args['state']))
    DB.commit()
    # EXECUTOR.submit(EVENT_HANDLER.submit_follow_list)
    EXECUTOR.submit(SubmitFollowList())
    profile = DB.get_profile(request.args['id'])
    is_me = request.args['id'] == Settings.get('pubkey')
    upd = request.args['upd']
    if upd == "1":
        return render_template("profile.tools.html", profile=profile, is_me=is_me)
    else:
        return render_template("upd.json", data=json.dumps({'followed': True}))


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
    results, status = {}, 200
    for ts in request.args['ts'].split(','):
        try:
            dt = arrow.get(int(ts))
            results[ts] = dt.humanize()
        except Exception as e:
            logger.warn('Could not read timestamp provided')
            status = 400
    return render_template("upd.json", data=json.dumps({'data': results})), status


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
                note = DB.get_note(data['parent_id'])
                if note:
                    members = json.loads(note.members)
                    if note.public_key not in members:
                        members.insert(0, note.public_key)
            pow_difficulty = Settings.get('pow_default')
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
    if SETUP_PK is not None and Settings.get("privkey") is None:
        logger.info('New setup detected')
        DB.save_pk(encrypt_key(SETUP_PW, SETUP_PK), 1)
        redirect('/login')
    if Settings.get("privkey") is not None:
        logger.info('Has session keys, is logged in {}'.format(Settings.get('pubkey')))
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
            Settings.set("new_keys", True)
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
    logger.info('Set session keys')
    if k is None:
        pk = PrivateKey()
    else:
        pk = PrivateKey(bytes.fromhex(k))
    private_key = pk.hex()
    public_key = pk.public_key.hex()
    Settings.set('pubkey', public_key)
    Settings.set('privkey', private_key)
    process_key_save(private_key)
    if DB.get_profile(public_key) is None:
        DB.add_profile(public_key)


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
