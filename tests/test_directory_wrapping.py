"""Long source directories remain fully visible and copyable at narrow widths."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
import pytest
from geoforma.ui.readouts import RasterInfo
from geoforma.theme import install_theme


@pytest.mark.parametrize('width',[230,360])
@pytest.mark.parametrize('name',['S2-MCQ-2025-Q3-RGB/X181','很长的目录名称' * 12])
def test_wrapped_directory_fits_every_line_and_preserves_text(width,name):
    app=QApplication.instance() or QApplication([]);install_theme(app)
    info=RasterInfo();info.setFixedWidth(width);info.show();app.processEvents()
    path='I:/HighAsia-Imagery/'+name
    info.setText('2,048 × 2,048 · 3 波段\n影像 CRS：EPSG:3857\n模型 RGB：1/2/3\n文件目录：'+path)
    for _ in range(5):app.processEvents()
    directory=info.directory
    try:
        assert directory.text()==path and directory.isReadOnly()
        assert directory.document().firstBlock().layout().lineCount()>1
        directory.moveCursor(QTextCursor.MoveOperation.End);app.processEvents()
        assert directory.cursorRect().bottom()<=directory.viewport().rect().bottom()
        assert directory.verticalScrollBar().maximum()==0 and directory.horizontalScrollBar().maximum()==0
        directory.selectAll();assert directory.textCursor().selectedText()==path
        height=info.height();info.setText(info.text());app.processEvents();assert info.height()==height
        info.clear();app.processEvents();assert directory.text()=='—' and info.height()<=height
    finally:info.close()
