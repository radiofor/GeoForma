"""Observe a real Windows startup and gracefully close only this tool's child."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
USER = ctypes.WinDLL('user32', use_last_error=True)
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
USER.EnumWindows.argtypes = [CALLBACK, wintypes.LPARAM]
USER.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER.IsWindowVisible.argtypes = [wintypes.HWND]
USER.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
USER.SendMessageTimeoutW.restype = wintypes.LPARAM
USER.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def windows(pid):
    found = []
    @CALLBACK
    def visit(handle, _):
        owner = wintypes.DWORD()
        USER.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid and USER.IsWindowVisible(handle):
            text = ctypes.create_unicode_buffer(512)
            USER.GetWindowTextW(handle, text, len(text))
            found.append((handle, text.value))
        return True
    USER.EnumWindows(visit, 0)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--scale', default='1')
    parser.add_argument('--output-dir', type=Path, help='Isolated directory for startup data and reports')
    parser.add_argument('--close-delay', type=float, default=0, help='Wait for startup dialogs before closing the workbench')
    parser.add_argument('--close-resource-dialog', action='store_true', help='Close the startup resource dialog before its parent')
    args = parser.parse_args()
    if args.close_delay < 0:parser.error('--close-delay must not be negative')
    label = 'frozen' if args.exe else 'source'
    output = (args.output_dir or ROOT / 'experiments' / 'appearance').resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM='windows', QT_SCALE_FACTOR=args.scale,
               GEOFORMA_DATA_DIR=str(output / ('process_' + label)),
               GEOFORMA_SETTINGS_FILE=str(output / ('settings_' + label + '.ini')))
    if args.exe:
        for key in ['PYTHONPATH', 'PYTHONHOME', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'GDAL_DATA', 'PROJ_DATA', 'PROJ_LIB']:
            env.pop(key, None)
        env['PATH'] = os.environ['SystemRoot'] + '/System32;' + os.environ['SystemRoot']
        command = [str(args.exe.resolve())]
    else:
        command = [str(Path(sys.executable).with_name('pythonw.exe')), str(ROOT / 'main.py')]
    started = time.monotonic()
    process = subprocess.Popen(command, env=env, cwd=output)
    seen = []
    ready = None
    try:
        while time.monotonic() - started < 90:
            if process.poll() is not None:
                raise RuntimeError('Application exited before creating its workbench: ' + str(process.returncode))
            for handle, title in windows(process.pid):
                if title not in [item['title'] for item in seen]:
                    seen.append({'title': title, 'seconds': round(time.monotonic() - started, 3)})
                if title == 'GeoForma':
                    result = ctypes.c_size_t()
                    if not USER.SendMessageTimeoutW(handle, 0, 0, 0, 2, 200, ctypes.byref(result)):
                        raise RuntimeError('Workbench is unresponsive')
                    ready = time.monotonic() - started
                    if args.close_delay:
                        time.sleep(args.close_delay)
                        for _, other_title in windows(process.pid):
                            if other_title not in [item['title'] for item in seen]:
                                seen.append({'title': other_title, 'seconds': round(time.monotonic() - started, 3)})
                    if args.close_resource_dialog:
                        resource = next((child for child, caption in windows(process.pid) if caption == '资源配置'), None)
                        if resource is None:raise RuntimeError('Startup resource dialog did not appear')
                        USER.PostMessageW(resource, 0x0010, 0, 0)
                        deadline = time.monotonic() + 10
                        while any(child == resource for child, _ in windows(process.pid)):
                            if time.monotonic() >= deadline:raise RuntimeError('Startup resource dialog did not close')
                            time.sleep(.02)
                    USER.PostMessageW(handle, 0x0010, 0, 0)  # WM_CLOSE on our own QA child only.
                    break
            if ready is not None:
                break
            time.sleep(.02)
        if ready is None:
            raise TimeoutError('Windows startup did not finish')
        try:
            code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            remaining = [{'handle': int(handle), 'title': title} for handle, title in windows(process.pid)]
            report = {'ok': False, 'kind': label, 'scale': args.scale, 'stage': 'close_timeout',
                      'ready_seconds': round(ready, 3), 'windows': seen, 'remaining_windows': remaining}
            (output / ('windows_' + label + '_' + args.scale + '.json')).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            raise RuntimeError('Window did not exit after WM_CLOSE: ' + json.dumps(report, ensure_ascii=False)) from None
        if code:
            raise RuntimeError('Application did not close normally: ' + str(code))
        report = {'ok': True, 'kind': label, 'scale': args.scale, 'ready_seconds': round(ready, 3),
                  'windows': seen, 'responsive': True, 'normal_close': True,
                  'closed_resource_dialog': args.close_resource_dialog}
        (output / ('windows_' + label + '_' + args.scale + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True), flush=True)
    finally:
        if process.poll() is None:
            for handle, title in windows(process.pid):
                USER.PostMessageW(handle, 0x0010, 0, 0)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
