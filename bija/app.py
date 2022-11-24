
from flask_socketio import SocketIO
from flask import Flask
from flask_session import Session
from sqlalchemy.orm import scoped_session
import db
from gui import init_gui

app = Flask(__name__)
socketio = SocketIO(app)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
app.session = scoped_session(db.DB_SESSION)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

from routes import *


if __name__ == '__main__':
    init_gui(app, socketio)
    # app.run()
