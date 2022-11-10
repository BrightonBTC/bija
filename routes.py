import json
import time
import atexit
from enum import IntEnum

from flask import render_template, request, session, redirect
from flask_executor import Executor
from app import app
from db import BijaDB
from nostr.key import PrivateKey
from markdown import markdown
from password import encrypt_key, decrypt_key
from helpers import *

DB = BijaDB()


class LoginState(IntEnum):
    LOGGED_IN = 0
    WITH_KEY = 1
    WITH_PASSWORD = 2

# def on_shutdown():
#     session.clear()
#     print("session closed")
#
#
# # Register the function to be called on exit
# atexit.register(on_shutdown)


@app.route('/')
def index_page():
    login_state = get_login_state()
    if login_state is LoginState.LOGGED_IN:
        return render_template("base.html", title="Home", data={})
    else:
        return render_template("login.html", title="Login", login_type=login_state)


@app.route('/login', methods=['POST'])
def login_page():
    login_state = get_login_state()
    if request.method == 'POST':
        if process_login():
            return redirect("/")
        else:
            return render_template("login.html", title="Login", message="Incorrect key or password", login_type=login_state)
    return render_template("login.html", title="Login", login_type=login_state)


def is_logged_in():
    return session.get("key")


def get_login_state():
    if session.get("keys") is not None:
        return LoginState.LOGGED_IN
    saved_pk = DB.get_saved_pk()
    if saved_pk is not None:
        if saved_pk.enc == 0:
            session["key"] = saved_pk.key
            return LoginState.LOGGED_IN
        else:
            return LoginState.WITH_PASSWORD
    return LoginState.WITH_KEY


def process_login():
    if 'login' in request.form.keys():
        saved_pk = DB.get_saved_pk()
        k = decrypt_key(request.form['pw'].strip(), saved_pk.key)
        if is_hex_key(k):
            # session["key"] = k
            private_key = PrivateKey(bytes.fromhex(k))
            public_key = private_key.public_key
            set_session_keys(public_key.hex(), private_key.hex())
            return True
        else:
            return False

    elif 'load_private_key' in request.form.keys():
        if len(request.form['private_key'].strip()) < 1:  # generate a new key
            private_key = PrivateKey()
            public_key = private_key.public_key
        elif is_hex_key(request.form['private_key'].strip()):
            hex_key = bytes.fromhex(request.form['private_key'].strip())
            private_key = PrivateKey(hex_key)
            public_key = private_key.public_key
        else:
            return False
        if DB.get_profile(public_key.hex()) is None:
            DB.add_profile(public_key.hex())
        process_key_save(private_key.hex())
        set_session_keys(public_key.hex(), private_key.hex())
        # session["key"] = private_key.hex()
        return True


def process_key_save(pk):
    if 'save_key' in request.form.keys():
        pw = request.form['password'].strip()
        enc = 0
        if len(pw) > 0:
            pk = encrypt_key(pw, pk)
            enc = 1
        DB.save_pk(pk, enc)


def set_session_keys(pub, prv):
    session["keys"] = {
        'public': pub,
        'private': prv
    }

