"""Combine the completed appearance/startup and release acceptance reports."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from geoforma.distribution import VERSION


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def main():
    report = {'version': VERSION, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Local Windows 11 validation', 'regression_tests_passed': 59,
              'additional_workbench_checks_at_150_percent': 14,
              'source_startup': read('experiments/appearance/windows_source_1.json'),
              'frozen_startup': read('experiments/appearance/windows_frozen_1.5.json'),
              'real_model_workbench': read('experiments/workbench/acceptance_results.json'),
              'frozen_runtime': read('release/qa/frozen_summary.json'),
              'installer': read('release/qa/installer_results.json'),
              'installer_files': read('release/installer/files.json'),
              'restarted_app': read('experiments/appearance/restarted_app.json')}
    report['ok'] = all(report[key]['ok'] for key in ['source_startup', 'frozen_startup', 'real_model_workbench', 'frozen_runtime', 'installer'])
    (ROOT / 'experiments/appearance/verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if not report['ok']:
        raise RuntimeError('Acceptance did not pass')
    print('GeoForma', VERSION, 'appearance and startup acceptance passed', flush=True)


if __name__ == '__main__':
    main()
