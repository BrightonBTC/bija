import os
from enum import IntEnum

from flask import render_template, request, session, redirect, make_response
from flask_executor import Executor
import pydenticon
from app import app
from db import BijaDB
from events import BijaEvents
from nostr.key import PrivateKey
from password import encrypt_key, decrypt_key
from helpers import *

DB = BijaDB(app.session)
EXECUTOR = Executor(app)
EVENT_HANDLER = BijaEvents(DB, session)

foreground = [ "rgb(45,79,255)",
               "rgb(254,180,44)",
               "rgb(226,121,234)",
               "rgb(30,179,253)",
               "rgb(232,77,65)",
               "rgb(49,203,115)",
               "rgb(141,69,170)" ]
background = "rgb(224,224,224)"
ident_im_gen = pydenticon.Generator(10, 10, foreground=foreground, background=background)


class LoginState(IntEnum):
    LOGGED_IN = 0
    WITH_KEY = 1
    WITH_PASSWORD = 2


@app.route('/')
def index_page():
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        notes = DB.get_feed()
        return render_template("feed.html", title="Home", notes=notes)
    else:
        return render_template("login.html", title="Login", login_type=login_state)


@app.route('/login', methods=['POST'])
def login_page():
    login_state = get_login_state()
    if request.method == 'POST':
        if process_login():
            EXECUTOR.submit(EVENT_HANDLER.subscribe_primary)
            EXECUTOR.submit(EVENT_HANDLER.message_pool_handler)
            return redirect("/")
        else:
            return render_template("login.html", title="Login", message="Incorrect key or password", login_type=login_state)
    return render_template("login.html", title="Login", login_type=login_state)


@app.route('/identicon', methods=['GET'])
def identicon():
    im = ident_im_gen.generate(request.args['id'], 90, 90, padding=(20, 20, 20, 20), output_format="png")
    response = make_response(im)
    response.headers.set('Content-Type', 'image/png')
    return response


@app.route('/profile')
def profile_page():
    notes = DB.get_notes_by_pubkey(session.get("keys")["public"])
    profile = DB.get_profile(session.get("keys")["public"])
    return render_template("profile.html", title="Home", notes=notes, profile=profile)


@app.route('/keys')
def keys_page():
    return render_template("keys.html", title="Home", k=session.get("keys"))


@app.teardown_appcontext
def remove_session(*args, **kwargs):
    app.session.remove()




@app.get('/shutdown')
def shutdown():
    EVENT_HANDLER.close()
    quit()


def get_login_state():
    if session.get("keys") is not None:
        return LoginState.LOGGED_IN
    saved_pk = DB.get_saved_pk()
    if saved_pk is not None:
        if saved_pk.enc == 0:
            set_session_keys(saved_pk.key)
            EXECUTOR.submit(EVENT_HANDLER.subscribe_primary)
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

