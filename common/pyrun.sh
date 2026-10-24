#!/usr/bin/env bash
# Run a Python script with the project's Python environment. uv is optional.
# Usage: common/pyrun.sh <script.py> [args...]
#        common/pyrun.sh --check        # show which Python is used and check the packages
# The first of these that exists is used:
#   1. $ACS_PYTHON                  an interpreter you name, e.g. ACS_PYTHON=/opt/py/bin/python
#   2. $VIRTUAL_ENV/bin/python      an activated venv
#   3. <repo>/.venv/bin/python      a venv made with "python3 -m venv .venv" + pip, or by "uv sync"
#   4. uv run                       only if uv is installed; it creates .venv from uv.lock
#   5. python3 on PATH              system Python with the packages installed
set -eu
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${ACS_PYTHON:-}" ]]; then py=("$ACS_PYTHON"); how="ACS_PYTHON"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then py=("$VIRTUAL_ENV/bin/python"); how="active venv"
elif [[ -x "$REPO/.venv/bin/python" ]]; then py=("$REPO/.venv/bin/python"); how="repo .venv"
elif command -v uv >/dev/null 2>&1; then py=(uv run --quiet --project "$REPO" python); how="uv"
elif command -v python3 >/dev/null 2>&1; then py=(python3); how="python3 on PATH"
else echo "pyrun: no Python found. Create a venv first (see README, section 1)." >&2; exit 1
fi

if [[ "${1:-}" == --check ]]; then
  echo "python via $how: ${py[*]}"
  exec "${py[@]}" - <<'EOF'
import sys
print("python", sys.version.split()[0], "at", sys.executable)
if sys.version_info < (3, 13):
    print("warning: the project is tested with Python 3.13 or newer", file=sys.stderr)
missing = []
for m in ("numpy", "pandas", "matplotlib", "scipy"):
    try:
        __import__(m)
    except ImportError:
        missing.append(m)
if missing:
    sys.exit("missing Python packages: " + " ".join(missing)
             + "\ninstall them in the venv: python -m pip install numpy pandas matplotlib scipy")
print("packages ok: numpy pandas matplotlib scipy")
EOF
fi

[[ $# -ge 1 ]] || { echo "usage: $0 <script.py> [args...] | --check" >&2; exit 1; }
exec "${py[@]}" "$@"
