"""Shared, restrained visual language for the desktop and startup screen."""
from functools import lru_cache
import os
from pathlib import Path

from PySide6.QtCore import Qt, QRectF,QTranslator,QLibraryInfo
from .class_colors import HIGHLIGHTS
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QHBoxLayout, QWidget, QGroupBox

INK = '#172f3d'
TEAL = '#087f88'
CANVAS = '#122430'
SELECTION,EDITING = HIGHLIGHTS

STYLE = '''
QMainWindow,QDialog{background:#f1f5f6;color:#213946;font-family:"Microsoft YaHei UI";font-size:9pt;}
QMenuBar{background:#ffffff;border-bottom:1px solid #e0e8eb;padding:2px 6px;}
QMenuBar::item{padding:5px 10px;border-radius:4px;background:transparent;}
QMenuBar::item:selected,QMenu::item:selected{background:#e3f3f0;color:#086972;}
QMenu{background:white;border:1px solid #d3e0e5;padding:5px;}
QMenu::item{padding:7px 24px 7px 12px;border-radius:4px;}
QToolBar{background:white;border:0;border-bottom:1px solid #dbe5e9;padding:5px 4px;spacing:3px;}
QToolBar::separator{background:#dce5e9;width:1px;margin:7px 5px;}
QToolButton{padding:6px 6px;border:1px solid transparent;border-radius:6px;color:#334f5d;}
QToolButton:hover{background:#edf5f6;border-color:#d2e6e7;}
QToolButton:checked{background:#def3ef;border-color:#a9dcd4;color:#066b70;font-weight:600;}
QToolButton:disabled{color:#8799a3;}
QPushButton{padding:7px 10px;background:white;color:#304c59;border:1px solid #ccdce2;border-radius:6px;}
QPushButton[role="modelSelector"]{padding:7px 2px;padding-right:22px;font-size:8.5pt;}
QPushButton:hover{background:#edf8f6;border-color:#76bdb8;}
QPushButton:pressed{background:#d8ece8;}
QPushButton:checked{background:#def3ef;border-color:#a9dcd4;color:#066b70;}
QPushButton:focus,QToolButton:focus{border-color:#087f88;}
QPushButton:disabled{color:#7d909c;background:#f3f6f7;border-color:#dce5e9;}
QPushButton#primary{background:#087f88;color:white;border-color:#087f88;font-weight:600;}
QPushButton#primary:hover{background:#086b75;border-color:#086b75;}
QPushButton#primary:pressed{background:#075661;}
QPushButton#primary:disabled{background:#d3e4e5;color:#637c87;border-color:#d3e4e5;}
QPushButton[role="import"]{background:#e7f5f1;color:#0a6871;border-color:#b8ded6;font-weight:600;}
QPushButton[role="import"]:hover{background:#d8eee8;border-color:#70b8ad;}
QPushButton[role="import"]:pressed{background:#087f88;color:white;border-color:#066b70;}
QPushButton[role="import"]:disabled{background:#f3f6f7;color:#7d909c;border-color:#dce5e9;}
QPushButton[role="danger"]:hover{background:#fff1f0;color:#a33e4b;border-color:#e3b4b9;}
QPushButton[role="danger"]:pressed{background:#f9dce1;color:#9e3444;border-color:#d78491;}
QDockWidget{border:0;}
QMainWindow::separator{background:#dce5e9;width:6px;height:6px;}
QMainWindow::separator:hover{background:#9fc9cb;}
QLabel[role="panelTitle"]{color:#516c7a;background:#eaf0f3;padding:4px 12px;font-weight:600;font-size:11px;border-bottom:1px solid #dce5e9;}
QWidget[role="sidePanel"]{background:#f6f9fa;}
QWidget#rasterInfo,QWidget#promptCounters{background:#edf4f6;border-radius:6px;}
QLabel[role="counter"]{color:#176d72;font-size:17px;font-weight:600;}
QLabel[role="muted"]{color:#5e7684;}
QLabel[role="deviceStatus"]{color:#5e7684;background:white;border:1px solid #ccdce2;border-radius:6px;font-size:8.5pt;}
QLabel[role="dialogTitle"]{color:#116d77;font-size:18px;font-weight:600;}
QLabel[role="sectionTitle"]{color:#385a6a;font-weight:600;}
QLabel[role="project"]{color:#21505a;background:#edf7f5;border:1px solid #d8eae5;border-radius:6px;font-weight:600;padding:6px 10px;}
QLabel[role="status"]{color:#536f7d;background:#e6eef2;border-radius:5px;padding:4px 9px;font-weight:600;}
QLabel[role="status"][tone="ready"]{color:#086e68;background:#dcf2eb;}
QLabel[role="status"][tone="busy"]{color:#096c82;background:#e1f1f6;}
QLabel[role="status"][tone="warning"]{color:#896321;background:#fff0d5;}
QLabel[role="status"][tone="error"]{color:#a13e50;background:#fce9ee;}
QGroupBox{background:white;border:1px solid #dce6ea;border-radius:9px;margin-top:12px;padding:14px 2px 3px 2px;}
QGroupBox::title{subcontrol-origin:margin;left:12px;color:#385a6a;font-weight:600;padding:0px 4px;}
QListWidget,QTableWidget,QPlainTextEdit{background:white;border:1px solid #dce6ea;border-radius:7px;selection-background-color:#e1f3ef;selection-color:#173d48;outline:0;}
QListWidget::item{padding:7px 6px;margin:2px 3px;border:1px solid transparent;border-radius:5px;}
QListWidget::item:selected{background:#e1f3ef;border-color:#afdbd2;color:#174b51;}
QListWidget::item:hover:!selected{background:#e8f4f5;border-color:#b0d6d8;}
QListWidget::item:selected:hover{background:#d2ece7;border-color:#76bdb8;}
QTableWidget{gridline-color:#edf2f4;}
QTableWidget::item{padding:4px;}
QTableWidget::item:selected{background:#ffce45;color:#293842;}
QHeaderView::section{background:#edf3f5;color:#4c6978;border:0;border-bottom:1px solid #dfe8ec;padding:7px;font-weight:600;}
QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit{padding:6px;background:white;color:#304c59;border:1px solid #ccdce2;border-radius:5px;min-height:18px;}
QComboBox:enabled:hover{background:#f0f7f7;border-color:#76bdb8;}
QComboBox:focus,QLineEdit:focus{border-color:#087f88;}
QComboBox:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled{color:#7d909c;background:#f3f6f7;border-color:#dce5e9;}
QComboBox::drop-down{border:0;width:22px;background:transparent;}
QComboBox::down-arrow{image:url("asset_chevron_down");width:12px;height:12px;}
QSpinBox,QDoubleSpinBox{padding-right:18px;padding-left:4px;}
QSpinBox::up-button,QDoubleSpinBox::up-button{subcontrol-origin:border;subcontrol-position:top right;width:21px;height:16px;border:0;border-left:1px solid #dce5e9;border-top-right-radius:5px;background:#edf3f5;}
QSpinBox::down-button,QDoubleSpinBox::down-button{subcontrol-origin:border;subcontrol-position:bottom right;width:21px;height:16px;border:0;border-left:1px solid #dce5e9;border-bottom-right-radius:5px;background:#edf3f5;}
QSpinBox::up-button:hover,QDoubleSpinBox::up-button:hover,QSpinBox::down-button:hover,QDoubleSpinBox::down-button:hover{background:#def3ef;}
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow{image:url("asset_spin_up");width:12px;height:12px;}
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow{image:url("asset_spin_down");width:12px;height:12px;}
QComboBox QAbstractItemView{background:white;color:#304c59;selection-background-color:#e1f3ef;selection-color:#173d48;border:1px solid #c7dbdf;border-radius:7px;outline:0;padding:4px;}
QComboBox QAbstractItemView::item{padding:0px 10px;border:1px solid transparent;border-radius:5px;}
QComboBox QAbstractItemView::item:hover{background:#f0f7f7;}
QComboBox QAbstractItemView::item:selected{background:#e1f3ef;border-color:#b7ddd6;color:#12656d;}
QTabWidget#resourceTabs::pane{background:white;border:1px solid #dce6ea;border-radius:7px;}
QTextBrowser#resourceFiles{background:white;color:#304c59;border:1px solid #dce6ea;border-radius:7px;padding:10px;}
QTabBar::tab{padding:10px 12px;background:#e5edef;color:#4c6774;border:1px solid transparent;}
QTabBar::tab:first{border-top-left-radius:7px;border-bottom-left-radius:7px;}
QTabBar::tab:last{border-top-right-radius:7px;border-bottom-right-radius:7px;}
QTabBar::tab:selected{background:#117b85;color:white;font-weight:600;}
QTabBar::tab:hover:!selected{background:#d9e9eb;}
QStatusBar{background:#eaf1f4;color:#4a6575;border-top:1px solid #dbe5e9;padding:3px 7px;}
QStatusBar::item{border:0;}
QScrollArea{background:#f6f9fa;border:0;}
QScrollBar:vertical{background:transparent;width:10px;margin:2px;}
QScrollBar::handle:vertical{background:#c0d1da;border-radius:3px;min-height:24px;}
QScrollBar::handle:vertical:hover{background:#98b7c2;}
QScrollBar::handle:vertical:disabled{background:transparent;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}
QToolTip{background:#203d4d;color:white;border:0;padding:6px;}
'''
from .distribution import resource_root
STYLE = STYLE.replace('asset_chevron_down', (resource_root() / 'assets' / 'chevron_down.svg').as_posix())
STYLE = STYLE.replace('asset_spin_up', (resource_root() / 'assets' / 'spin_up.svg').as_posix()).replace('asset_spin_down', (resource_root() / 'assets' / 'spin_down.svg').as_posix())


def install_theme(app=None):
    """Call only on the GUI thread. Fusion removes platform-specific control noise."""
    app = app or QApplication.instance()
    from .ui.button_feedback import install_button_feedback
    install_button_feedback(app)
    from .ui.tooltips import install_tooltips
    install_tooltips(app)
    if app.property('geoformaThemeInstalled'):
        return
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    translator=QTranslator(app)
    if translator.load('qtbase_zh_CN',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator);app._geoforma_qt_translator=translator
    app.setStyle('Fusion')
    app.setFont(QFont('Microsoft YaHei UI', 9))
    app.setStyleSheet(STYLE)
    app.setProperty('geoformaThemeInstalled', True)


def set_tone(label, tone):
    if label.property('tone') == tone:
        return
    label.setProperty('tone', tone)
    label.style().unpolish(label)
    label.style().polish(label)
    label.update()


class PanelGroupBox(QGroupBox):
    """A title capsule centered on the top border, independent of platform metrics."""
    def __init__(self,title='',parent=None):
        super().__init__(title,parent);self.setProperty('role','card')
        # Establish the frame metrics before layouts are added, including the
        # first card constructed before the main window has a native handle.
        self.setStyleSheet('QGroupBox {margin:0; padding:0; border:0; background:transparent;}')
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line_y=16.;frame=QRectF(.5,line_y,self.width()-1,self.height()-line_y-.5)
        painter.setPen(QPen(QColor('#d5e3e7'),1));painter.setBrush(QColor('white'));painter.drawRoundedRect(frame,9,9)
        font=self.font();font.setBold(True);painter.setFont(font);metrics=painter.fontMetrics()
        height=metrics.height()+6;width=metrics.horizontalAdvance(self.title())+18
        title=QRectF(12,line_y-height/2,width,height)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#e4f3ef'));painter.drawRoundedRect(title,6,6)
        painter.setPen(QColor('#176c70'));painter.drawText(title,Qt.AlignmentFlag.AlignCenter,self.title())


BLOCK_PITCH = 60
BLOCK_SIZE = 40
BLOCK_COLORS = ('#172E3A', '#19353F', '#193B42', '#254149')
BLOCK_ORDER = ((0, 1, 0, 2), (2, 0, 1, 0), (0, 3, 0, 1), (1, 0, 2, 0))


@lru_cache(maxsize=4)
def _grid_tile(device_ratio):
    """The same filled-block rhythm as GeoSage, with a blue/teal palette."""
    side = round(BLOCK_PITCH * len(BLOCK_ORDER) * device_ratio)
    tile = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    tile.setDevicePixelRatio(device_ratio)
    tile.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tile)
    inset = (BLOCK_PITCH - BLOCK_SIZE) / 2
    for row, colors in enumerate(BLOCK_ORDER):
        for column, index in enumerate(colors):
            painter.fillRect(QRectF(column * BLOCK_PITCH + inset, row * BLOCK_PITCH + inset,
                                    BLOCK_SIZE, BLOCK_SIZE), QColor(BLOCK_COLORS[index]))
    painter.end()
    return tile


def draw_grid_pattern(painter, rect, opacity=1.0):
    """Quiet square array in screen space; never overlays loaded raster pixels."""
    painter.save()
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    painter.setOpacity(opacity)
    ratio = round(painter.device().devicePixelRatioF(), 3)
    painter.fillRect(rect, QBrush(_grid_tile(ratio)))
    painter.restore()


class BrandHeader(QWidget):
    """A compact brand signature; the imagery retains the largest share of space."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)
        row.addStretch()
        from .branding import application_icon
        mark = QLabel()
        mark.setPixmap(application_icon().pixmap(40, 40))
        mark.setFixedSize(40, 40)
        row.addWidget(mark)
        name = QLabel('GeoForma')
        name.setStyleSheet('color:#eef9fa;font-size:18pt;font-weight:700;background:transparent;')
        row.addWidget(name)
        row.addStretch()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect())
        gradient = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        gradient.setColorAt(0, QColor('#173b4c'))
        gradient.setColorAt(1, QColor('#16545e'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(bounds, 9, 9)

