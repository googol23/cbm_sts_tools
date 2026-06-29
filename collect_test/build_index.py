from __future__ import annotations

import argparse
import sqlite3
import subprocess
from pathlib import Path

import utils.sts_naming as sts_naming


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime REAL,
    size INTEGER
);
"""


# ----------------------------
# DB utilities
# ----------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, path: str, mtime: float, size: int) -> None:
    conn.execute(
        """
        INSERT INTO files(path, mtime, size)
        VALUES (?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            mtime=excluded.mtime,
            size=excluded.size
        """,
        (path, mtime, size),
    )

def get_all_files(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT path FROM files")
    return [r[0] for r in cur.fetchall()]

def delete(conn: sqlite3.Connection, path: str) -> None:
    conn.execute("DELETE FROM files WHERE path = ?", (path,))

def db_module_test_files(
    conn: sqlite3.Connection,
    host: str,
    remote_root: str,
    check=False
) -> list[str]:

    db_files = get_all_files(conn)

    valid_files = []

    for path in db_files:
        # still enforce correctness (robustness layer)
        if not valid_path(path, remote_root):
            continue

        # consistency check → update DB if changed
        if check:
            try:
                mtime, size = fetch_remote_stat(host, path)
            except Exception:
                delete(conn, path)
                continue
    
            cur = conn.execute(
                "SELECT mtime, size FROM files WHERE path = ?",
                (path,)
            )
            row = cur.fetchone()
    
            if row is None:
                upsert(conn, path, mtime, size)
            else:
                old_mtime, old_size = row
                if old_mtime != mtime or old_size != size:
                    upsert(conn, path, mtime, size)

        valid_files.append(path)

    conn.commit()
    return valid_files
    
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
    
def fetch_remote_files(host: str, remote_root: str) -> list[str]:
    """
    Uses SSH + remote find to list target files.
    Requires SSH keys configured (no password handling here).
    """

    cmd = [
        "ssh",
        host,
        f"find {remote_root} -type f -name 'module_test_*.txt'",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    files =  [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    return [ f for f  in files if valid_path(f, remote_root)]

def fetch_remote_stat(host: str, path: str) -> tuple[float, int]:
    """
    Get mtime and size for a single file.
    """

    cmd = [
        "ssh",
        host,
        f"stat -c '%Y %s' {path}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    mtime, size = result.stdout.strip().split()
    return float(mtime), int(size)

def fetch_remote_files_batched(host: str, remote_root: str) -> list[tuple[str, float, int]]:
    """
    Single SSH call:
    returns [(path, mtime, size), ...]
    """

    cmd = [
        "ssh",
        host,
        # -type f: files only
        # -printf: full path + mtime + size
        f"find {remote_root} -type f -name 'module_test_*.txt' "
        f"-printf '%p %T@ %s\\n'",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    out = []
    for line in result.stdout.splitlines():
        try:
            path, mtime, size = line.rsplit(" ", 2)
            out.append((path, float(mtime), int(size)))
        except ValueError:
            continue

    return out

def sync_and_filter_from_db(
    conn: sqlite3.Connection,
    host: str,
    remote_root: str,
) -> list[str]:

    remote_files = fetch_remote_files_batched(host, remote_root)

    valid_files = []

    for path, mtime, size in remote_files:

        # local structural validation only
        if not valid_path(path, remote_root):
            continue

        row = conn.execute(
            "SELECT mtime, size FROM files WHERE path = ?",
            (path,),
        ).fetchone()

        # insert / update if new or changed
        if row is None:
            upsert(conn, path, mtime, size)
        else:
            old_mtime, old_size = row
            if old_mtime != mtime or old_size != size:
                upsert(conn, path, mtime, size)

        valid_files.append(path)

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

    print(f"Scanning remote: {host}:{remote_root}")
    files = fetch_remote_files(host, remote_root)
    print(f"Found {len(files)} files")

    for i, f in enumerate(files, 1):
        try:
            mtime, size = fetch_remote_stat(host, f)
        except Exception:
            continue

        upsert(conn, f, mtime, size)

        if i % 500 == 0:
            conn.commit()
            print(f"Indexed {i}/{len(files)}")

    conn.commit()
    conn.close()

    print("Index build complete")


# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description="Build module test file index")

    parser.add_argument("host", help="SSH host (uses ~/.ssh/config if needed)")
    parser.add_argument("remote_root", help="Remote test_result directory")
    parser.add_argument("--db", default="collect_test/file_index.db")

    args = parser.parse_args()

    build_index(args.host, args.remote_root, args.db)


if __name__ == "__main__":
    main()