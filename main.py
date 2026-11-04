"""GeoForma desktop entry point. Run with the GeoForma Python environment."""
import argparse
import os
import sys
from pathlib import Path


def configure_runtime():
    from geoforma.process_bootstrap import configure_native_environment
    configure_native_environment()
    from PySide6.QtCore import QLibraryInfo
    plugins=Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    os.environ['QT_PLUGIN_PATH']=str(plugins)
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']=str(plugins/'platforms')
    os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'xcb')


def main():
    parser=argparse.ArgumentParser(description='GeoForma desktop annotation')
    parser.add_argument('project',nargs='?',help='GeoForma project file (.gfm)')
    parser.add_argument('--recover',action='store_true',help='Restore the latest autosave when reopening the project')
    parser.add_argument('--self-test',metavar='REPORT',help='Check the bundled runtime, model, spawn and GIS exports')
    parser.add_argument('--test-device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--test-execution',choices=['native'],default='native')
    parser.add_argument('--test-raster')
    parser.add_argument('--test-model',help='Registered model ID for release validation')
    parser.add_argument('--test-core-only',action='store_true',help='Validate desktop/GIS/settings without inference resources')
    parser.add_argument('--runtime-command',choices=['cleanup-cache'])
    parser.add_argument('--output',help='JSON result for a runtime command')
    parser.add_argument('--resource-command',choices=['status','install-runtime','install-weight'])
    parser.add_argument('--resource-profile',choices=['cpu','cu126'],default='cpu')
    parser.add_argument('--resource-files',nargs='+',help='Pinned official wheels or one model checkpoint')
    parser.add_argument('--resource-model',help='Registered model ID for weight configuration')
    parser.add_argument('--uninstall-choice',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--uninstall-cleanup',type=int,help=argparse.SUPPRESS)
    args=parser.parse_args()
    try:configure_runtime()
    except Exception as error:
        # pythonw has no console; make an early runtime/profile failure visible.
        if sys.platform=='win32' and Path(sys.executable).stem.lower()=='pythonw':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(error),'GeoForma 启动失败',0x10)
        raise
    if args.uninstall_choice or args.uninstall_cleanup is not None:
        from geoforma.uninstall_commands import choose,cleanup
        if args.uninstall_choice:return choose()
        if args.uninstall_cleanup < 0 or args.uninstall_cleanup > 15:return 2
        return cleanup(args.uninstall_cleanup)
    if args.self_test or args.runtime_command or args.resource_command:
        def command():
            if args.self_test:
                from PIL import Image
                from geoforma.diagnostics import self_test
                return self_test(args.self_test,args.test_raster,args.test_device,args.test_execution,args.test_model,core_only=args.test_core_only)
            if args.runtime_command:
                from geoforma.cache_commands import cleanup_command
                return cleanup_command(args.output)
            from geoforma.resource_commands import resource_command
            return resource_command(args.resource_command,args.output,args.resource_profile,args.resource_files,args.resource_model)
        read_only=not args.self_test and not args.runtime_command and args.resource_command=='status'
        if read_only:return command()
        from geoforma.resource_migration import pending_migration
        try:pending=pending_migration()
        except (OSError,ValueError,RuntimeError):pending=True
        if pending:
            from geoforma.diagnostics import write_report
            from geoforma.domain import data_dir
            report=args.self_test or args.output or data_dir()/'runtime'/'last-command.json'
            write_report(report,{'ok':False,'error':'资源迁移未完成，请先在资源配置中继续迁移。'})
            return 1
        from geoforma.domain import data_dir
        from geoforma.session_guard import desktop_session,resource_session
        with desktop_session(data_dir()) as acquired:
            if acquired:
                with resource_session():return command()
            from geoforma.diagnostics import write_report
            report=args.self_test or args.output or data_dir()/'runtime'/('last-command.json' if args.runtime_command else 'last-resource-command.json')
            write_report(report,{'ok':False,'error':'此数据目录正在由 GeoForma 使用，请关闭工作窗口后重试。'})
            return 1
    from PySide6.QtWidgets import QApplication,QMessageBox
    from geoforma.branding import application_icon
    if sys.platform=='win32':
        import ctypes
        from geoforma.package_context import configure_application_id
        configure_application_id()
    app=QApplication(sys.argv);app.setApplicationName('GeoForma');app.setOrganizationName('GeoForma')
    from geoforma.distribution import VERSION
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(application_icon())
    from geoforma.theme import install_theme
    install_theme(app)
    def log_exception(text):
        from geoforma.resource_location import require_resource_dir
        from geoforma.logging_limits import append_error
        append_error(require_resource_dir(),text)
    def show_exception(value):
        from geoforma.error_messages import user_message
        from geoforma.ui.text import ui_text
        QMessageBox.critical(None,'GeoForma',user_message(value)+'\n'+ui_text('errors.recorded'))
    from geoforma.exception_guard import guarded_exception_hook
    sys.excepthook=guarded_exception_hook(log_exception,show_exception)
    from geoforma.domain import data_dir
    from geoforma.session_guard import desktop_session,resource_session
    with desktop_session(data_dir()) as acquired:
        if not acquired:
            QMessageBox.information(None,'GeoForma','此数据目录已有 GeoForma 窗口正在使用，请切换到已有窗口。')
            return 0
        mutex=None
        if sys.platform=='win32':
            ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
            mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\GeoForma.Desktop')
        with resource_session():
            from geoforma.startup import StartupController
            startup=StartupController(app,args.project,recover_latest=args.recover);startup.start()
            try:return app.exec()
            finally:
                if mutex:
                    ctypes.windll.kernel32.CloseHandle.argtypes=[ctypes.c_void_p]
                    ctypes.windll.kernel32.CloseHandle(mutex)


if __name__=='__main__':
    from geoforma.process_bootstrap import configure_worker_diagnostics
    configure_worker_diagnostics()
    from multiprocessing import freeze_support
    freeze_support()
    raise SystemExit(main())
