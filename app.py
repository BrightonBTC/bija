from db import BijaDB
from flask import Flask
from flask_session import Session
from sqlalchemy.orm import scoped_session
import db
from gui import init_gui

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
app.session = scoped_session(db.DB_SESSION)
from routes import *


if __name__ == '__main__':
    init_gui(app)
    # app.run()
