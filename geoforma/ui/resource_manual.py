"""One manual configuration entry for official downloads and local imports."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTextBrowser,QPushButton,QApplication
from ..resource_links import download_html,download_text
from .text import ui_text


class ManualResourceDialog(QDialog):
    def __init__(self,parent,files,homepage,caption=''):
        super().__init__(parent);self.setWindowTitle('手动配置'+(' · '+caption if caption else ''));self.resize(720,410);self.setMinimumSize(640,380)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,16,18,16);layout.setSpacing(12)
        if caption:
            self.caption=QLabel(caption);self.caption.setProperty('role','dialogTitle');layout.addWidget(self.caption)
        note=QLabel(ui_text('resources.manual_requirements'))
        note.setProperty('role','muted');note.setWordWrap(True);layout.addWidget(note)
        self.browser=QTextBrowser();self.browser.setObjectName('resourceFiles');self.browser.setOpenExternalLinks(True)
        self.browser.setToolTip(ui_text('resources.manual_scope'))
        self.browser.setHtml(download_html(files,homepage));layout.addWidget(self.browser)
        row=QHBoxLayout();self.website=QPushButton('打开下载页面');self.website.setToolTip(homepage)
        self.website.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(homepage)));row.addWidget(self.website,1)
        self.import_button=QPushButton('导入本地文件');self.import_button.setObjectName('primary');self.import_button.setProperty('feedback','import')
        self.import_button.clicked.connect(self.accept);row.addWidget(self.import_button,1);layout.addLayout(row)
        row=QHBoxLayout();self.copy_button=QPushButton(ui_text('resources.copy_downloads'));self.copy_button.setToolTip(ui_text('resources.copy_downloads_hint'))
        self.copy_button.clicked.connect(lambda:QApplication.clipboard().setText(download_text(files,homepage)))
        row.addWidget(self.copy_button);row.addStretch(1);close=QPushButton('关闭');close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
