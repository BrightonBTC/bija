from db import BijaDB
from flask import Flask
from gui import init_gui
app = Flask(__name__)

from routes import *
DB = BijaDB()


def main():
    profile = DB.get_profile("test")
    if profile is not None:
        print(profile.public_key)


if __name__ == '__main__':
    init_gui(app)
    # app.run()
