import json
from pathlib import Path

import pytest

from location_component import _BUILD_DIR, validate_frontend_assets


def test_location_component_frontend_build_is_packaged():
    validated = validate_frontend_assets()
    assert (_BUILD_DIR / "index.html") in validated
    assert (_BUILD_DIR / "asset-manifest.json") in validated
    assert (_BUILD_DIR / "component.css") in validated


def test_location_component_manifest_references_existing_files():
    manifest = json.loads((_BUILD_DIR / "asset-manifest.json").read_text(encoding="utf-8"))
    assert manifest["entrypoints"]
    for relative_path in manifest["files"].values():
        candidate = _BUILD_DIR / str(relative_path).removeprefix("./")
        assert candidate.is_file(), relative_path
        assert candidate.stat().st_size > 0


def test_location_component_index_references_packaged_bundle():
    html = (_BUILD_DIR / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((_BUILD_DIR / "asset-manifest.json").read_text(encoding="utf-8"))
    main_js = manifest["files"]["main.js"]
    assert main_js in html
    assert (_BUILD_DIR / main_js.removeprefix("./")).is_file()


def test_location_component_validation_fails_clearly_when_assets_are_missing(tmp_path: Path):
    (tmp_path / "asset-manifest.json").write_text(
        json.dumps({"files": {"main.js": "./static/js/missing.js"}}),
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "component.css").write_text("body{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="não foram incluídos na publicação"):
        validate_frontend_assets(tmp_path)
