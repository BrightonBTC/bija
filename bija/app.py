from flask_socketio import SocketIO
from engineio.async_drivers import gevent
from flask import Flask
from flask_session import Session
from sqlalchemy.orm import scoped_session
import bija.db as db
from bija.gui import init_gui

app = Flask(__name__, template_folder='../bija/templates')
socketio = SocketIO(app)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
app.session = scoped_session(db.DB_SESSION)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

from bija.routes import *


def main():
    init_gui(app, socketio)
    #socketio.run(app)


if __name__ == '__main__':
    main()
