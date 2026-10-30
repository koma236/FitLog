"""Private local immutable objects; no user paths or symlink traversal."""
import errno
import fcntl
import hashlib
import heapq
import os
import re
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings

from media_assets.exceptions import ImageError

MAX_OBJECT_BYTES = 5 * 1024 * 1024
KEY_PATTERN = re.compile(r"[a-f0-9]{32}\.(?:jpg|png)", re.ASCII)
TEMP_PATTERN = re.compile(r"\.upload-[a-f0-9]{32}\.tmp", re.ASCII)
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


@dataclass(frozen=True)
class StoredObject:
    key: str
    modified_at: datetime


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        if settings.FITLOG_ENV != "local" or settings.PRIVATE_MEDIA_BACKEND != "local":
            raise ImageError(503, "STORAGE_UNAVAILABLE")
        self.root = Path(settings.PRIVATE_MEDIA_ROOT if root is None else root).absolute()

    @contextmanager
    def _directory(self) -> Iterator[int]:
        """Open each component without following symlinks, pin root for the operation."""
        descriptor = -1
        try:
            descriptor = os.open(self.root.anchor, DIRECTORY_FLAGS)
            for part in self.root.parts[1:]:
                if part in (".", ".."):
                    raise ImageError(503, "STORAGE_UNAVAILABLE")
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            # Repair existing named-volume roots through the pinned descriptor only.
            # Ancestors can be shared and must never have their permissions changed.
            root_info = os.fstat(descriptor)
            if root_info.st_uid != os.geteuid():
                raise ImageError(503, "STORAGE_UNAVAILABLE")
            if stat.S_IMODE(root_info.st_mode) != 0o700:
                os.fchmod(descriptor, 0o700)
            yield descriptor
        except OSError:
            raise ImageError(503, "STORAGE_UNAVAILABLE") from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _validate_key(key: str) -> None:
        if not KEY_PATTERN.fullmatch(key):
            raise ImageError(503, "STORAGE_UNAVAILABLE")

    @staticmethod
    def _read_at(directory: int, key: str) -> bytes:
        descriptor = os.open(key, READ_FLAGS, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OBJECT_BYTES:
                raise ImageError(503, "STORAGE_UNAVAILABLE")
            data = handle.read(MAX_OBJECT_BYTES + 1)
            if len(data) > MAX_OBJECT_BYTES:
                raise ImageError(503, "STORAGE_UNAVAILABLE")
            return data

    def put_if_absent(self, key: str, data: bytes, digest: str) -> None:
        self._validate_key(key)
        if len(data) > MAX_OBJECT_BYTES or hashlib.sha256(data).hexdigest() != digest:
            raise ImageError(503, "STORAGE_UNAVAILABLE")
        with self._directory() as directory:
            temporary = ".upload-" + uuid.uuid4().hex + ".tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 mode=0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    fcntl.flock(handle, fcntl.LOCK_EX)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                    try:
                        # Atomic publication without the overwrite behavior of rename.
                        os.link(temporary, key, src_dir_fd=directory, dst_dir_fd=directory,
                                follow_symlinks=False)
                    except FileExistsError:
                        existing = self._read_at(directory, key)
                        if hashlib.sha256(existing).hexdigest() != digest:
                            raise ImageError(503, "STORAGE_UNAVAILABLE") from None
                    os.fsync(directory)
            finally:
                os.unlink(temporary, dir_fd=directory)

    def read(self, key: str) -> bytes:
        self._validate_key(key)
        with self._directory() as directory:
            try:
                return self._read_at(directory, key)
            except FileNotFoundError:
                raise ImageError(404, "NOT_FOUND") from None

    def delete(self, key: str) -> None:
        self._validate_key(key)
        with self._directory() as directory:
            try:
                info = os.stat(key, dir_fd=directory, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise ImageError(503, "STORAGE_UNAVAILABLE")
                os.unlink(key, dir_fd=directory)
                os.fsync(directory)
            except FileNotFoundError:
                pass

    def list_page(self, cursor: str | None = None, limit: int = 100,
                  ) -> tuple[list[StoredObject], str | None]:
        if cursor is not None:
            self._validate_key(cursor)
        if not 1 <= limit <= 1000:
            raise ImageError(503, "STORAGE_UNAVAILABLE")
        with self._directory() as directory, os.scandir(directory) as entries:
            # Only one bounded page is retained, even when many objects exist.
            keys = heapq.nsmallest(limit + 1, (
                entry.name for entry in entries
                if KEY_PATTERN.fullmatch(entry.name) and (cursor is None or entry.name > cursor)
            ))
            objects = []
            for key in keys[:limit]:
                try:
                    info = os.stat(key, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    continue  # Concurrent deletes are revisited on the next full sweep.
                if not stat.S_ISREG(info.st_mode):
                    raise ImageError(503, "STORAGE_UNAVAILABLE")
                objects.append(StoredObject(key, datetime.fromtimestamp(info.st_mtime, UTC)))
            return objects, keys[limit - 1] if len(keys) > limit else None

    def sweep_temporary(self, before: datetime) -> int:
        """Reap old abandoned temp files; flock protects live synchronous writers."""
        if before.utcoffset() is None:
            raise ImageError(503, "STORAGE_UNAVAILABLE")
        cutoff = min(before, datetime.now(UTC) - timedelta(hours=1)).timestamp()
        removed = 0
        with self._directory() as directory, os.scandir(directory) as entries:
            for entry in entries:
                if not TEMP_PATTERN.fullmatch(entry.name):
                    continue
                try:
                    descriptor = os.open(entry.name, READ_FLAGS, dir_fd=directory)
                except FileNotFoundError:
                    continue
                with os.fdopen(descriptor, "rb") as handle:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError as error:
                        if error.errno in (errno.EAGAIN, errno.EACCES):
                            continue
                        raise
                    info = os.fstat(handle.fileno())
                    if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff:
                        os.unlink(entry.name, dir_fd=directory)
                        removed += 1
            if removed:
                os.fsync(directory)
        return removed
