from family_ai_api.members import cli
from family_ai_api.members.store import MemberStore, hash_token


def test_member_store_crud_and_auth(tmp_path) -> None:
    store = MemberStore(tmp_path / "members.db")
    try:
        member, token = store.add("alice", "member")
        assert member.name == "alice"
        assert member.role == "member"
        assert not member.revoked
        assert store.authenticate(token).id == member.id
        assert store.authenticate("wrong") is None
        assert store.count() == 1

        rotated = store.rotate("alice")
        assert rotated is not None
        assert store.authenticate(token) is None
        assert store.authenticate(rotated).id == member.id

        assert store.revoke("alice") is True
        assert store.authenticate(rotated) is None
        assert store.revoke("alice") is False
        assert store.get("alice").revoked is True
        assert store.rotate("missing") is None
    finally:
        store.close()


def test_member_store_rejects_duplicates(tmp_path) -> None:
    store = MemberStore(tmp_path / "members.db")
    try:
        store.add("alice", "member", "token-a")
        try:
            store.add("alice", "member", "token-b")
        except ValueError:
            pass
        else:
            raise AssertionError("expected duplicate name error")

        try:
            store.add("bob", "member", "token-a")
        except ValueError:
            pass
        else:
            raise AssertionError("expected duplicate token error")

        try:
            store.add("bad", "owner")
        except ValueError:
            pass
        else:
            raise AssertionError("expected invalid role error")
    finally:
        store.close()


def test_bootstrap_admin_only_when_missing(tmp_path) -> None:
    store = MemberStore(tmp_path / "members.db")
    try:
        store.add("alice", "member", "alice-token")
        store.ensure_bootstrap("legacy-token")
        assert store.count() == 2
        assert store.authenticate("legacy-token").name == "admin"

        store.ensure_bootstrap("another-token")
        assert store.count() == 2
        assert store.authenticate("another-token") is None
    finally:
        store.close()


def test_hash_token_is_stable() -> None:
    assert hash_token("test-token") == hash_token("test-token")
    assert hash_token("test-token") != hash_token("other-token")


def test_cli_create_list_rotate_revoke(tmp_path, capsys) -> None:
    db = str(tmp_path / "members.db")

    assert cli.main(["--db", db, "create", "--name", "alice"]) == 0
    created = capsys.readouterr().out
    token = created.split("token (shown once): ")[1].strip()
    assert "alice" in created

    assert cli.main(["--db", db, "list"]) == 0
    listed = capsys.readouterr().out
    assert "alice" in listed
    assert "member" in listed

    assert cli.main(["--db", db, "rotate", "--name", "alice"]) == 0
    rotated = capsys.readouterr().out.split("(shown once): ")[1].strip()
    assert rotated != token

    store = MemberStore(db)
    try:
        assert store.authenticate(token) is None
        assert store.authenticate(rotated).name == "alice"
    finally:
        store.close()

    assert cli.main(["--db", db, "revoke", "--name", "alice"]) == 0
    assert "revoked" in capsys.readouterr().out

    store = MemberStore(db)
    try:
        assert store.authenticate(rotated) is None
    finally:
        store.close()

    assert cli.main(["--db", db, "revoke", "--name", "alice"]) == 1
