"""Only identified, inactive test scratch can be removed."""
import os,time
import pytest
from geoforma.resource_lock import try_resource_lock
from tools.clean_build_scratch import clean
from tools.test_scratch import create_scratch,prune_stale,remove_checked


def old(path):os.utime(path,(time.time()-8*86400,)*2)


def test_legacy_build_cleanup_only_deletes_recognized_old_fixture_trees(tmp_path):
    build=tmp_path/'build';build.mkdir()
    fixture=build/'old-tests'/'test_sample0';fixture.mkdir(parents=True);(fixture/'data').write_text('fixture');old(fixture.parent)
    recent=build/'recent-tests'/'test_sample0';recent.mkdir(parents=True);(recent/'data').write_text('recent')
    mixed=build/'audit'/'test_case0';mixed.mkdir(parents=True);(mixed.parent/'report.json').write_text('report');old(mixed.parent)
    release=tmp_path/'release'/'product.msix';release.parent.mkdir();release.write_text('package')
    preview=clean(tmp_path);assert len(preview['targets'])==1 and fixture.exists()
    applied=clean(tmp_path,apply=True);assert len(applied['targets'])==1 and not fixture.exists()
    assert recent.exists() and (mixed.parent/'report.json').exists() and release.exists()


def test_only_owned_unlocked_old_managed_scratch_is_pruned(tmp_path):
    first=create_scratch(tmp_path);second=create_scratch(tmp_path);fresh=create_scratch(tmp_path)
    old(first/'.geoforma-owned');old(second/'.geoforma-owned')
    with try_resource_lock(second/'.active.lock') as acquired:
        assert acquired
        # The first stale directory needs an existing lock marker too.
        (first/'.active.lock').write_bytes(b'0')
        assert prune_stale(tmp_path)==[first.name]
        assert not first.exists() and second.exists() and fresh.exists()
    assert prune_stale(tmp_path)==[second.name] and not second.exists()
    assert fresh.exists()


def test_prefix_restricts_scratch_cleanup(tmp_path):
    build=tmp_path/'build';build.mkdir()
    selected=build/'task-tests-01'/'test_sample0';selected.mkdir(parents=True)
    other=build/'other-tests-01'/'test_sample0';other.mkdir(parents=True)
    result=clean(tmp_path,apply=True,older_hours=0,prefixes=('task-tests-',))
    assert len(result['targets'])==1 and not selected.exists() and other.exists()


def test_recursive_cleanup_rejects_root_and_outside_targets(tmp_path):
    folder=tmp_path/'owned';folder.mkdir();outside=tmp_path/'other';outside.mkdir()
    with pytest.raises(ValueError):remove_checked(folder,folder)
    with pytest.raises(ValueError):remove_checked(folder,outside)
    assert folder.exists() and outside.exists()
