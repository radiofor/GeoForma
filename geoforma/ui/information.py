"""Read-only local documentation and dependency dialogs with stable layouts."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,
    QTextBrowser,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPushButton,QDialogButtonBox)
from ..application_info import DOCUMENTS,document_text,dependency_rows
from ..distribution import VERSION


class DocumentationDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('说明文档');self.resize(860,580);self.setMinimumSize(640,420)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,12);layout.setSpacing(12)
        heading=QLabel('GeoForma '+VERSION);heading.setProperty('role','panelTitle');layout.addWidget(heading)
        row=QHBoxLayout();row.setSpacing(12);self.navigation=QListWidget();self.navigation.setFixedWidth(144)
        self.navigation.addItems([title for title,_ in DOCUMENTS]);row.addWidget(self.navigation)
        self.navigation.setUniformItemSizes(True)
        for index in range(self.navigation.count()):self.navigation.item(index).setSizeHint(QSize(120,36))
        self.browser=QTextBrowser();self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet('QTextBrowser{background:white;border:1px solid #dce6ea;border-radius:7px;padding:12px;}')
        row.addWidget(self.browser,1);layout.addLayout(row,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.button(QDialogButtonBox.StandardButton.Close).setText('关闭')
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.navigation.currentRowChanged.connect(self.show_document);self.navigation.setCurrentRow(0)

    def show_document(self,index):
        if not 0<=index<len(DOCUMENTS):return
        try:text=document_text(DOCUMENTS[index][1])
        except (OSError,ValueError) as error:text='无法读取说明文档：'+str(error)
        self.browser.setPlainText(text);self.browser.verticalScrollBar().setValue(0)


class DependencyVersionsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('依赖库版本');self.resize(560,540);self.setMinimumSize(460,360)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,12);layout.setSpacing(12)
        heading=QLabel('GeoForma '+VERSION);heading.setProperty('role','panelTitle');layout.addWidget(heading)
        self.rows=dependency_rows();self.table=QTableWidget(len(self.rows),2);self.table.setHorizontalHeaderLabels(['组件','版本'])
        self.table.verticalHeader().hide();self.table.setShowGrid(False);self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for row,values in enumerate(self.rows):
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);self.table.setItem(row,column,item)
        layout.addWidget(self.table,1);row=QHBoxLayout();row.addStretch(1)
        self.copy_button=QPushButton('复制');self.copy_button.clicked.connect(self.copy_versions);row.addWidget(self.copy_button)
        close=QPushButton('关闭');close.clicked.connect(self.accept);row.addWidget(close);layout.addLayout(row)

    def copy_versions(self):
        QApplication.clipboard().setText('\n'.join(name+'\t'+version for name,version in self.rows))
