from db import BijaDB
from flask import Flask
from flask_session import Session
from gui import init_gui

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
from routes import *


# def main():
#     profile = DB.get_profile("test")
#     if profile is not None:
#         print(profile.public_key)


if __name__ == '__main__':
    init_gui(app)
    # app.run()
