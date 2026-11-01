"""Render the application's model dialog and popup without editing user settings."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from main import configure_runtime
configure_runtime()
from PySide6.QtWidgets import QApplication
from geoforma.domain import new_project
from geoforma.dialogs import ModelDialog

app=QApplication([]);dialog=ModelDialog(new_project()['model']);dialog.show();app.processEvents()
dialog.grab().save(str(ROOT/'experiments/model_status_dialog.png'))
dialog.variant.showPopup();app.processEvents()
dialog.variant.view().window().grab().save(str(ROOT/'experiments/model_status_list.png'))
print('\n'.join(dialog.variant.itemText(i) for i in range(dialog.variant.count())))
dialog.variant.hidePopup();dialog.close();app.processEvents()
