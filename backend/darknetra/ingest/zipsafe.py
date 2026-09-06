import stat
from pathlib import PurePosixPath


class ZipUnsafe(ValueError):
    pass


def safe_members(archive, max_bytes=500 * 1024 * 1024):
    members = archive.infolist()
    if len(members) > 2000:
        raise ZipUnsafe("ZIP_MEMBER_LIMIT")
    total = 0
    for member in members:
        name = member.filename.replace("\\", "/")
        if name.startswith("/") or ":" in name or ".." in PurePosixPath(name).parts:
            raise ZipUnsafe("ZIP_UNSAFE_PATH")
        if stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1:
            raise ZipUnsafe("ZIP_UNSAFE_MEMBER")
        total += member.file_size
        if total > max_bytes or member.file_size > max(1, member.compress_size) * 100:
            raise ZipUnsafe("ZIP_SIZE_LIMIT")
        if PurePosixPath(name).suffix.lower() in {".zip", ".rar", ".7z", ".tar", ".gz"}:
            raise ZipUnsafe("ZIP_NESTED_ARCHIVE")
    return members
