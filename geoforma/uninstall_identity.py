"""Fail closed if an elevated uninstaller does not own the desktop session."""
import os


def _matching_users(current_pid, shell_pid, session_id, user_sid):
    """Require both the same interactive session and the same account SID."""
    if not current_pid or not shell_pid:
        return False
    try:
        current_session=session_id(current_pid)
        shell_session=session_id(shell_pid)
        if current_session is None or current_session!=shell_session:
            return False
        current_sid=user_sid(current_pid)
        shell_sid=user_sid(shell_pid)
        return bool(current_sid and shell_sid and current_sid==shell_sid)
    except (OSError,ValueError,TypeError):
        return False


def current_user_owns_desktop():
    """Return False when the active desktop or either account is unavailable.

    A per-machine uninstaller may run under alternate administrator credentials.
    Do not infer the interactive account from environment variables or names.
    """
    if os.name!='nt':return False
    try:
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        user=ctypes.WinDLL('user32',use_last_error=True)
        security=ctypes.WinDLL('advapi32',use_last_error=True)
        kernel.GetCurrentProcessId.restype=wintypes.DWORD
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        kernel.ProcessIdToSessionId.argtypes=[wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
        kernel.ProcessIdToSessionId.restype=wintypes.BOOL
        kernel.LocalFree.argtypes=[wintypes.HLOCAL];kernel.LocalFree.restype=wintypes.HLOCAL
        user.GetShellWindow.restype=wintypes.HWND
        user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype=wintypes.DWORD
        security.OpenProcessToken.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]
        security.OpenProcessToken.restype=wintypes.BOOL
        security.GetTokenInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
        security.GetTokenInformation.restype=wintypes.BOOL
        security.ConvertSidToStringSidW.argtypes=[ctypes.c_void_p,ctypes.POINTER(wintypes.LPWSTR)]
        security.ConvertSidToStringSidW.restype=wintypes.BOOL

        class SidAndAttributes(ctypes.Structure):
            _fields_=[('sid',ctypes.c_void_p),('attributes',wintypes.DWORD)]
        class TokenUser(ctypes.Structure):
            _fields_=[('user',SidAndAttributes)]

        def session_id(pid):
            result=wintypes.DWORD()
            if not kernel.ProcessIdToSessionId(pid,ctypes.byref(result)):raise OSError('无法读取会话')
            return result.value

        def user_sid(pid):
            process=kernel.OpenProcess(0x1000,False,pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not process:raise OSError('无法读取进程')
            token=wintypes.HANDLE()
            try:
                if not security.OpenProcessToken(process,0x0008,ctypes.byref(token)):raise OSError('无法读取令牌')
                required=wintypes.DWORD()
                security.GetTokenInformation(token,1,None,0,ctypes.byref(required))  # TokenUser
                if not required.value:raise OSError('无法读取账户')
                buffer=ctypes.create_string_buffer(required.value)
                if not security.GetTokenInformation(token,1,buffer,required,ctypes.byref(required)):raise OSError('无法读取账户')
                sid=ctypes.cast(buffer,ctypes.POINTER(TokenUser)).contents.user.sid
                result=wintypes.LPWSTR()
                if not sid or not security.ConvertSidToStringSidW(sid,ctypes.byref(result)):raise OSError('无法读取 SID')
                try:return result.value
                finally:kernel.LocalFree(ctypes.cast(result,wintypes.HLOCAL))
            finally:
                if token:kernel.CloseHandle(token)
                kernel.CloseHandle(process)

        shell=user.GetShellWindow();shell_pid=wintypes.DWORD()
        if not shell or not user.GetWindowThreadProcessId(shell,ctypes.byref(shell_pid)):return False
        return _matching_users(kernel.GetCurrentProcessId(),shell_pid.value,session_id,user_sid)
    except (OSError,ValueError,TypeError,AttributeError):
        return False
