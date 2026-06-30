from __future__ import annotations

import hashlib
import argparse
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
import utils.sts_naming as sts_naming

import logging

log_dir = Path("log/")
log_dir.mkdir(exist_ok=True)

logger = logging.getLogger("IndexBuilder")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()

formatter = logging.Formatter(
    "%(asctime)s %(levelname)-8s %(message)s"
)

# timestamp prefix for file name
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"{timestamp}_index_builder.log"

# File: DEBUG and above
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Terminal: INFO and above
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime REAL,
    size INTEGER,
    file_hash TEXT
);
"""


# ----------------------------
# DB utilities
# ----------------------------
def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn

def upsert(conn: sqlite3.Connection, path: str, mtime: float, size: int, file_hash:str) -> None:
    conn.execute(
        """
        INSERT INTO files(path, mtime, size, file_hash)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            mtime=excluded.mtime,
            size=excluded.size,
            file_hash=excluded.file_hash
        """,
        (path, mtime, size, file_hash),
    )

def get_all_files(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT path FROM files")
    return [r[0] for r in cur.fetchall()]

def delete(conn: sqlite3.Connection, path: str) -> None:
    conn.execute("DELETE FROM files WHERE path = ?", (path,))


# ----------------------------
# Remote indexing
# ----------------------------
def valid_path(path: str, remote_root: str) -> bool:
    p = Path(path)
    root = Path(remote_root)

    try:
        rel = p.relative_to(root)
    except Exception:
        return False

    parts = rel.parts

    if len(parts) != 4:
        return False

    ladder, module, folder, filename = parts

    if not sts_naming.is_valid_label(ladder, sts_naming.LADDER_NAME_PATTERN):
        return False

    if not sts_naming.is_valid_module_name(module):
        return False

    # Folder structure check
    if folder != "pscan_files":
        return False

    # Filename structure check
    expected = f"module_test_{module}.txt"
    if filename != expected:
        return False

    return True

def fetch_remote_files_batched(
    host: str, remote_root: str
) -> list[tuple[str, float, int, str]]:
    """
    Single SSH call:
    returns [(path, mtime, size), ...]
    """

    # cmd = [
    #     "ssh",
    #     host,
    #     # -type f: files only
    #     # -printf: full path + mtime + size
    #     f"find {remote_root} -type f -name 'module_test_*.txt' -printf '%p %T@ %s\\n'"
    # ]
    script = f"""
    find "{remote_root}" -type f -name 'module_test_*.txt' -print0 |
    while IFS= read -r -d '' f; do
        hash=$(sha256sum "$f" | cut -d' ' -f1)
        mtime=$(stat -c '%Y' "$f")
        size=$(stat -c '%s' "$f")
        printf "%s|%s|%s|%s\\n" "$f" "$mtime" "$size" "$hash"
    done
    """
    
    cmd = ["ssh", host, "bash -s"]

    result = subprocess.run(
        cmd,
        input=script,
        text=True,
        capture_output=True,
        check=True
    )

    out = []
    for line in result.stdout.splitlines():
        try:
            path, mtime, size, h = line.split("|")
            out.append((path, float(mtime), int(size), h))
        except ValueError:
            continue

    return out


def sync_and_filter_from_db(
    conn: sqlite3.Connection,
    host: str,
    remote_root: str,
) -> list[str]:
    logger.info("Re-syncronizing DB ...")
    
    remote_files = fetch_remote_files_batched(host, remote_root)

    valid_files = []
    updated = 0

    for path, mtime, size, hash in remote_files:
        # local structural validation only
        if not valid_path(path, remote_root):
            continue

        row = conn.execute(
            "SELECT file_hash FROM files WHERE path = ?",
            (path,),
        ).fetchone()

        # insert / update if new or changed
        if row is None or row[0] != hash:
            upsert(conn, path, mtime, size, hash)
            updated += 1

        valid_files.append(path)

    logger.info(f"Listed files: {len(remote_files)}")
    logger.info(f"Updated files: {updated}")
    
    conn.commit()
    return valid_files


# ----------------------------
# Index builder
# ----------------------------
def build_index(host: str, remote_root: str, db_path: str) -> None:
    """
    Build SQLite index from remote filesystem.
    """
    conn = init_db(db_path)

    logger.info(f"Scanning remote: {host}:{remote_root}")
    file_stats = fetch_remote_files_batched(host, remote_root)
    logger.info(f"Found {len(file_stats)} files")

    for path, mtime, size, hash in file_stats:
        logger.debug(f"{mtime}\t{size}\t{path}")
        upsert(conn, path, mtime, size, hash)

    conn.commit()
    conn.close()

    logger.info("Index build complete")


# ----------------------------
# CLI
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="Build module test file index")

    parser.add_argument("--path", help="Base path to the module test folders")

    parser.add_argument(
        "--host",
        default=None,
        help="SSH host (if omitted, provided path is assumed local)",
    )

    parser.add_argument(
        "--db",
        default="module_test/file_index.db",
        help="Data base for files index (avoid file ssytem scanning)",
    )

    parser.add_argument(
        "--sync",
        action="store_true",
        help="Synchronize the existing database with the remote filesystem",
    )

    args = parser.parse_args()

    if args.sync:
        conn = init_db(args.db)
        sync_and_filter_from_db(conn, args.host, args.path)
    else:
        build_index(args.host, args.path, args.db)


if __name__ == "__main__":
    main()
