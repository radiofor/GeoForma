"""Inspect the real category dialog and numeric size menu without user data writes."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from main import configure_runtime
configure_runtime()
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow
from geoforma.dialogs import ClassesDialog


def main():
    app=QApplication([]);out=ROOT/'experiments/classes';out.mkdir(parents=True,exist_ok=True)
    w=MainWindow(auto_prepare=False);w.autosave_timer.stop();w.autosave=lambda:None;w.show();w.tabs.setCurrentIndex(1);app.processEvents()
    w.grab().save(str(out/'custom_workbench.png'))
    dialog=ClassesDialog(w.project['classes'],2,set(),1,w);dialog.name.setText('建筑');dialog.rename();dialog.name.setText('道路');dialog.add();dialog.show();app.processEvents();dialog.grab().save(str(out/'classes_dialog.png'));dialog.close()
    w.generation_level.setCurrentIndex(1);w.generation_level.showPopup();app.processEvents()
    w.generation_level.view().window().grab().save(str(out/'size_menu.png'));w.generation_level.hidePopup()
    for size in [(1440,900),(1024,700)]:
        w.resize(*size);app.processEvents();w.grab().save(str(out/f'sizes_{size[0]}_{size[1]}.png'))
    w.dirty=False;w.close();app.processEvents();print('Custom category and size previews saved',flush=True)


if __name__=='__main__':main()
