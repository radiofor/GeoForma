"""Run tests with the same validated dependencies and native setup as the app."""
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    # Unit tests must not depend on the active Windows desktop or overwrite
    # the user's clipboard. Explicit platform settings still take precedence.
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from main import configure_runtime
    configure_runtime()
    import pytest
    from tools.test_scratch import create_scratch,prune_stale,remove_checked
    from geoforma.resource_lock import try_resource_lock
    args=sys.argv[1:] or [str(ROOT/'tests'),'-q']
    prune_stale(ROOT)
    if any(arg=='--basetemp' or arg.startswith('--basetemp=') for arg in args):return pytest.main(args)
    scratch=create_scratch(ROOT)
    with try_resource_lock(scratch/'.active.lock') as acquired:
        if not acquired:raise RuntimeError('无法锁定测试临时目录。')
        result=pytest.main([*args,'--basetemp',str(scratch/'pytest')])
    # Keep failed runs briefly for investigation; successful runs have no value as fixtures.
    if result==0:
        try:remove_checked(scratch.parent,scratch)
        except (OSError,ValueError):pass
    return result


if __name__=='__main__':raise SystemExit(main())
