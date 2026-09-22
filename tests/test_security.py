from pathlib import Path

import pytest

from eregistry.security import AuthStore


def test_password_and_recovery_round_trip(tmp_path: Path):
    store = AuthStore(tmp_path / "auth.json")
    master, recovery = store.setup("correct horse battery staple")
    assert store.unlock("correct horse battery staple") == master
    with pytest.raises(ValueError):
        store.unlock("wrong")
    recovered = store.reset_with_recovery(recovery, "new password")
    assert recovered == master
    assert store.unlock("new password") == master
