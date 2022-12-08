import json
from collections import OrderedDict
from datetime import datetime
from threading import Thread, Event

from flask import render_template, request, session, redirect, make_response
from flask_executor import Executor
import pydenticon

from bija.app import app, socketio
from bija.db import BijaDB
from bija.events import BijaEvents
from python_nostr.nostr.key import PrivateKey

from bija.password import encrypt_key, decrypt_key
from bija.helpers import *

thread = Thread()

DB = BijaDB(app.session)
EXECUTOR = Executor(app)
EVENT_HANDLER = BijaEvents(DB, session)

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
    LOGGED_IN = 0
    WITH_KEY = 1
    WITH_PASSWORD = 2


@app.route('/')
def index_page():
    EVENT_HANDLER.set_page('home', None)
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    DB.set_all_seen_in_feed(get_key())
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        notes = DB.get_feed(time.time(), get_key())
        threads, last_ts = make_threaded(notes)
        profile = DB.get_profile(get_key())
        return render_template("feed.html", page_id="home", title="Home", threads=threads, last=last_ts,
                               profile=profile)
    else:
        return render_template("login.html", page_id="login", title="Login", login_type=login_state)


@app.route('/feed', methods=['GET'])
def feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        notes = DB.get_feed(before, get_key())
        profile = DB.get_profile(get_key())
        if len(notes) > 0:
            threads, last_ts = make_threaded(notes)
            return render_template("feed.items.html", threads=threads, last=last_ts, profile=profile)
        else:
            return 'END'


@app.route('/alerts', methods=['GET'])
def alerts_page():
    alerts = DB.get_alerts(get_key())
    DB.set_alerts_read()
    return render_template("alerts.html", page_id="alerts", title="alerts", alerts=alerts)


@app.route('/login', methods=['POST'])
def login_page():
    EVENT_HANDLER.set_page('login', None)
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    login_state = get_login_state()
    if request.method == 'POST':
        if process_login():
            EXECUTOR.submit(EVENT_HANDLER.subscribe_primary)
            EXECUTOR.submit(EVENT_HANDLER.message_pool_handler)
            return redirect("/")
        else:
            return render_template("login.html", title="Login", message="Incorrect key or password",
                                   login_type=login_state)
    return render_template("login.html", page_id="login", title="Login", login_type=login_state)


@app.route('/profile', methods=['GET'])
def profile_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    if 'pk' in request.args and is_hex_key(request.args['pk']) and request.args['pk'] != get_key():
        EVENT_HANDLER.set_page('profile', request.args['pk'])
        EXECUTOR.submit(EVENT_HANDLER.subscribe_profile, request.args['pk'], timestamp_minus(TimePeriod.WEEK))
        k = request.args['pk']
        is_me = False
    else:
        k = get_key()
        EVENT_HANDLER.set_page('profile', k)
        is_me = True
    notes = DB.get_notes_by_pubkey(k, int(time.time()), timestamp_minus(TimePeriod.DAY))
    # t, i = make_threaded(notes)
    threads, last_ts = make_threaded(notes)
    profile = DB.get_profile(k)
    if profile is None:
        DB.add_profile(k)
        profile = DB.get_profile(k)
    return render_template("profile.html", page_id="profile", title="Profile", threads=threads, last=last_ts,
                           profile=profile, is_me=is_me)


@app.route('/note', methods=['GET'])
def note_page():
    EVENT_HANDLER.set_page('note', request.args['id'])
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    note_id = request.args['id']
    EXECUTOR.submit(EVENT_HANDLER.subscribe_thread, note_id)
    notes = DB.get_note_thread(note_id)
    notes_processed = []
    members = []
    for note in notes:
        note = dict(note)
        if note['reshare'] is not None:
            reshare = DB.get_note(note['reshare'])
            if reshare is not None:
                note['reshare'] = reshare
        members.append(note['public_key'])
        members = json.loads(note['members']) + members
        notes_processed.append(note)
    members = list(dict.fromkeys(members))
    profiles = []
    for member in members:
        p = DB.get_profile(member)
        if p is not None:
            profiles.append(p)
    profile = DB.get_profile(get_key())
    return render_template("thread.html",
                           page_id="note", title="Note", notes=notes_processed, members=profiles, profile=profile,
                           root=note_id)


@app.route('/quote_form', methods=['GET'])
def quote_form():
    note_id = request.args['id']
    note = DB.get_note(note_id)
    profile = DB.get_profile(get_key())
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
        event_id = EVENT_HANDLER.submit_delete([note_id], reason)
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
                event_id = EVENT_HANDLER.submit_note(data, members)
                out['event_id'] = event_id
        else:
            out['error'] = 'Quoted note not found at DB'
    return render_template("upd.json", title="Home", data=json.dumps(out))


@app.route('/thread_item', methods=['GET'])
def thread_item():
    note_id = request.args['id']
    note = DB.get_note(note_id)
    profile = DB.get_profile(get_key())
    return render_template("thread.item.html", item=note, profile=profile)


@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        if request.method == 'POST' and 'del_keys' in request.form.keys():
            print("RESET DB")
            EVENT_HANDLER.close()
            DB.reset()
            session.clear()
            return redirect('/')
        else:
            EVENT_HANDLER.set_page('settings', None)
            EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
            settings = {}
            relays = DB.get_relays()
            EVENT_HANDLER.get_connection_status()
            return render_template(
                "settings.html",
                page_id="settings",
                title="Settings", relays=relays, settings=settings, k=session.get("keys"))
    else:
        return render_template("login.html", title="Login", login_type=login_state)


@app.route('/upd_profile', methods=['POST', 'GET'])
def update_profile():
    out = {'success': False}
    if request.method == 'POST':
        profile = {}
        for item in request.json:
            if item[0] in ['name', 'about', 'picture', 'nip05']:
                profile[item[0]] = item[1].strip()
        if 'nip05' in profile and len(profile['nip05']) > 0:
            valid_nip5 = EVENT_HANDLER.validate_nip05(profile['nip05'], get_key())
            out['nip05'] = valid_nip5
            if valid_nip5:
                out['success'] = EVENT_HANDLER.submit_profile(profile)
        else:
            out['success'] = EVENT_HANDLER.submit_profile(profile)
    return render_template("upd.json", data=json.dumps(out))


@app.route('/add_relay', methods=['POST', 'GET'])
def add_relay():
    success = False
    if request.method == 'POST':
        for item in request.json:
            if item[0] == 'newrelay' and is_valid_relay(item[1]):
                success = True
                DB.insert_relay(item[1])
                EVENT_HANDLER.add_relay(item[1])
    return render_template("upd.json", data=json.dumps({'ad_relay': success}))


@app.route('/reset_relays', methods=['POST', 'GET'])
def reset_relays():
    EXECUTOR.submit(EVENT_HANDLER.reset)
    return render_template("upd.json", data=json.dumps({'reset_relays': True}))


@app.route('/messages', methods=['GET'])
def private_messages_page():
    EVENT_HANDLER.set_page('messages', None)
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)

    messages = DB.get_message_list()

    return render_template("messages.html", page_id="messages", title="Private Messages", messages=messages)


@app.route('/message', methods=['GET'])
def private_message_page():
    EVENT_HANDLER.set_page('message', request.args['pk'])
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    messages = []
    pk = ''
    if 'pk' in request.args and is_hex_key(request.args['pk']):
        messages = DB.get_message_thread(request.args['pk'])
        pk = request.args['pk']

    profile = DB.get_profile(get_key())
    them = DB.get_profile(pk)

    messages.reverse()

    return render_template("message_thread.html", page_id="messages_from", title="Messages From", messages=messages,
                           me=profile, them=them)


@app.route('/submit_message', methods=['POST', 'GET'])
def submit_message():
    event_id = False
    if request.method == 'POST':
        event_id = EVENT_HANDLER.submit_message(request.json)
    return render_template("upd.json", title="Home", data=json.dumps({'event_id': event_id}))


@app.route('/like', methods=['GET'])
def submit_like():
    event_id = False
    if 'id' in request.args:
        note_id = request.args['id']
        note = DB.get_note(note_id)
        if note.liked is False:
            DB.set_note_liked(note_id)
            event_id = EVENT_HANDLER.submit_like(note_id)
        else:
            DB.set_note_liked(note_id, False)
            like_events = DB.get_like_events_for(note_id, get_key())
            if like_events is not None:
                ids = []
                for event in like_events:
                    ids.append(event.id)
                event_id = EVENT_HANDLER.submit_delete(ids)

    return render_template("upd.json", data=json.dumps({'event_id': event_id}))


@app.route('/following', methods=['GET'])
def following_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    if 'pk' in request.args and is_hex_key(request.args['pk']):
        EXECUTOR.submit(EVENT_HANDLER.subscribe_profile, request.args['pk'], timestamp_minus(TimePeriod.WEEK))
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
        k = get_key()
        is_me = True
        profiles = DB.get_following()
    profile = DB.get_profile(k)
    return render_template("following.html", page_id="profile", title="Following", profile=profile, profiles=profiles,
                           is_me=is_me)


@app.route('/search', methods=['GET'])
def search_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    results = []
    if 'search_term' in request.args or len(request.args['search_term'].strip()) < 1:
        term = request.args['search_term']
        if is_hex_key(request.args['search_term']):
            return redirect('/profile?pk={}'.format(term))
        elif validate_nip05(term):
            profile = DB.get_pk_by_nip05(term)
            if profile is not None:
                return redirect('/profile?pk={}'.format(profile.public_key))
            else:
                pk = request_nip05(term)
                if pk is not None:
                    return redirect('/profile?pk={}'.format(pk))
                else:
                    message = "Nip-05 identifier could not be located"
        else:
            message = "Nothing found. Please try again with a valid public key or nip-05 identifier."
    else:
        message = "no search term found!"
    return render_template("search.html", page_id="search", title="Search", message=message, results=results)


@app.route('/identicon', methods=['GET'])
def identicon():
    im = ident_im_gen.generate(request.args['id'], 120, 120, padding=(10, 10, 10, 10), output_format="png")
    response = make_response(im)
    response.headers.set('Content-Type', 'image/png')
    return response


@socketio.on('connect')
def io_connect(m):
    unseen_messages = DB.get_unseen_message_count()
    if unseen_messages > 0:
        socketio.emit('unseen_messages_n', unseen_messages)

    unseen_posts = DB.get_unseen_in_feed()
    if unseen_posts > 0:
        socketio.emit('unseen_posts_n', unseen_posts)

    unseen_alerts = DB.get_unread_alert_count()
    if unseen_alerts > 0:
        socketio.emit('alert_n', unseen_alerts)

    EXECUTOR.submit(EVENT_HANDLER.get_connection_status)


@app.route('/refresh_connections', methods=['GET'])
def refresh_connections():
    EXECUTOR.submit(EVENT_HANDLER.reset())
    return render_template("upd.json", data=json.dumps({'reset': True}))


@app.route('/del_relay', methods=['GET'])
def del_relay():
    DB.remove_relay(request.args['url'])
    EVENT_HANDLER.remove_relay(request.args['url'])
    return render_template("upd.json", data=json.dumps({'del': True}))


@app.route('/follow', methods=['GET'])
def follow():
    DB.set_following([request.args['id']], int(request.args['state']))
    EXECUTOR.submit(EVENT_HANDLER.submit_follow_list)
    profile = DB.get_profile(request.args['id'])
    is_me = request.args['id'] == get_key()
    return render_template("profile.tools.html", profile=profile, is_me=is_me)


@app.route('/fetch_raw', methods=['GET'])
def fetch_raw():
    d = DB.get_raw_note_data(request.args['id'])
    return render_template("upd.json", data=json.dumps({'data': d.raw}))


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
            event_id = EVENT_HANDLER.submit_note(data, members)
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
    EVENT_HANDLER.close()
    quit()


@app.template_filter('dt')
def _jinja2_filter_datetime(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d @ %H:%M')


@app.template_filter('decr')
def _jinja2_filter_decr(content, pubkey):
    try:
        k = bytes.fromhex(get_key("private"))
        pk = PrivateKey(k)
        return pk.decrypt_message(content, pubkey)
    except ValueError:
        return 'could not decrypt!'


@app.template_filter('ident_string')
def _jinja2_filter_ident(name, pk, nip5=None, validated=None):
    if validated and nip5 is not None:
        if nip5[0:2] == "_@":
            nip5 = nip5[2:]
        return "<span class='uname' data-pk='{}'><span class='name'>{}</span> <span class='nip5'>{}</span>".format(pk,
                                                                                                                   name,
                                                                                                                   nip5)
    elif name is None or len(name.strip()) < 1:
        name = "<span class='uname' data-pk='{}'><span class='name'>{}...</span> <span class='nip5'></span></span>".format(
            pk, pk[0:21])
    else:
        name = "<span class='uname' data-pk='{}'><span class='name'>{}</span> <span class='nip5'></span></span>".format(
            pk, name)
    return name


@app.template_filter('responders_string')
def _jinja2_filter_responders(the_dict, n):
    names = []
    for pk, name in the_dict.items():
        names.append([pk, _jinja2_filter_ident(name, pk)])

    if n == 1:
        return '<a href="/profile?pk={}">@{}</a> commented'.format(names[0][0], names[0][1])
    elif n == 2:
        return '<a href="/profile?pk={}">@{}</a> and <a href="/profile?pk={}">@{}</a> commented'.format(names[0][0],
                                                                                                        names[0][1],
                                                                                                        names[1][0],
                                                                                                        names[1][1])
    else:
        return '<a href="/profile?pk={}">@{}</a>, <a href="/profile?pk={}">@{}</a> and {} other contacts commented'.format(
            names[0][0], names[0][1], names[1][0], names[1][1], n - 2)


@app.template_filter('process_media_attachments')
def _jinja2_filter_media(json_string):
    a = json.loads(json_string)
    if len(a) > 0:
        media = a[0]
        if media[1] == 'image':
            return '<div class="image-attachment"><img src="{}"></div>'.format(media[0])
    return '';


@app.template_filter('get_thread_root')
def _jinja2_filter_thread_root(root, reply, parent_id):
    out = {'root': '', 'reply': ''}
    if root is None and reply is None:
        out['root'] = parent_id
    elif root is not None and reply is not None:
        out = {'root': root, 'reply': parent_id}
    elif root is not None:
        out = {'root': root, 'reply': parent_id}
    elif reply is not None:
        out = {'root': reply, 'reply': parent_id}
    return out


def make_threaded(notes):
    threads = []
    thread_roots = []
    last_ts = None
    for note in notes:
        note = dict(note)
        last_ts = note['created_at']
        if note['thread_root'] is not None:
            thread_roots.append(note['thread_root'])
        elif note['response_to'] is not None:
            thread_roots.append(note['response_to'])
        elif note['thread_root'] is None and note['response_to'] is None:
            thread_roots.append(note['id'])

    thread_roots = list(dict.fromkeys(thread_roots))

    for root in thread_roots:
        t = {'self': None, 'id': root, 'response': None, 'responders': {}}
        responders = []
        for note in notes:
            note = dict(note)
            if note['reshare'] is not None:
                reshare = DB.get_note(note['reshare'])
                if reshare is not None:
                    note['reshare'] = reshare
            if note['id'] == root:
                t['self'] = note
            elif note['response_to'] == root or note['thread_root'] == root:
                if t['response'] is None:
                    t['response'] = note
                if len(t['responders']) < 2:
                    t['responders'][note['public_key']] = note['name']
                responders.append(note['public_key'])
        responders = list(dict.fromkeys(responders))
        t['responder_count'] = len(responders)

        if t['self'] is None:
            t['self'] = DB.get_note(root)
        threads.append(t)

    return threads, last_ts


def get_login_state():
    if session.get("keys") is not None:
        return LoginState.LOGGED_IN
    saved_pk = DB.get_saved_pk()
    if saved_pk is not None:
        if saved_pk.enc == 0:
            set_session_keys(saved_pk.key)
            EXECUTOR.submit(EVENT_HANDLER.subscribe_primary)
            # EXECUTOR.submit(EVENT_HANDLER.get_active_relays)
            EXECUTOR.submit(EVENT_HANDLER.message_pool_handler)
            return LoginState.LOGGED_IN
        else:
            return LoginState.WITH_PASSWORD
    return LoginState.WITH_KEY


def process_login():
    if 'login' in request.form.keys():
        saved_pk = DB.get_saved_pk()
        k = decrypt_key(request.form['pw'].strip(), saved_pk.key)
        if is_hex_key(k):
            set_session_keys(k)
            return True
        else:
            return False

    elif 'load_private_key' in request.form.keys():
        if len(request.form['private_key'].strip()) < 1:  # generate a new key
            private_key = None
        elif is_hex_key(request.form['private_key'].strip()):
            private_key = request.form['private_key'].strip()
        else:
            return False
        set_session_keys(private_key)
        return True


def process_key_save(pk):
    if 'save_key' in request.form.keys():
        pw = request.form['password'].strip()
        enc = 0
        if len(pw) > 0:
            pk = encrypt_key(pw, pk)
            enc = 1
        DB.save_pk(pk, enc)


def get_key(k='public'):
    keys = session.get("keys")
    if keys is not None and k in keys:
        return keys[k]
    else:
        return False


def set_session_keys(k):
    if k is None:
        pk = PrivateKey()
    else:
        pk = PrivateKey(bytes.fromhex(k))
    private_key = pk.hex()
    public_key = pk.public_key.hex()
    session["keys"] = {
        'private': private_key,
        'public': public_key
    }
    process_key_save(private_key)
    if DB.get_profile(public_key) is None:
        DB.add_profile(public_key)
