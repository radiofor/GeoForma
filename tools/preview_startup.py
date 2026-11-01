"""Fresh-process startup timing and actual Qt screenshots, without user projects."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
OUT = ROOT / 'experiments' / 'appearance'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['GEOFORMA_DATA_DIR'] = str(OUT / 'test_data')
from main import configure_runtime
configure_runtime()
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from geoforma.startup import StartupController
from geoforma.theme import install_theme


def main():
    app = QApplication([])
    app.setApplicationName('GeoForma')
    install_theme(app)
    started = time.monotonic()
    phases, ticks, errors = [], [], []
    c = StartupController(app)
    c.failed.connect(errors.append)
    def phase(value, text):
        phases.append({'value': value, 'text': text, 'seconds': round(time.monotonic() - started, 3)})
        if value == 2:
            c.splash.grab().save(str(OUT / 'startup_loading.png'))
    def capture():
        c.splash.grab().save(str(OUT / 'startup_screen.png'))
    def ready(window):
        window.autosave_timer.stop()
        window.autosave = lambda: None
        def done():
            assert window.width() == 1440 and window.height() == 900
            window.grab().save(str(OUT / 'empty_window.png'))
            report = {'ok': not errors, 'ready_seconds': round(time.monotonic() - started, 3),
                      'phases': phases, 'gui_timer_ticks': len(ticks), 'torch_loaded': 'torch' in sys.modules,
                      'size': [window.width(), window.height()], 'scale': window.devicePixelRatioF()}
            (OUT / ('startup_scale_' + os.environ.get('QT_SCALE_FACTOR', '1') + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=True), flush=True)
            window.dirty = False
            window.close()
        QTimer.singleShot(0, done)
    c.ready.connect(ready)
    c.start()
    c.splash.grab().save(str(OUT / 'startup_screen.png'))
    # Worker is created on the next event turn; connect before it emits progress.
    QTimer.singleShot(0, lambda: c.worker.progress.connect(phase) if c.worker else None)
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(time.monotonic()))
    heartbeat.start()
    QTimer.singleShot(30000, app.quit)
    code = app.exec()
    if c.worker:
        c.worker.requestInterruption()
        c.worker.wait()
    if errors:
        raise RuntimeError(errors)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
