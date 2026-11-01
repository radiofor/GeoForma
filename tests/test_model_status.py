import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from geoforma.model_catalog import MODELS
from geoforma.model_status import weight_status,memory_budget
from geoforma.dialogs import ModelDialog


def test_missing_partial_and_complete_weights_are_distinguished(tmp_path):
    spec=dict(MODELS[0],bytes=8);path=tmp_path/spec['file']
    assert weight_status(spec,path)[0]=='未配置'
    path.write_bytes(b'part');assert weight_status(spec,path)[0]=='文件不完整'
    path.write_bytes(b'complete');assert weight_status(spec,path)[0]=='权重就绪'
    custom=tmp_path/'custom.pt';custom.write_bytes(b'unknown')
    assert weight_status(spec,custom)[0]=='本地待校验'


def test_budgets_include_margin_for_every_model():
    for spec in MODELS:
        for mode in ('interaction','automatic'):
            assert memory_budget(spec,mode)>spec['memory_profile'][mode+'_peak_mib']/1024


def test_model_dialog_cpu_and_custom_path_status(tmp_path,monkeypatch):
    import geoforma.model_status as module
    monkeypatch.setattr(module,'default_checkpoint',lambda *a:tmp_path/'missing.pt')
    app=QApplication.instance() or QApplication([])
    cfg={'backend':'sam','variant':'vit_b','device':'cuda','checkpoint':str(tmp_path/'missing.pt')}
    dialog=ModelDialog(cfg)
    assert '未配置' in dialog.variant.currentText() and '预计显存' in dialog.memory_info.text()
    dialog.device.setCurrentIndex(dialog.device.findData('cpu'))
    assert '不占用模型显存' in dialog.memory_info.text()
    custom=tmp_path/'custom.pt';custom.write_bytes(b'unknown');dialog.path.setText(str(custom))
    assert '本地待校验' in dialog.weight_info.text()
    assert dialog.value()['checkpoint']==str(custom)
    dialog.close();app.processEvents()
