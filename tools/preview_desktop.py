"""Capture the actual Qt widgets for layout QA without modifying the demo project."""
import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from main import configure_runtime
configure_runtime()
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QSettings
from geoforma.window import MainWindow
from geoforma.dialogs import BandsDialog,ModelDialog


def main():
    app=QApplication([]);QMessageBox.question=lambda *args:QMessageBox.StandardButton.Yes;out=ROOT/'experiments/workbench';out.mkdir(parents=True,exist_ok=True)
    source=out/'acceptance.geoforma.json' if (out/'acceptance.geoforma.json').exists() else ROOT/'examples/himalaya.geoforma.json'
    w=MainWindow(source,auto_prepare=False);w.settings=QSettings('GeoForma','GeoFormaTests');w.autosave_timer.stop();w.autosave=lambda:None;w.show();start=time.monotonic()
    while True:
        app.processEvents();time.sleep(.02)
        if w.image and not w.candidate_task and not w.render_task and not w.render_timer.isActive():break
        if time.monotonic()-start>60:raise TimeoutError('Preview render')
    w.project_title.setText(source.name);w.view.fit_image();w.grab().save(str(out/'geoforma_preview.png'))
    draft=w.draft;w.draft={};w.tabs.setCurrentIndex(1);w.refresh_labels();w.update_draft_info();app.processEvents()
    w.grab().save(str(out/'candidate_levels_preview.png'));w.draft=draft;w.tabs.setCurrentIndex(0);w.refresh_labels();w.update_draft_info()
    w.resize(1280,800);app.processEvents();time.sleep(.1);app.processEvents();w.grab().save(str(out/'compact_preview.png'))
    model=ModelDialog(w.project['model'],w);model.show();app.processEvents();model.grab().save(str(out/'model_dialog.png'));model.close()
    bands=BandsDialog(w.image,w);bands.show();app.processEvents();bands.grab().save(str(out/'bands_dialog.png'));bands.close()
    w.tabs.setCurrentIndex(1)
    for width,height in [(1280,800),(1024,700)]:
        w.resize(width,height);app.processEvents();w.grab().save(str(out/f'workbench_{width}_{height}.png'))
        print('layout',width,height,'actual',w.width(),w.height(),'table',w.labels_table.height(),flush=True)
    candidate=next((label for label in w.presentation_labels() if label['status']=='candidate'),None)
    if candidate:
        w.select_label(candidate['id']);w.edit_selected();w.draft['edge']=True;w.update_draft_info();w.update_controls();app.processEvents();w.grab().save(str(out/'small_editor.png'))
        print('small editor actual',w.width(),w.height(),'table',w.labels_table.height(),flush=True)
    while w.candidate_task or w.render_task or w.render_timer.isActive():app.processEvents();time.sleep(.02)
    w.dirty=False;w.close();app.processEvents()
    empty=MainWindow(auto_prepare=False);empty.autosave=lambda:None;empty.show();app.processEvents();empty.grab().save(str(out/'empty_workbench.png'));empty.dirty=False;empty.close();app.processEvents();print('Qt layout snapshots saved',flush=True)


if __name__=='__main__':main()
