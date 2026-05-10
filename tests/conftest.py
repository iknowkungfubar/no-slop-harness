"""Shared test fixtures."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture()
def sample_python_file(tmp_dir: Path):
    path = tmp_dir / "sample.py"
    path.write_text('def hello():\n    return "world"\n')
    return path


@pytest.fixture()
def git_repo(tmp_path: Path):
    """Minimal git repo with one commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    return tmp_path
