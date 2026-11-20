"""El diagnóstico no filtra secretos ni la carpeta del usuario."""

from __future__ import annotations

import zipfile
from pathlib import Path

from miky import diagnostics


def test_la_config_sale_sin_la_clave(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[ai]\napi_key = "dpapi:AKJSDHASKJDHASKJHD"\nmodel = "gemini-3.5-flash-lite"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(diagnostics.paths, "config_file", lambda: config)
    monkeypatch.setattr(diagnostics.paths, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(diagnostics.paths, "ipc_root", lambda: tmp_path / "ipc")

    destination = tmp_path / "diag.zip"
    path = diagnostics.collect(destination)
    assert path == destination and destination.exists()

    with zipfile.ZipFile(destination) as archive:
        text = archive.read(
            next(name for name in archive.namelist() if name.endswith("config-sin-clave.toml"))
        ).decode("utf-8")
    assert "dpapi:" not in text
    assert "<oculta>" in text
    assert 'model = "gemini-3.5-flash-lite"' in text


def test_el_diagnostico_incluye_lo_basico(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics.paths, "config_file", lambda: tmp_path / "no.toml")
    monkeypatch.setattr(diagnostics.paths, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(diagnostics.paths, "ipc_root", lambda: tmp_path / "ipc")

    destination = diagnostics.collect(tmp_path / "diag.zip")
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
    assert any(name.endswith("info.txt") for name in names)
    assert any(name.endswith("doctor.txt") for name in names)
    assert any("dispositivos" in name for name in names)


def test_no_filtra_la_carpeta_del_usuario(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics.paths, "config_file", lambda: tmp_path / "no.toml")
    monkeypatch.setattr(diagnostics.paths, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(diagnostics.paths, "ipc_root", lambda: tmp_path / "ipc")
    monkeypatch.setattr(diagnostics.Path, "home", classmethod(lambda cls: Path("C:/Users/Tester")))

    destination = diagnostics.collect(tmp_path / "diag.zip")
    with zipfile.ZipFile(destination) as archive:
        info = archive.read(next(n for n in archive.namelist() if n.endswith("info.txt"))).decode()
    assert "C:/Users/Tester" not in info
    assert "C:\\Users\\Tester" not in info
