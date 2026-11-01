"""Keep exception diagnostics in logs and plain messages in editing panels."""
import re


def user_message(diagnostic):
    lines=str(diagnostic).strip().splitlines()
    line=lines[-1] if lines else '操作未完成，请重试。'
    return re.sub(r'^[A-Za-z][\w.]*(?:Error|Exception):\s*','',line)
