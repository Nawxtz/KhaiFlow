"""T-102 (product board P-001): the secret scan also catches secrets assigned in code."""
import os
import shutil
import subprocess
import tempfile

SCRIPT = os.path.join(os.getcwd(), "scripts", "check_no_secrets.sh")
KEY = "LINE_CHANNEL_" + "SECRET"  # built at run time so this file never matches the scan itself
VALUE = "0123456789abcdef" * 2


def scan(files):
    d = tempfile.mkdtemp()
    try:
        for name, text in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
        # clean env: a shell function named grep in the caller must not change the result
        return subprocess.run(["bash", SCRIPT], cwd=d, env={"PATH": "/usr/bin:/bin"}, capture_output=True).returncode
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_code_assignment_caught():
    assert scan({"x.py": f'{KEY} = "{VALUE}"\n'}) == 1


def test_openrouter_key_shape_caught():
    assert scan({"y.js": 'const k = "sk-or-v1-' + "a" * 32 + '";\n'}) == 1


def test_env_line_still_caught():
    assert scan({"z.env.txt": f"{KEY}={VALUE}\n"}) == 1


def test_clean_tree_not_flagged():
    assert scan({"ok.py": f'{KEY} = os.environ.get("{KEY}", "")\n', "a.example": f"{KEY}={VALUE}\n"}) == 0


def test_short_placeholder_not_flagged():
    assert scan({"p.py": f'{KEY} = "changeme"\n'}) == 0
