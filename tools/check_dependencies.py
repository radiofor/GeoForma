"""Validate dependency metadata under the same runtime as the source app."""
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def require_consistent_dependencies():
    result=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:
        details=(result.stdout+'\n'+result.stderr).strip()
        raise ValueError('运行依赖不一致，请修复后重新构建。'+('\n'+details if details else ''))
    return result.stdout.strip()


def main():
    sys.path.insert(0,str(ROOT))
    from main import configure_runtime
    configure_runtime()
    print(require_consistent_dependencies())


if __name__=='__main__':main()
