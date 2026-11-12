"""Make a zip of the finance tracker that can be sent to someone else.

Run from the project folder:
    python make_package.py               # code only (recommended)
    python make_package.py --with-data   # also include the raw export and the built database

The zip holds the code, the dashboard, the tests, requirements.txt, HOW_TO_RUN.md and the one-click
setup and run scripts (setup.bat / run.bat for Windows, setup.sh / run.sh for Mac and Linux).
It never includes the virtual environment (venv), notebooks, backups or uploaded files.
By default it also leaves out the data, because the export lists payments to named people.
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "finance_tracker_package.zip"
TOP = "finance_tracker"
SKIP_DIRS = {"venv", ".venv", "env", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "notebooks", "data", ".git", "backups", "uploads"}
REQUIRED = ["config.py", "parser.py", "build_database.py", "model_runs.py", "dashboard/app.py", "tests/test_pipeline.py",
            "requirements.txt", "HOW_TO_RUN.md", "check_setup.py", "setup.bat", "run.bat", "setup.sh", "run.sh"]


def wanted(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts[:-1]) or path.name == OUT.name:
        return False
    return path.suffix not in {".pyc", ".db", ".xls", ".zip", ".bak"} and not path.name.startswith(".~")


def main():
    with_data = "--with-data" in sys.argv
    missing = [r for r in REQUIRED if not (ROOT / r).exists()]
    if missing:
        sys.exit("Cannot make the package. These files are missing from the project folder: " + ", ".join(missing))
    files = [p for p in sorted(ROOT.rglob("*")) if p.is_file() and wanted(p)]
    if with_data:
        files += [p for p in sorted((ROOT / "data").glob("*")) if p.is_file() and p.suffix in {".xls", ".db"}]
    OUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo.from_file(p, f"{TOP}/{p.relative_to(ROOT).as_posix()}")
            info.compress_type = zipfile.ZIP_DEFLATED
            if p.suffix == ".sh":
                info.external_attr = 0o755 << 16                          # so ./setup.sh runs on Mac and Linux
            elif p.suffix in {".bat", ".md", ".txt", ".py", ".ini"}:
                z.writestr(info, p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") if p.suffix == ".bat" else p.read_bytes())
                continue
            z.writestr(info, p.read_bytes())
    print(f"Wrote {OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB) with {len(files)} files:")
    for p in files:
        print("  ", p.relative_to(ROOT).as_posix())
    if not with_data:
        print("\nThe data was left out on purpose. He can load his own export from the dashboard's 'Update data' tab.")


if __name__ == "__main__":
    main()
