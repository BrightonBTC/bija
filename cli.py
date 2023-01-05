from bija.app import main

from gevent.pywsgi import WSGIServer

if __name__ == '__main__':
    app = main()
    http_server = WSGIServer(("0.0.0.0", 5000), app)
    http_server.serve_forever()
