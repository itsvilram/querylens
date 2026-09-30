"""Load BIRD mini-dev into its own database, bird_eval, next to Pagila.

Needs: `docker compose up -d db` and `python -m scripts.download_bird` first.
Run from api/:  uv run python -m scripts.load_bird

The dump's "ALTER ... OWNER TO xiaolongli" lines name a user we don't have,
so we drop them on the way in. Any other error stops the load (ON_ERROR_STOP).
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DUMP = REPO / "data" / "bird" / "BIRD_dev.sql"
SETUP_SQL = REPO / "db" / "bird" / "setup.sql"
DB = "bird_eval"


def psql(*args: str, database: str = "postgres") -> list[str]:
    env_arg = (
        f"QUERYLENS_BIRD_RO_PASSWORD={os.environ.get('QUERYLENS_BIRD_RO_PASSWORD', 'bird_ro_dev')}"
    )
    return [
        "docker", "compose", "exec", "-T", "-e", env_arg, "db",
        "psql", "-U", "postgres", "-d", database, "-X", "-q", "-v", "ON_ERROR_STOP=1", *args,
    ]  # fmt: skip


def run(command: list[str]) -> str:
    return subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True).stdout


def main() -> None:
    if not DUMP.exists():
        sys.exit("Missing data/bird/BIRD_dev.sql: run `python -m scripts.download_bird` first.")

    exists = run(psql("-tAc", "SELECT 1 FROM pg_database WHERE datname = 'bird_eval'")).strip()
    if exists:
        sys.exit(
            "Database bird_eval already exists. To reload, first run: DROP DATABASE bird_eval;"
        )
    run(psql("-c", "CREATE DATABASE bird_eval"))

    print(f"loading {DUMP.name} ({DUMP.stat().st_size / 1e6:.0f} MB) into {DB} ...")
    skipped = 0
    loader = subprocess.Popen(psql(database=DB), cwd=REPO, stdin=subprocess.PIPE)
    if loader.stdin is None:
        sys.exit("Could not open a pipe to psql.")
    with DUMP.open("rb") as dump:
        for line in dump:
            if b" OWNER TO " in line and line.startswith(b"ALTER "):
                skipped += 1
                continue
            loader.stdin.write(line)
    loader.stdin.close()
    if loader.wait() != 0:
        sys.exit("psql failed while loading the dump (see the error above).")
    print(f"loaded (skipped {skipped} OWNER TO lines)")

    with SETUP_SQL.open("rb") as setup:
        subprocess.run(psql(database=DB), cwd=REPO, stdin=setup, check=True)
    tables = run(
        psql("-tAc", "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'", database=DB)
    )
    print(f"bird_ro ready; {tables.strip()} tables in {DB}")


if __name__ == "__main__":
    main()
