"""Tests for scripts/schema.py — available-year detection."""

import scripts.schema as schema_module


def test_available_years_empty(tmp_path, monkeypatch):
    """No Parquet files → empty list."""
    monkeypatch.setattr(schema_module, "PARQUET_DIR", tmp_path)
    manifest = {"years": {"2024": {}, "2023": {}}}
    assert schema_module._available_years(manifest) == []


def test_available_years_some_files(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_module, "PARQUET_DIR", tmp_path)
    (tmp_path / "BRFSS_2024.parquet").touch()
    (tmp_path / "BRFSS_2022.parquet").touch()
    manifest = {"years": {"2024": {}, "2023": {}, "2022": {}}}
    result = schema_module._available_years(manifest)
    assert result == ["2024", "2022"]


def test_available_years_sorted_descending(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_module, "PARQUET_DIR", tmp_path)
    for y in ["2020", "2022", "2021"]:
        (tmp_path / f"BRFSS_{y}.parquet").touch()
    manifest = {"years": {"2020": {}, "2021": {}, "2022": {}}}
    result = schema_module._available_years(manifest)
    assert result == ["2022", "2021", "2020"]


def test_available_years_ignores_years_not_in_manifest(tmp_path, monkeypatch):
    """A Parquet file for a year not in the manifest should not be returned."""
    monkeypatch.setattr(schema_module, "PARQUET_DIR", tmp_path)
    (tmp_path / "BRFSS_2024.parquet").touch()
    (tmp_path / "BRFSS_2019.parquet").touch()  # not in manifest
    manifest = {"years": {"2024": {}}}
    result = schema_module._available_years(manifest)
    assert result == ["2024"]


def test_available_years_all_present(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_module, "PARQUET_DIR", tmp_path)
    for y in ["2022", "2023", "2024"]:
        (tmp_path / f"BRFSS_{y}.parquet").touch()
    manifest = {"years": {"2022": {}, "2023": {}, "2024": {}}}
    result = schema_module._available_years(manifest)
    assert result == ["2024", "2023", "2022"]
