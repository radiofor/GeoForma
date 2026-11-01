"""Small SVG toolbar symbols, rendered by Qt without bitmap scaling artifacts."""
from PySide6.QtCore import QByteArray,Qt
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtSvg import QSvgRenderer

PATHS={
    'generate':'<path d="M10 3l2.2 5.8L18 11l-5.8 2.2L10 19l-2.2-5.8L2 11l5.8-2.2zM19 2v6M16 5h6M20 16v6M17 19h6"/>',
    'positive':'<circle cx="12" cy="12" r="8" stroke="#168c6a"/><path d="M8 12h8M12 8v8" stroke="#168c6a"/>',
    'negative':'<circle cx="12" cy="12" r="8" stroke="#d95968"/><path d="M8 12h8" stroke="#d95968"/>',
    'box':'<rect x="4" y="5" width="16" height="14" rx="1" stroke-dasharray="3 2"/>',
    'draw_polygon':'<path d="M4 17l3-12 10-2 4 11-8 7z"/><circle cx="4" cy="17" r="1.5" fill="#ffffff"/><circle cx="7" cy="5" r="1.5" fill="#ffffff"/><circle cx="17" cy="3" r="1.5" fill="#ffffff"/><circle cx="21" cy="14" r="1.5" fill="#ffffff"/><circle cx="13" cy="21" r="1.5" fill="#ffffff"/>',
    'select_points':'<path d="M4 3l6 16 2-6 6-2z"/><circle cx="18" cy="18" r="3"/>',
    'select':'<path d="M5 4l12 8-6 1-3 6z"/><path d="M3 14v6h5M16 4h5v5"/>',
    'reshape':'<path d="M3 18V5h7M21 6v13h-7" stroke-dasharray="2 3"/><path d="M3 18l6-8 6 5 6-9"/><rect x="7" y="8" width="4" height="4" fill="#ffffff"/><rect x="13" y="13" width="4" height="4" fill="#ffffff"/>',
    'pan':'<path d="M7 12V8a1.5 1.5 0 013 0V4a1.5 1.5 0 013 0v2a1.5 1.5 0 013 0v2a1.5 1.5 0 013 0v6c0 5-3 7-6 7h-2c-2 0-3-2-4-3l-4-5a1.5 1.5 0 012-2z"/>',
    'save':'<path d="M5 3h13l3 3v15H3V3z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
    'new_project':'<path d="M5 3h9l5 5v13H5zM14 3v5h5M12 11v7M8.5 14.5h7"/>',
    'open_project':'<path d="M3 7h7l2 2h9l-2 10H3zM3 7V5h7l2 2"/>',
    'recover_project':'<path d="M4 11a8 8 0 118 9M4 5v6h6M12 7v5l3 2"/>',
    'export':'<path d="M4 14v7h16v-7M12 17V3M7 8l5-5 5 5"/>',
    'fit':'<path d="M9 4H4v5M15 4h5v5M20 15v5h-5M4 15v5h5"/>',
    'native':'<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M10 4v16M16 4v16M4 10h16M4 16h16"/>',
    'search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.2 15.2l5.2 5.2"/>',
    'undo':'<path d="M8 4L3 9l5 5M3 9h10a7 7 0 010 14"/>',
    'redo':'<path d="M16 4l5 5-5 5M21 9H11a7 7 0 000 14"/>',
    'delete':'<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    'raw':'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    'raw_hidden':'<path d="M3 8c-1 2-1 4-1 4s4 7 10 7c2 0 4-1 5-2M7 6c2-1 3-1 5-1 6 0 10 7 10 7s-1 2-3 4"/><path d="M10 10a3 3 0 004 4M3 3l18 18"/>',
    'settings':'<path d="M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z"/><circle cx="12" cy="12" r="3"/>',
}

def icon(name,color='#48616e'):
    renderer=QSvgRenderer(QByteArray(('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="'+color+'" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+PATHS[name]+'</g></svg>').encode()))
    pixmap=QPixmap(48,48);pixmap.fill(Qt.GlobalColor.transparent);painter=QPainter(pixmap);renderer.render(painter);painter.end();return QIcon(pixmap)


def visibility_icon():
    """Native checked state: open eye when visible, crossed eye when hidden."""
    result=QIcon()
    for state,name in ((QIcon.State.On,'raw'),(QIcon.State.Off,'raw_hidden')):
        result.addPixmap(icon(name).pixmap(48,48),QIcon.Mode.Normal,state)
    return result
