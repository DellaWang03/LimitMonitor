import hashlib
import os
from pathlib import Path
import platform
import subprocess

import pytest

from scripts import run_frozen_baseline as runner


@pytest.mark.skipif(platform.system() != "Darwin", reason="requires macOS sandbox-exec")
def test_real_sandbox_allows_only_output_and_denies_loopback(tmp_path: Path) -> None:
    sandbox_exec = Path("/usr/bin/sandbox-exec")
    assert sandbox_exec.is_file(), "macOS 缺少 /usr/bin/sandbox-exec"
    allow = tmp_path / "allow"
    output = allow / "run"
    allow.mkdir()
    output.mkdir()
    (output / "home").mkdir()
    (output / "tmp").mkdir()
    profile_sha = hashlib.sha256(runner.SANDBOX_PROFILE.read_bytes()).hexdigest()
    profile_text = runner.SANDBOX_PROFILE.read_text(encoding="utf-8")
    assert "(allow sysctl-read)" in profile_text
    assert '(allow file-write* (literal "/dev/null"))' in profile_text
    assert "(allow network" not in profile_text
    env = {
        "ENV": "test",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": str(output / "home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LIMIT_MONITOR_PROFILE": "local",
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": str(output / "tmp"),
    }
    command = [
        str(sandbox_exec),
        "-D",
        f"OUTPUT_ROOT={output.resolve()}",
        "-f",
        str(runner.SANDBOX_PROFILE),
        "/opt/homebrew/bin/python3",
        str(runner.RUNNER_PATH),
        "--sandbox-probe-only",
        "--allow-output-root",
        str(allow),
        "--output-root",
        str(output),
        "--sandbox-profile",
        str(runner.SANDBOX_PROFILE),
        "--sandbox-profile-sha256",
        profile_sha,
    ]

    completed = subprocess.run(command, cwd=runner.PROJECT_ROOT, env=env, check=False)

    assert completed.returncode == 0
    assert not any(path.name.startswith(".outside-write-probe-") for path in allow.iterdir())
