from PySide2.QtWidgets import QMainWindow, QWidget, QTextBrowser, QGridLayout

from PySide2.QtCore import Qt

class AboutWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QGridLayout(self.central_widget)
        self.setWindowTitle(self.tr("About"))
        self.setMinimumSize(600, 600)
        self.text = QTextBrowser()
        self.layout.addWidget(self.text, 0, 0)
        self.setWindowFlags(Qt.Drawer)
        self.text.setHtml(
"""
<font face="Arial">
    <h2>QGrain</h2>
    <p>QGrain is a easy to use software that can unmix the multi-modal grain size distribution to some single modals.</p>
    <p>It's writted by Python which make it can benifit from the great open source and scientific computation communities.</p>
    <p>QGrain is still during the rapid development stage, its functionalities and usages may changes many and many times. And of course, there probably are some bugs. We are very sorry for its immaturity.</p>
    <p>We are really hope to receive your feedbacks. Whatever it's bug report, request of new feature, disscusion on algorithms.</p>
    <p>Moreover, we are looking forward that there are some partners to join the development of QGrain.</>
    <p>If you have any idea, you can contact the authors below.</p>
    <h4>Authors:</h4>
    <ul>
        <li>Yuming Liu <a>liuyuming@ieecas.cn</a></li>
    </ul>
</font>
""")

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.saveGeometry()
