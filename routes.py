import json
import time
from datetime import datetime
from enum import IntEnum

from flask import render_template, request, session, redirect, make_response
from flask_executor import Executor
import pydenticon
from markdown import markdown

from app import app
from db import BijaDB
from events import BijaEvents
from python_nostr.nostr.key import PrivateKey

from password import encrypt_key, decrypt_key
from helpers import *

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
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    EVENT_HANDLER.unseen_notes = 0
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        notes = DB.get_feed(time.time(), session.get("keys")["public"])
        t, i = make_threaded(notes)

        return render_template("feed.html", title="Home", threads=t, ids=i)
    else:
        return render_template("login.html", title="Login", login_type=login_state)


@app.route('/feed', methods=['GET'])
def feed():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        notes = DB.get_feed(before, session.get("keys")["public"])
        t, i = make_threaded(notes)

        return render_template("feed.items.html", threads=t, ids=i)


@app.route('/login', methods=['POST'])
def login_page():
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
    return render_template("login.html", title="Login", login_type=login_state)


@app.route('/profile', methods=['GET'])
def profile_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    if 'pk' in request.args and is_hex_key(request.args['pk']):
        EXECUTOR.submit(EVENT_HANDLER.subscribe_profile, request.args['pk'], timestamp_minus(TimePeriod.WEEK))
        k = request.args['pk']
        is_me = False
    else:
        k = session.get("keys")["public"]
        is_me = True
    notes = DB.get_notes_by_pubkey(k, int(time.time()), timestamp_minus(TimePeriod.DAY))
    t, i = make_threaded(notes)
    profile = DB.get_profile(k)
    return render_template("profile.html", title="Profile", threads=t, ids=i, profile=profile, is_me=is_me)


@app.route('/note', methods=['GET'])
def note_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    note_id = request.args['id']
    EXECUTOR.submit(EVENT_HANDLER.subscribe_note, note_id)

    note = DB.get_note(note_id)
    notes = []
    if note is not None:
        if note.thread_root is not None:
            notes = DB.get_note_thread(note.thread_root)
        elif note.response_to is not None:
            notes = DB.get_note_thread(note.response_to)
        else:
            notes = DB.get_note_thread(note.id)

    n = note_thread(notes, note_id)
    return render_template("note.html", title="Note", notes=n)


@app.route('/messages', methods=['GET'])
def private_messages_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)

    messages = DB.get_message_list()

    return render_template("messages.html", title="Message List", messages=messages)


@app.route('/message', methods=['GET'])
def private_message_page():
    EXECUTOR.submit(EVENT_HANDLER.close_secondary_subscriptions)
    messages = []
    pk = ''
    if 'pk' in request.args and is_hex_key(request.args['pk']):
        messages = DB.get_message_thread(request.args['pk'])
        pk = request.args['pk']

    profile = DB.get_profile(session.get("keys")["public"])

    messages.reverse()

    return render_template("message_thread.html", title="Messages", messages=messages, me=profile, them=pk)


@app.route('/submit_message', methods=['POST', 'GET'])
def submit_message():
    event_id = False
    if request.method == 'POST':
        event_id = EVENT_HANDLER.submit_message(request.json)
    return render_template("upd.json", title="Home", data=json.dumps({'event_id': event_id}))


def note_thread(notes, current):
    out = []
    notes.reverse()
    current_found = False
    next_ancestor = None
    for note in notes:
        note = dict(note)
        note['content'] = markdown(note['content'])

        if current_found:
            if note['response_to'] is None and note['thread_root'] is None:
                note['is_root'] = True
                out.insert(0, note)
            elif note['id'] == next_ancestor:
                note['is_ancestor'] = True
                next_ancestor = note["response_to"]
                out.insert(0, note)
        elif current == note['response_to']:
            note['is_reply'] = True
            out.insert(0, note)
        elif note['id'] == current:
            out.insert(0, note)
            next_ancestor = note["response_to"]
            current_found = True
    return out


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
        k = session.get("keys")["public"]
        is_me = True
        profiles = DB.get_following()
    profile = DB.get_profile(k)
    return render_template("following.html", title="Following", profile=profile, profiles=profiles, is_me=is_me)


@app.route('/identicon', methods=['GET'])
def identicon():
    im = ident_im_gen.generate(request.args['id'], 120, 120, padding=(10, 10, 10, 10), output_format="png")
    response = make_response(im)
    response.headers.set('Content-Type', 'image/png')
    return response


@app.route('/upd', methods=['POST', 'GET'])
def get_updates():
    notices = EVENT_HANDLER.notices
    d = {'unseen_posts': EVENT_HANDLER.unseen_notes, 'notices': notices}
    EVENT_HANDLER.notices = []
    return render_template("upd.json", title="Home", data=json.dumps(d))


@app.route('/follow', methods=['GET'])
def follow():
    DB.set_following([request.args['id']], int(request.args['state']))
    EXECUTOR.submit(EVENT_HANDLER.submit_follow_list)
    profile = DB.get_profile(request.args['id'])
    is_me = request.args['id'] == session.get("keys")["public"]
    return render_template("profile.tools.html", profile=profile, is_me=is_me)


@app.route('/upd_profile', methods=['GET'])
def get_profile_updates():
    d = []
    p = DB.get_profile_updates(request.args['pk'], request.args['updat'])
    if p is not None:
        if p.pic is None or len(p.pic.strip()) == 0:
            p.pic = '/identicon?id={}'.format(p.public_key)
        d = {'profile': {
            'name': p.name,
            'nip05': p.nip05,
            'about': p.about,
            'updated_at': p.updated_at,
            'pic': p.pic,
        }}
    return render_template("upd.json", title="Home", data=json.dumps(d))


@app.route('/submit_note', methods=['POST', 'GET'])
def submit_note():
    event_id = False
    if request.method == 'POST':
        event_id = EVENT_HANDLER.submit_note(request.json)
        print(request.json)
    return render_template("upd.json", title="Home", data=json.dumps({'event_id': event_id}))


@app.route('/keys', methods=['GET', 'POST'])
def keys_page():
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        if request.method == 'POST' and 'del_keys' in request.form.keys():
            print("RESET DB")
            EVENT_HANDLER.close()
            DB.reset()
            session.clear()
            return redirect('/')
        else:
            return render_template("keys.html", title="Keys", k=session.get("keys"))
    else:
        return render_template("login.html", title="Login", login_type=login_state)


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
def _jinja2_filter_decr(content, pk):
    return EVENT_HANDLER.decrypt(content, pk)


def make_threaded(notes):
    in_list = []
    threads = []
    for note in notes:
        in_list.append(note['id'])
        note = dict(note)
        note['content'] = markdown(note['content'])

        thread = [note]
        thread_ids = []
        if note['response_to'] is not None:
            thread_ids.append(note['response_to'])
        if note['thread_root'] is not None:
            thread_ids.append(note['thread_root'])

        for n in notes:
            nn = dict(n)
            if nn['id'] in thread_ids:
                notes.remove(n)
                nn['is_parent'] = True
                thread.insert(0, nn)
                in_list.append(nn['id'])
                if nn['response_to'] is not None:
                    thread_ids.append(nn['response_to'])
                if nn['thread_root'] is not None:
                    thread_ids.append(nn['thread_root'])

        threads.append(thread)

    return threads, in_list


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
