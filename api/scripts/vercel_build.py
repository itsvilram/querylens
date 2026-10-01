"""Vercel build step: build the Vue app and put it where the API serves it from.

Vercel runs this from api/ (see [tool.vercel.scripts] in pyproject.toml) after
installing the Python packages. It builds web/ and copies the result to
api/frontend/; app/main.py then serves it with app.frontend(), and Vercel moves
those files to its CDN. Locally the Vite dev server is used instead.

    python scripts/vercel_build.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
WEB = API.parent / "web"
TARGET = API / "frontend"


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    # shell=True on Windows only: npm is a .cmd file there.
    subprocess.run(command, cwd=WEB, check=True, shell=sys.platform == "win32")


def main() -> None:
    run("npm", "ci", "--no-audit", "--no-fund")
    run("npm", "run", "build-only")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(WEB / "dist", TARGET)
    print(f"frontend copied to {TARGET.relative_to(API.parent)}", flush=True)


if __name__ == "__main__":
    main()
