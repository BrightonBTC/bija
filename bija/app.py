from flask_socketio import SocketIO
from flask import Flask
from sqlalchemy.orm import scoped_session
import bija.db as db
from bija.active_events import ActiveEvents
from bija.args import args
from bija.ws.relay_manager import RelayManager

app = Flask(__name__, template_folder='../bija/templates')
socketio = SocketIO(app)
app.session = scoped_session(db.DB_SESSION)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
ACTIVE_EVENTS = ActiveEvents()
RELAY_MANAGER = RelayManager()


from bija.routes import *


def main():
    print("Bija is now running at http://localhost:{}".format(args.port))
    socketio.run(app, host="0.0.0.0", port=args.port)


if __name__ == '__main__':
    main()
