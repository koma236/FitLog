"""Local adapter contract; synthetic bytes only, dedicated temporary roots."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from media_assets.exceptions import ImageError
from media_assets.storage import LocalStorage

KEY = "a" * 32 + ".png"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_create_duplicate_is_immutable_and_missing_delete_is_success(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path / "private")
    store.put_if_absent(KEY, b"first", digest(b"first"))
    path = tmp_path / "private" / KEY
    inode = path.stat().st_ino
    store.put_if_absent(KEY, b"first", digest(b"first"))
    assert path.stat().st_ino == inode
    with pytest.raises(ImageError) as caught:
        store.put_if_absent(KEY, b"other", digest(b"other"))
    assert (caught.value.status, caught.value.code) == (503, "STORAGE_UNAVAILABLE")
    assert store.read(KEY) == b"first"
    store.delete(KEY)
    store.delete(KEY)
    with pytest.raises(ImageError) as missing:
        store.read(KEY)
    assert (missing.value.status, missing.value.code) == (404, "NOT_FOUND")


@pytest.mark.parametrize("key", ["../outside", "/tmp/outside", "a/b", "a" * 32 + ".svg",
                                 "A" * 32 + ".jpg", "a" * 32 + ".png\x00"])
def test_all_operations_reject_user_paths(tmp_path: Path, key: str) -> None:
    store = LocalStorage(tmp_path)
    for operation in (lambda: store.read(key), lambda: store.delete(key),
                      lambda: store.put_if_absent(key, b"x", digest(b"x"))):
        with pytest.raises(ImageError) as caught:
            operation()
        assert (caught.value.status, caught.value.code) == (503, "STORAGE_UNAVAILABLE")


def test_symlink_objects_and_roots_never_follow_or_delete_outside(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"secret")
    root = tmp_path / "private"
    root.mkdir()
    (root / KEY).symlink_to(outside)
    store = LocalStorage(root)
    for operation in (lambda: store.read(KEY), lambda: store.delete(KEY),
                      lambda: store.put_if_absent(KEY, b"new", digest(b"new"))):
        with pytest.raises(ImageError):
            operation()
    assert outside.read_bytes() == b"secret"
    assert (root / KEY).is_symlink()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ImageError):
        LocalStorage(alias).read(KEY)
    with pytest.raises(ImageError):
        LocalStorage(alias / "nested").put_if_absent(KEY, b"new", digest(b"new"))
    assert not (root / "nested").exists()


def test_read_is_bounded_and_put_digest_verified(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    (tmp_path / KEY).write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ImageError) as caught:
        store.read(KEY)
    assert caught.value.code == "STORAGE_UNAVAILABLE"
    store.delete(KEY)
    with pytest.raises(ImageError):
        store.put_if_absent(KEY, b"x", digest(b"other"))
    assert not (tmp_path / KEY).exists()


def test_page_cursor_only_lists_managed_files_and_aware_times(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    keys = [f"{i:032x}.png" for i in range(5)]
    for key in reversed(keys):
        store.put_if_absent(key, key.encode(), digest(key.encode()))
    (tmp_path / "unrelated").write_text("do not collect")
    seen: list[str] = []
    cursor = None
    while True:
        objects, cursor = store.list_page(cursor, 2)
        assert len(objects) <= 2
        assert all(obj.modified_at.utcoffset() is not None for obj in objects)
        seen.extend(obj.key for obj in objects)
        if cursor is None:
            break
    assert seen == keys
    assert (tmp_path / "unrelated").read_text() == "do not collect"


def test_concurrent_put_same_key_exposes_one_complete_object(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    barrier = Barrier(2)
    values = [b"a" * 100_000, b"b" * 100_000]
    def write(value: bytes) -> str:
        barrier.wait()
        try:
            store.put_if_absent(KEY, value, digest(value))
            return "success"
        except ImageError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, values))
    assert sorted(outcomes) == ["STORAGE_UNAVAILABLE", "success"]
    assert store.read(KEY) in values
    assert sorted(path.name for path in tmp_path.iterdir()) == [KEY]


def test_temporary_sweep_cannot_touch_active_writer(tmp_path: Path) -> None:
    import fcntl
    store = LocalStorage(tmp_path)
    old = datetime.now(UTC) - timedelta(hours=2)
    inactive = tmp_path / (".upload-" + "b" * 32 + ".tmp")
    active = tmp_path / (".upload-" + "c" * 32 + ".tmp")
    for path in (inactive, active):
        path.write_bytes(b"synthetic partial")
        os.utime(path, (old.timestamp(), old.timestamp()))
    with active.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert store.sweep_temporary(datetime.now(UTC) - timedelta(hours=1)) == 1
        assert active.exists()
        assert not inactive.exists()
    assert store.sweep_temporary(datetime.now(UTC) - timedelta(hours=1)) == 1


def test_write_failure_does_not_publish_partial_bytes_or_leave_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic unavailable")
    monkeypatch.setattr(os, "link", unavailable)
    with pytest.raises(ImageError) as caught:
        LocalStorage(tmp_path).put_if_absent(KEY, b"content", digest(b"content"))
    assert (caught.value.status, caught.value.code) == (503, "STORAGE_UNAVAILABLE")
    assert list(tmp_path.iterdir()) == []


def test_unknown_write_outcome_can_be_resolved_by_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = os.link
    def finish_then_fail(
        src: str, dst: str, *, src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None, follow_symlinks: bool = True,
    ) -> None:
        link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
             follow_symlinks=follow_symlinks)
        raise OSError("synthetic completion response lost")
    monkeypatch.setattr(os, "link", finish_then_fail)
    store = LocalStorage(tmp_path)
    with pytest.raises(ImageError) as caught:
        store.put_if_absent(KEY, b"complete", digest(b"complete"))
    assert caught.value.code == "STORAGE_UNAVAILABLE"
    assert store.read(KEY) == b"complete"
    assert sorted(path.name for path in tmp_path.iterdir()) == [KEY]


def test_put_holds_temporary_lock_until_atomic_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = os.link
    store = LocalStorage(tmp_path)
    old = datetime.now(UTC) - timedelta(hours=2)
    def sweep_during_publication(
        src: str, dst: str, *, src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None, follow_symlinks: bool = True,
    ) -> None:
        os.utime(src, (old.timestamp(), old.timestamp()), dir_fd=src_dir_fd)
        assert store.sweep_temporary(datetime.now(UTC) - timedelta(hours=1)) == 0
        link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
             follow_symlinks=follow_symlinks)
    monkeypatch.setattr(os, "link", sweep_during_publication)
    store.put_if_absent(KEY, b"complete", digest(b"complete"))
    assert store.read(KEY) == b"complete"
    assert sorted(path.name for path in tmp_path.iterdir()) == [KEY]


def test_existing_root_becomes_private_without_changing_parent_permissions(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    root = parent / "private"
    root.mkdir(parents=True)
    parent.chmod(0o755)
    root.chmod(0o755)
    before = parent.stat().st_mode & 0o7777
    LocalStorage(root).put_if_absent(KEY, b"content", digest(b"content"))
    assert root.stat().st_mode & 0o7777 == 0o700
    assert parent.stat().st_mode & 0o7777 == before


def test_root_with_unexpected_owner_is_unavailable_without_changing_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "private"
    root.mkdir()
    root.chmod(0o755)
    monkeypatch.setattr(os, "geteuid", lambda: root.stat().st_uid + 1)
    with pytest.raises(ImageError) as caught:
        LocalStorage(root).put_if_absent(KEY, b"content", digest(b"content"))
    assert (caught.value.status, caught.value.code) == (503, "STORAGE_UNAVAILABLE")
    assert root.stat().st_mode & 0o7777 == 0o755
    assert list(root.iterdir()) == []
