import os
import sys
from PyQt6 import QtCore, QtWidgets, QtGui, QtWebEngineWidgets
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWebEngineCore import QWebEngineSettings


def init_gui(application, socketio, port=5000, width=1100, height=800,
             window_title="Bija Nostr Client", icon="/static/bija.png"):

    ROOT_URL = 'http://127.0.0.1:{}/'.format(port)

    def run_app():
        socketio.run(application)

    # Application Level
    qtapp = QtWidgets.QApplication(sys.argv)
    webapp = QtCore.QThread()
    webapp.run = run_app
    webapp.start()

    # Main Window Level
    window = MainWindow()
    window.resize(width, height)
    window.setWindowTitle(window_title)

    scriptDir = os.path.dirname(os.path.realpath(__file__))
    window.setWindowIcon(QtGui.QIcon(scriptDir + os.path.sep + icon))

    def url_changed(url):
        url_s = url.url()
        if ROOT_URL not in url_s:
            QDesktopServices.openUrl(url)
            window.webView.back()

    # WebView Level
    window.webView = QtWebEngineWidgets.QWebEngineView(window)
    window.setCentralWidget(window.webView)
    window.webView.urlChanged.connect(url_changed)

    # WebPage Level
    window.webView.load(QtCore.QUrl(ROOT_URL))

    window.show()
    window.webView.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)

    return qtapp.exec()


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, *args, obj=None, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.ui = Ui_MainWindow()
        self.setupUi(self)

    def closeEvent(self, event):
        page = QtWebEngineWidgets.QWebEngineView()
        page.load(QtCore.QUrl("http://127.0.0.1:5000/shutdown"))
