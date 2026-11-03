"""T-051 (C-1): backend/ ships models.py so the parser imports with only backend files; sync script covers it."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.getcwd()


def _isolated(files):
    d = tempfile.mkdtemp()
    for f in files:
        shutil.copy(os.path.join(ROOT, "backend", f), d)
    return d


def test_parser_imports_with_only_backend_files():
    d = _isolated(["parser.py", "geo_engine.py", "constants.py", "models.py"])
    r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r); import parser" % d],
                       cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_backend_models_identical_to_root():
    assert open(os.path.join(ROOT, "backend", "models.py"), "rb").read() == open(os.path.join(ROOT, "models.py"), "rb").read()


def test_sync_script_lists_models_and_catches_drift():
    assert '"models.py"' in open(os.path.join(ROOT, "scripts", "check_parser_sync.sh")).read()
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "backend"))
    os.makedirs(os.path.join(tmp, "scripts"))
    shutil.copy(os.path.join(ROOT, "scripts", "check_parser_sync.sh"), os.path.join(tmp, "scripts"))
    for f in ["parser.py", "geo_engine.py", "constants.py", "models.py"]:
        shutil.copy(os.path.join(ROOT, f), tmp)
        shutil.copy(os.path.join(ROOT, "backend", f), os.path.join(tmp, "backend"))
    ok = subprocess.run(["bash", "scripts/check_parser_sync.sh"], cwd=tmp, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout
    with open(os.path.join(tmp, "backend", "models.py"), "a") as fh:
        fh.write("\n# drift\n")
    bad = subprocess.run(["bash", "scripts/check_parser_sync.sh"], cwd=tmp, capture_output=True, text=True)
    assert bad.returncode != 0 and "models.py" in bad.stdout


def test_other_mirrors_still_identical():
    for f in ["parser.py", "geo_engine.py", "constants.py"]:
        assert open(os.path.join(ROOT, f), "rb").read() == open(os.path.join(ROOT, "backend", f), "rb").read()
