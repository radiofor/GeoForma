import unittest

from geoforma.exception_guard import guarded_exception_hook


class ExceptionGuardTests(unittest.TestCase):
    def test_nested_and_repeated_qt_errors_do_not_open_more_dialogs(self):
        logs=[]
        dialogs=[]
        hook=None

        def show(error):
            dialogs.append(str(error))
            hook(RuntimeError,RuntimeError('nested paint error'),None)
            hook(AttributeError,AttributeError("'PressFeedback' object has no attribute 'strength'"),None)

        hook=guarded_exception_hook(logs.append,show)
        error=AttributeError("'PressFeedback' object has no attribute 'strength'")
        hook(type(error),error,None)
        hook(type(error),error,None)
        self.assertEqual(len(dialogs),1)
        self.assertEqual(len(logs),2)
        self.assertTrue(any('nested paint error' in text for text in logs))

    def test_distinct_later_error_is_reported(self):
        logs=[]
        dialogs=[]
        hook=guarded_exception_hook(logs.append,dialogs.append)
        hook(ValueError,ValueError('first'),None)
        hook(ValueError,ValueError('second'),None)
        self.assertEqual([str(error) for error in dialogs],['first','second'])
        self.assertEqual(len(logs),2)

    def test_repeated_errors_use_sliding_window_and_can_reappear(self):
        now=[0.0]
        dialogs=[]
        hook=guarded_exception_hook(lambda _:None,dialogs.append,clock=lambda:now[0])
        error=ValueError('same')
        hook(type(error),error,None)
        for instant in (4.0,8.0,12.0):
            now[0]=instant
            hook(type(error),error,None)
        self.assertEqual(len(dialogs),1)
        now[0]=17.0
        hook(type(error),error,None)
        self.assertEqual(len(dialogs),2)

    def test_long_errors_with_the_same_tail_are_not_confused(self):
        dialogs=[]
        hook=guarded_exception_hook(lambda _:None,dialogs.append)
        suffix='x'*300
        hook(ValueError,ValueError('first'+suffix),None)
        hook(ValueError,ValueError('second'+suffix),None)
        self.assertEqual(len(dialogs),2)

    def test_reporting_failures_do_not_leave_guard_stuck(self):
        dialogs=[]
        def broken_log(_text):
            raise OSError('log unavailable')
        def show(error):
            dialogs.append(str(error))
            if str(error)=='first':raise RuntimeError('dialog unavailable')
        hook=guarded_exception_hook(broken_log,show)
        hook(ValueError,ValueError('first'),None)
        hook(ValueError,ValueError('second'),None)
        self.assertEqual(dialogs,['first','second'])


if __name__=='__main__':
    unittest.main()
