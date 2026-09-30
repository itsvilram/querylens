"""Download the BIRD mini-dev files we need, and nothing else.

BIRD mini-dev (https://github.com/bird-bench/mini_dev) is licensed CC BY-SA 4.0.
We never commit it: this script puts it in data/bird/ (git-ignored).

The official zip is 800 MB because it holds SQLite, MySQL and PostgreSQL copies.
A zip keeps its table of contents at the end, so with HTTP range requests we
read that table and then only the files we need (~230 MB). zipfile checks
each file's CRC32 as we read it, so a broken download fails loudly.

Run from api/:  uv run python -m scripts.download_bird
"""

import io
import urllib.request
import zipfile
from pathlib import Path

ZIP_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "bird"

# zip path -> local path (relative to DATA_DIR)
FILES = {
    "minidev/MINIDEV/mini_dev_postgresql.json": "mini_dev_postgresql.json",
    "minidev/MINIDEV/dev_tables.json": "dev_tables.json",
    "minidev/MINIDEV_postgresql/BIRD_dev.sql": "BIRD_dev.sql",
}
DESCRIPTIONS_PREFIX = (
    "minidev/MINIDEV/dev_databases/"  # .../<db_id>/database_description/<table>.csv
)


class RemoteFile(io.RawIOBase):
    """A read-only, seekable file whose bytes come from HTTP range requests."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._pos = 0
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=60) as response:
            self._size = int(response.headers["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = base + offset
        return self._pos

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        if self._pos >= self._size:
            return 0
        end = min(self._pos + len(buffer), self._size) - 1
        request = urllib.request.Request(self._url, headers={"Range": f"bytes={self._pos}-{end}"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        buffer[: len(data)] = data
        self._pos += len(data)
        return len(data)


def _extract(archive: zipfile.ZipFile, member: str, target: Path) -> None:
    if target.exists() and target.stat().st_size == archive.getinfo(member).file_size:
        print(f"  have      {target.relative_to(DATA_DIR)}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    size = archive.getinfo(member).file_size
    with archive.open(member) as source, partial.open("wb") as out:
        done = 0
        while chunk := source.read(8 << 20):
            out.write(chunk)
            done += len(chunk)
            print(f"\r  download  {target.relative_to(DATA_DIR)}  {done / size:5.1%}", end="")
    partial.replace(target)  # only complete files get their real name
    print()


def main() -> None:
    print(f"BIRD mini-dev -> {DATA_DIR}")
    remote = io.BufferedReader(RemoteFile(ZIP_URL), buffer_size=8 << 20)
    with zipfile.ZipFile(remote) as archive:
        for member, local in FILES.items():
            _extract(archive, member, DATA_DIR / local)
        for member in archive.namelist():
            if member.startswith(DESCRIPTIONS_PREFIX) and member.endswith(".csv"):
                db_id, _, table_file = member.removeprefix(DESCRIPTIONS_PREFIX).split("/")
                _extract(archive, member, DATA_DIR / "descriptions" / db_id / table_file)
    print("done. Licence: CC BY-SA 4.0 (https://github.com/bird-bench/mini_dev)")


if __name__ == "__main__":
    main()
