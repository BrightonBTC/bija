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
from nostr.key import PrivateKey

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
    EVENT_HANDLER.unseen_notes = 0
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        notes = DB.get_feed(time.time())
        t, i = make_threaded(notes)

        return render_template("feed.html", title="Home", threads=t, ids=i)
    else:
        return render_template("login.html", title="Login", login_type=login_state)


@app.route('/feed', methods=['GET'])
def feed():
    if request.method == 'GET':
        if 'before' in request.args:
            before = int(request.args['before'])
        else:
            before = time.time()
        notes = DB.get_feed(before)
        t, i = make_threaded(notes)

        return render_template("feed_items.html", threads=t, ids=i)


@app.route('/login', methods=['POST'])
def login_page():
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


@app.route('/note', methods=['GET'])
def note_page():
    return render_template("note.html", title="Note")


@app.route('/identicon', methods=['GET'])
def identicon():
    im = ident_im_gen.generate(request.args['id'], 120, 120, padding=(10, 10, 10, 10), output_format="png")
    response = make_response(im)
    response.headers.set('Content-Type', 'image/png')
    return response


@app.route('/upd', methods=['POST', 'GET'])
def get_updates():
    d = {'unseen_posts': EVENT_HANDLER.unseen_notes}
    return render_template("upd.json", title="Home", data=json.dumps(d))


@app.route('/submit_note', methods=['POST', 'GET'])
def submit_note():
    event_id = False
    if request.method == 'POST':
        event_id = EVENT_HANDLER.submit_note(request.json)
        print(request.json)
    return render_template("upd.json", title="Home", data=json.dumps({'event_id': event_id}))


@app.route('/profile', methods=['GET'])
def profile_page():
    if 'pk' not in request.args:
        k = session.get("keys")["public"]
    elif is_hex_key(request.args['pk']):
        k = request.args['pk']
    else:
        redirect('/404')
    notes = DB.get_notes_by_pubkey(k, time.time())
    t, i = make_threaded(notes)
    profile = DB.get_profile(k)
    return render_template("profile.html", title="Profile", threads=t, ids=i, profile=profile)


@app.route('/keys', methods=['GET', 'POST'])
def keys_page():
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        if request.method == 'POST' and 'del_keys' in request.form.keys():
            print("RESET DB")
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
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d | %H:%M:%S')


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
