from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import zipfile

import pytest


def test_core_metadata_keeps_report_renderer_optional():
    project_root = Path(__file__).resolve().parents[1]
    metadata = (project_root / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dependencies = []' in metadata
    assert 'report = ["reportlab>=4.0"]' in metadata
    assert 'all = ["reportlab>=4.0", "playwright>=1.49"]' in metadata


def test_core_wheel_build_has_no_reportlab_runtime_requirement(tmp_path):
    pytest.importorskip("setuptools.build_meta")
    project_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
            str(project_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(tmp_path.glob("research_engine-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        metadata_path = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_path).decode("utf-8")
    report_requirements = [
        line for line in metadata.splitlines() if line.startswith("Requires-Dist: reportlab")
    ]
    assert report_requirements
    assert all('extra == "report"' in line or 'extra == "all"' in line for line in report_requirements)
    assert "Provides-Extra: report" in metadata
    assert "Provides-Extra: browser" in metadata
    assert "Provides-Extra: all" in metadata
