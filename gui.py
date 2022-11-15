import sys
from PyQt5 import QtCore, QtWidgets, QtGui, QtWebEngineWidgets
from PyQt5.QtWidgets import QMainWindow


def init_gui(application, port=5000, width=1100, height=800,
             window_title="Bija Nostr Client", icon="static/aum.png"):

    ROOT_URL = 'http://localhost:{}'.format(port)

    # open links in browser from http://stackoverflow.com/a/3188942/1103397 :D thanks to
    # https://github.com/marczellm/qhangups/blob/cfed73ee4383caed1568c0183a9906180f01cb00/qhangups/WebEnginePage.py
    def link_clicked(url, typ, ismainframe):
        ready_url = url.toEncoded().data().decode()
        is_clicked = typ == QtWebEngineWidgets.QWebEnginePage.NavigationTypeLinkClicked
        is_not_internal = ROOT_URL not in ready_url
        if is_clicked and is_not_internal:
            QtGui.QDesktopServices.openUrl(url)
            return False
        return True

    def run_app():
        application.run(port=port, threaded=True)

    # Application Level
    qtapp = QtWidgets.QApplication(sys.argv)
    webapp = QtCore.QThread()
    webapp.__del__ = webapp.wait
    webapp.run = run_app
    webapp.start()
    qtapp.aboutToQuit.connect(webapp.terminate)

    # Main Window Level
    window = MainWindow()
    window.resize(width, height)
    window.setWindowTitle(window_title)
    window.setWindowIcon(QtGui.QIcon(icon))

    # WebView Level
    window.webView = QtWebEngineWidgets.QWebEngineView(window)
    window.setCentralWidget(window.webView)

    # WebPage Level
    page = QtWebEngineWidgets.QWebEnginePage()
    page.acceptNavigationRequest = link_clicked
    page.load(QtCore.QUrl(ROOT_URL))
    window.webView.setPage(page)

    window.show()

    return qtapp.exec_()


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, *args, obj=None, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setupUi(self)



    def closeEvent(self, event):
        page = QtWebEngineWidgets.QWebEnginePage()
        page.load(QtCore.QUrl("http://localhost:5000/shutdown"))
        self.webView.setPage(page)

        print("Close clicked")
        # Ask for confirmation
        answer = QtWidgets.QMessageBox.question(self,
        "Confirm Exit...",
        "Are you sure you want to exit?\nAll data will be lost.",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

        event.ignore()
        if answer == QtWidgets.QMessageBox.Yes:
            event.accept()


