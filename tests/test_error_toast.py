"""Error feedback is transient, non-modal and independent of status messages."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_workbench import workbench


def test_error_toast_does_not_block_or_overwrite_status(workbench):
    w,app,_,_=workbench;w.show();app.processEvents();bar=w.statusBar()
    bar.showMessage('正在准备影像',5000);bar.report_error('参考读取失败，请检查文件。',source='reference')
    app.processEvents();toast=bar._error_toast
    assert toast.label.isVisible() and toast.label.text()=='参考读取失败，请检查文件。'
    assert toast.label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert toast.label.focusPolicy()==Qt.FocusPolicy.NoFocus and bar.currentMessage()=='正在准备影像'
    assert toast.timer.interval()==2000
    QTest.qWait(2050);app.processEvents();assert not toast.label.isVisible()


def test_error_toast_treats_paths_and_input_as_plain_text(workbench):
    w,app,_,_=workbench;w.show();app.processEvents()
    text='无法读取 <lake.tif>：请检查路径。';w.statusBar().report_error(text)
    label=w.statusBar()._error_toast.label
    assert label.textFormat()==Qt.TextFormat.PlainText and label.text()==text


def test_errors_deduplicate_and_source_reset(workbench):
    w,app,_,_=workbench;w.show();app.processEvents();bar=w.statusBar()
    bar.report_error('保存失败',source='save');toast=bar._error_toast
    toast.timer.setInterval(1500);bar.report_error('保存失败',source='save')
    assert toast.timer.interval()==1500
    bar.report_error('参考读取失败',source='reference');assert toast.label.text()=='保存失败'
    assert toast.pending==[('reference','参考读取失败')]
    bar.clear_error_source('save');assert toast.label.isVisible() and toast.label.text()=='参考读取失败'
    bar.clear_error_source('reference');assert not toast.label.isVisible()
    bar.reset_error_source('save');bar.report_error('保存失败',source='save');assert toast.label.isVisible()


def test_error_toast_wraps_to_available_width(workbench):
    w,app,_,_=workbench;w.resize(1024,700);w.show();app.processEvents();bar=w.statusBar()
    text='读取影像失败，请检查文件及其路径。'*8;bar.report_error(text);app.processEvents();toast=bar._error_toast
    assert toast.label.wordWrap() and toast.label.text()==text and toast.label.width()<=w.width()-32
    assert toast.label.height()>=toast.label.heightForWidth(toast.label.width())


def test_extreme_error_stays_inside_window_and_points_to_log(workbench):
    w,app,_,_=workbench;w.resize(700,450);w.show();app.processEvents();bar=w.statusBar()
    bar.report_error('无法读取文件。'*2000);app.processEvents();toast=bar._error_toast
    assert toast.label.geometry().top()>=0 and toast.label.geometry().bottom()<w.height()
    assert '详见任务记录' in toast.label.text()


def test_concurrent_errors_each_remain_for_two_seconds(workbench):
    w,app,_,_=workbench;w.show();app.processEvents();bar=w.statusBar()
    bar.report_error('影像读取失败',source='image');bar.report_error('平滑失败',source='smoothing')
    toast=bar._error_toast;assert toast.label.text()=='影像读取失败'
    QTest.qWait(2050);app.processEvents();assert toast.label.text()=='平滑失败' and toast.label.isVisible()
    QTest.qWait(2050);app.processEvents();assert not toast.label.isVisible()


def test_error_can_be_shown_within_active_decision_dialog(workbench):
    from PySide6.QtWidgets import QDialog
    w,app,_,_=workbench;w.show();dialog=QDialog(w);dialog.resize(450,220);dialog.show();app.processEvents()
    w.statusBar().report_error('路径无效，请重新选择。',source='missing',parent=dialog);app.processEvents()
    toast=dialog._error_toast
    assert toast.label.parentWidget() is dialog and toast.label.isVisible()
    assert toast.label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    dialog.close();app.processEvents()


def test_destroy_and_recreate_windows_with_active_toasts(workbench):
    import gc
    from PySide6.QtCore import QCoreApplication,QEvent
    from PySide6.QtWidgets import QDialog
    from geoforma.ui.error_toast import ErrorToast
    w,app,_,_=workbench;w.show()
    for index in range(20):
        dialog=QDialog(w);dialog.resize(320,180);dialog.show();app.processEvents()
        toast=ErrorToast(dialog,None);toast.show(f'操作失败 {index}')
        dialog.resize(330,190);app.processEvents();dialog.close();dialog.deleteLater()
        del toast,dialog
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents();gc.collect()
    bar=w.statusBar();bar.report_error('窗口仍可工作');app.processEvents()
    assert bar._error_toast.label.text()=='窗口仍可工作'
