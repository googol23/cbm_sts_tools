"""
inspect_dtl_db.py

Utilities to inspect the STS-related tables in the DTL PostgreSQL database.

Features:
- Connects to the DTL DB in read-only mode using psycopg2.
- lists tables and columns in a given schema.
- Prints column info and sample rows for a given table.
- Ladder utilities:
    * get_ladder_modules: return ordered module names for a ladder.
    * get_module_sensor: map a module ID to its sensor name.
    * get_sensors_size: compute ladder length in Y including sensor overlap.
"""

from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np

from .sensor_type import STS_SENSOR_SIZE, SensorType

# --- Database connection helpers ----------------------------------------------
def get_conn() -> psycopg2.extensions.connection:
    """
    Create a read-only PostgreSQL connection.

    Returns
    -------
    psycopg2.extensions.connection
        An open psycopg2 connection using RealDictCursor.

    """

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "pgsql.gsi.de"),
            port=os.getenv("DB_PORT", "8646"),
            dbname=os.getenv("DB_NAME", "dtl"),
            user=os.getenv("DB_USER", "dtl_read"),
            password=os.getenv("DB_PASSWORD", "SFVZkz3FsuDRBfpZ5OVc"),
            cursor_factory=RealDictCursor,
            connect_timeout=10,
        )
        return conn
    except Exception as e:
        raise RuntimeError(f"Failed to connect to DB: {e}")


# --- Introspection utilities --------------------------------------------------
def list_tables(conn: psycopg2.extensions.connection, schema: str = "public") -> list[str]:
    """
    list all base tables in the given schema.

    Parameters
    ----------
    conn
        Open psycopg2 connection.
    schema
        Schema name. Default: "public".

    Returns
    -------
    list of str
        Fully qualified table names, e.g. "public.sts_module".
    """
    sql = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema,))
        return [f"{r['table_schema']}.{r['table_name']}" for r in cur.fetchall()]

def list_columns_for_table(
    conn: psycopg2.extensions.connection,
    schema: str,
    table: str,
) -> list[dict]:
    """
    list columns and data types for the given table.

    Parameters
    ----------
    conn
        Open psycopg2 connection.
    schema
        Schema name.
    table
        Table name (without schema).

    Returns
    -------
    list of dict
        Each dict has keys: "column_name", "data_type".
    """
    sql = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        return cur.fetchall()

def inspect_table(
    table_name: str = "public.sts_sensor",
    limit: int = 10,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> None:
    """
    Print column info and a few example rows from the given table.

    Parameters
    ----------
    table_name
        Fully qualified table name, e.g. "public.sts_module".
    limit
        Maximum number of rows to print.
    conn
        Optional existing database connection. If None, a new connection
        is created and closed inside this function.
    """
    close_conn = False
    if conn is None:
        conn = get_conn()
        close_conn = True

    schema, _, table = table_name.partition(".")
    if not schema or not table:
        raise ValueError(f"table_name must be 'schema.table', got: {table_name!r}")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Show schema (column names + types)
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (schema, table),
            )

            print(f"Columns in {schema}.{table}:")
            for row in cur.fetchall():
                print(f"  {row['column_name']:25} {row['data_type']}")

            # 2. Show sample data
            cur.execute(f"SELECT * FROM {schema}.{table} LIMIT %s;", (limit,))
            rows = cur.fetchall()
            print(f"\nSample {min(limit, len(rows))} row(s):")
            for r in rows:
                print(r)
    finally:
        if close_conn:
            conn.close()


# --- Ladder / module helpers --------------------------------------------------
def sort_ladder_modules(modules: list[str]) -> list[str]:
    """
    Sort ladder modules from top to bottom.

    Naming convention (assumed):
      - modules[5] = 'T' → top half (sorted descending by position)
      - modules[5] = 'B' → bottom half (sorted ascending by position)
      - position is a single digit at index 6
      - malformed entries go last, order among them preserved

    Parameters
    ----------
    modules
        list of module identifiers.

    Returns
    -------
    list of str
        Sorted module identifiers.
    """

    def custom_key(m: str) -> tuple[int, int]:
        side = m[5] if len(m) > 5 else ""
        try:
            pos = int(m[6]) if len(m) > 6 else 100
        except ValueError:
            pos = 100

        if side == "T":
            return (0, -pos)  # top half, reversed
        elif side == "B":
            return (1, pos)   # bottom half, normal
        else:
            return (2, 0)     # malformed → last

    return sorted(modules, key=custom_key)

def get_ladder_modules(
    ladder_id: str,
    conn: Optional[psycopg2.extensions.connection] = None,
    sorted: bool = True,
) -> list[str]:
    """
    Return list of module names for the given ladder_id.

    The query picks the maximum version digit inside the module name and
    reconstructs the name with that version.

    Parameters
    ----------
    ladder_id
        Ladder identifier (sts_module.ladder_name).
    conn
        Optional open connection. If None, a new connection is created
        and closed inside this function.
    sorted
        If True, modules are sorted top-to-bottom using sort_ladder_modules.

    Returns
    -------
    list of str
        Module names for this ladder.
    """
    close_conn = False
    if conn is None:
        conn = get_conn()
        close_conn = True

    sql = """
        SELECT
            MAX(substring(name, 8, 1)) AS version,
            overlay(name, '0', 8, 1)   AS name_new
        FROM sts_module
        WHERE ladder_name = %s
        GROUP BY name_new;
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (ladder_id,))
            rows = cur.fetchall()

        modules: list[str] = []
        for r in rows:
            base = r["name_new"]
            version = r["version"]
            # Replace the version digit at index 7 with the actual version.
            modules.append(base[:7] + version + base[8:])

        return sort_ladder_modules(modules) if sorted else modules
    finally:
        if close_conn:
            conn.close()

def get_module_sensor(
    module_id: str,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> Optional[str]:
    """
    Return sensor name for a given module ID.

    Parameters
    ----------
    module_id
        Module identifier (sts_module.name).
    conn
        Optional open connection. If None, a new connection is created
        and closed inside this function.

    Returns
    -------
    str or None
        Sensor name if found, otherwise None.
    """
    close_conn = False
    if conn is None:
        conn = get_conn()
        close_conn = True

    sql = """
        SELECT sensor_name
        FROM public.sts_module
        WHERE name = %s;
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (module_id,))
            row = cur.fetchone()
            return row["sensor_name"] if row else None
    finally:
        if close_conn:
            conn.close()

def get_sensors_size(
    ladder_id: str,
    conn: psycopg2.extensions.connection | None = None,
) -> list[tuple[float, float]]:
    """
    Return the list of (X, Y) sensor sizes (in mm) for all modules in a ladder.

    Returns
    -------
    list[tuple[float, float]]
        Each tuple is (size_x_mm, size_y_mm) for one sensor, in ladder order.
    """
    close_conn = False
    if conn is None:
        from .db_api import get_conn  # avoid circular import
        conn = get_conn()
        close_conn = True

    sql = """
        SELECT get_sensor_size_mm(sts_module.sensor_name::smallint) AS size_xy
        FROM public.sts_module
        WHERE ladder_name = %s;
    """

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (ladder_id,))
            rows = cur.fetchall()

        sizes: list[tuple[float, float]] = []

        for row in rows:
            # Example assumption:
            # DB returns something like "62x42" or "(62,42)" or "XY=62,42"
            # Your earlier code extracted Y via size[3:], but we now parse both.
            raw = str(row["size_xy"]).strip()

            # Try to extract numbers in a robust but simple way
            nums = [float(n) for n in "".join(
                ch if (ch.isdigit() or ch == '.') else " "
                for ch in raw
            ).split()]

            if len(nums) != 2:
                raise ValueError(f"Could not parse sensor size from DB string: {raw!r}")

            sx, sy = nums
            sizes.append((sx, sy))

        return sizes

    finally:
        if close_conn:
            conn.close()

def get_latest_modules_for_ladder(ladder_name: str, conn: psycopg2.extensions.connection | None = None) -> list[str]:
    """
    Keep only the latest version of each module.
    Version is the 8th character in the name.
    """
    sql = """
        SELECT
            MAX(substring(name, 8, 1)) AS version,
            overlay(name, '0', 8, 1) AS name_base
        FROM public.sts_module
        WHERE ladder_name = %s
        GROUP BY name_base;
    """
    if conn is None:
        conn = get_conn()
    
    with conn.cursor() as cur:
        cur.execute(sql, (ladder_name,))
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"No modules found for ladder {ladder_name}.")

    modules: list[str] = []
    for r in rows:
        base = r["name_base"]
        version = r["version"]
        if not base or not version:
            raise ValueError(f"Invalid module data: {r}")
        if len(base) < 8:
            raise ValueError(f"Module name too short: {base}")
        modules.append(base[:7] + version + base[8:])

    return modules

def list_ladder_names(conn) -> list[str]:
    sql = "SELECT name FROM public.sts_ladder ORDER BY name;"
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    if not rows:
        raise ValueError("No ladder names found in DB.")
    return [r["name"] for r in rows]

if __name__ == "__main__":
    """
    Example usage when run as a script.

    - Takes an optional ladder ID as the first argument.
    - Prints modules and ladder size in Y.
    """
    ladder_id = sys.argv[1] if len(sys.argv) > 1 else "L4DL000161"

    try:
        conn = get_conn()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    try:
       
        # Uncomment for ad-hoc inspection:
        for table_name in list_tables(conn):
            if "sts_module" in table_name:
                inspect_table(table_name=table_name, limit=1, conn=conn)

        ladder_names = list_ladder_names(conn)
        print(ladder_names)
    finally:
        conn.close()

# 'public.access_logs'
# 'public.smx_adc_calib'
# 'public.smx_csa_calib'
# 'public.smx_id'
# 'public.smx_on_wafer_test'
# 'public.smx_wafer'
# 'public.sts_chart_data_tmp'
# 'public.sts_comments'
# 'public.sts_feb8'
# 'public.sts_feb8_comments'
# 'public.sts_feb8_status'
# 'public.sts_ladder'
# 'public.sts_ladder_comments'
# 'public.sts_ladder_old'
# 'public.sts_ladder_status'
# 'public.sts_microcable'
# 'public.sts_module'
# 'public.sts_module_comments'
# 'public.sts_module_status'
# 'public.sts_module_test_list'
# 'public.sts_positions'
# 'public.sts_sensor'
# 'public.sts_sensor_comments'
# 'public.sts_sensor_status'
# 'public.sts_sensor_table'
# 'public.sts_sites'
# 'public.sts_user'