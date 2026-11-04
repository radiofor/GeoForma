import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow


def test_import_remembers_folder_across_settings_reload_and_cancel(tmp_path,monkeypatch):
    import PySide6.QtWidgets as ui
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    settings_path=str(tmp_path/'preferences.ini');w.settings=QSettings(settings_path,QSettings.Format.IniFormat)
    folder=tmp_path/'imagery';folder.mkdir();selected=str(folder/'sample.tif');imports=[];starts=[]
    w.import_paths=lambda files:imports.extend(files)
    def pick(parent,title,directory,filters):
        assert '*.vrt' in filters and '*.tif' in filters and '*.yaml' not in filters and '*.yml' not in filters
        assert w.import_button.isDown();starts.append(directory);return [selected],filters
    monkeypatch.setattr(ui.QFileDialog,'getOpenFileNames',pick)
    w.import_dialog();assert starts==[''] and imports==[selected] and not w.import_button.isDown()
    w.settings=QSettings(settings_path,QSettings.Format.IniFormat)
    def cancel(parent,title,directory,filters):
        starts.append(directory);return [],filters
    monkeypatch.setattr(ui.QFileDialog,'getOpenFileNames',cancel)
    w.import_dialog();assert starts[-1]==str(folder.resolve()) and not w.import_button.isDown()
    assert w.settings.value('last_import_directory')==str(folder.resolve()) and imports==[selected]
    folder.rmdir();w.import_dialog();assert starts[-1]==''
    w.dirty=False;w.close();app.processEvents()
