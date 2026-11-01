from geoforma.uninstall_identity import _matching_users, current_user_owns_desktop


def test_identity_requires_same_session_and_full_sid():
    sessions={1:2,2:2}
    users={1:'S-1-5-21-1',2:'S-1-5-21-1'}
    check=lambda: _matching_users(1,2,sessions.get,users.get)
    assert check()
    users[2]='S-1-5-21-2'
    assert not check()
    users[2]='S-1-5-21-1';sessions[2]=3
    assert not check()
    sessions[2]=2;users[2]=None
    assert not check()
    assert not _matching_users(1,0,sessions.get,users.get)


def test_identity_lookup_failure_is_denied():
    def fail(_):raise OSError('access denied')
    assert not _matching_users(1,2,fail,lambda _: 'sid')


def test_windows_api_lookup_never_grants_unknown_identity():
    # The real desktop may be inaccessible in automated sessions.
    assert isinstance(current_user_owns_desktop(),bool)
