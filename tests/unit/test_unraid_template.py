"""Parse and sanity-check the Unraid Community Applications template."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import struct

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "telegram-downloader.xml"
ICON = REPO_ROOT / "templates" / "icon.png"

RAW_BASE = "https://raw.githubusercontent.com/rfsbraz/telegram-downloader/main"
IMAGE = "rfsbraz/telegram-downloader"

REQUIRED_TAGS = (
    "Name",
    "Repository",
    "Registry",
    "Network",
    "Overview",
    "Support",
    "Project",
    "TemplateURL",
    "Icon",
    "Category",
)

REQUIRED_PATHS = {
    "/downloads": "Downloads",
    "/app/.sessions": "Sessions",
}

REQUIRED_VARIABLES = {
    "TDL_API_ID",
    "TDL_API_HASH",
    "TDL_PHONE_NUMBER",
    "TDL_SOURCES_0_URL",
    "TDL_DAEMON_ENABLED",
    "PUID",
    "PGID",
    "TZ",
}

PLACEHOLDER_SNIPPETS = (
    "YOUR_GITHUB_USERNAME",
    "YOUR_PLUGIN_REPO",
    "YOUR_SUPPORT_TOPIC",
    "example-app",
    "container_name",
    "changeme",
)


def _tree() -> ET.ElementTree:
    return ET.parse(TEMPLATE)


def _root() -> ET.Element:
    return _tree().getroot()


def _text(root: ET.Element, tag: str) -> str:
    child = root.find(tag)
    assert child is not None, f"missing <{tag}>"
    return (child.text or "").strip()


def _configs(root: ET.Element) -> list[ET.Element]:
    return root.findall("Config")


def test_template_file_exists():
    assert TEMPLATE.is_file(), f"missing {TEMPLATE.relative_to(REPO_ROOT)}"


def test_template_is_well_formed_xml():
    # A parse error is a failed test, not an error outside pytest.
    ET.parse(TEMPLATE)


def test_root_is_container_version_2():
    root = _root()
    assert root.tag == "Container"
    assert root.attrib.get("version") == "2"


@pytest.mark.parametrize("tag", REQUIRED_TAGS)
def test_required_tag_is_present_and_nonempty(tag):
    value = _text(_root(), tag)
    assert value, f"<{tag}> is empty"


def test_no_starter_placeholders_remain():
    text = TEMPLATE.read_text(encoding="utf-8")
    for snippet in PLACEHOLDER_SNIPPETS:
        assert snippet not in text, f"placeholder {snippet!r} still in the template"


def test_repository_is_the_published_image():
    repository = _text(_root(), "Repository")
    assert repository == IMAGE or repository.startswith(f"{IMAGE}:")


def test_template_url_points_at_this_file():
    assert _text(_root(), "TemplateURL") == f"{RAW_BASE}/templates/telegram-downloader.xml"


def test_icon_url_points_at_repo_png():
    assert _text(_root(), "Icon") == f"{RAW_BASE}/templates/icon.png"


def test_icon_png_exists_and_is_a_png():
    assert ICON.is_file(), "CA templates need a hosted PNG next to the XML"
    data = ICON.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    assert width == height, "CA crops icons in a circle"
    assert width >= 256, f"icon is {width}x{height}, expected at least 256px"


def test_support_and_project_urls():
    root = _root()
    assert _text(root, "Support") == "https://github.com/rfsbraz/telegram-downloader/issues"
    assert _text(root, "Project") == "https://github.com/rfsbraz/telegram-downloader"


def test_not_privileged_and_bridge_network():
    root = _root()
    assert _text(root, "Privileged").lower() == "false"
    assert _text(root, "Network") == "bridge"


def test_has_no_webui():
    webui = _root().find("WebUI")
    assert webui is None or not (webui.text or "").strip()


def test_overview_covers_first_run_auth():
    overview = _text(_root(), "Overview")
    lowered = overview.lower()
    assert "login" in lowered or "authentica" in lowered
    assert "one-shot" in lowered or "one shot" in lowered
    assert "console" in lowered
    assert overview.endswith("https://my.telegram.org/apps")


def test_required_paths_are_mapped():
    configs = {cfg.attrib.get("Target"): cfg for cfg in _configs(_root()) if cfg.attrib.get("Type") == "Path"}
    for target, name in REQUIRED_PATHS.items():
        cfg = configs.get(target)
        assert cfg is not None, f"missing Path config for {target}"
        assert cfg.attrib.get("Name") == name
        assert cfg.attrib.get("Mode") == "rw"
        assert cfg.attrib.get("Required") == "true"
        assert (cfg.attrib.get("Default") or "").startswith("/mnt/user/")


def test_required_variables_are_present():
    variables = {
        cfg.attrib.get("Target"): cfg
        for cfg in _configs(_root())
        if cfg.attrib.get("Type") == "Variable"
    }
    missing = REQUIRED_VARIABLES - variables.keys()
    assert missing == set(), f"missing variables: {sorted(missing)}"


def test_secrets_are_masked():
    variables = {
        cfg.attrib.get("Target"): cfg
        for cfg in _configs(_root())
        if cfg.attrib.get("Type") == "Variable"
    }
    assert variables["TDL_API_HASH"].attrib.get("Mask") == "true"
    assert variables["TDL_API_ID"].attrib.get("Mask") == "false"


def test_unraid_puid_pgid_defaults():
    variables = {
        cfg.attrib.get("Target"): cfg
        for cfg in _configs(_root())
        if cfg.attrib.get("Type") == "Variable"
    }
    assert variables["PUID"].attrib.get("Default") == "99"
    assert variables["PGID"].attrib.get("Default") == "100"


def test_daemon_mode_defaults_on():
    variables = {
        cfg.attrib.get("Target"): cfg
        for cfg in _configs(_root())
        if cfg.attrib.get("Type") == "Variable"
    }
    assert variables["TDL_DAEMON_ENABLED"].attrib.get("Default") == "true"


def _unknown_keys(data, model, prefix: str = "") -> list[str]:
    problems = []
    for key, value in data.items():
        field = model.model_fields.get(key)
        if field is None:
            problems.append(f"{prefix}{key}")
            continue
        annotation = field.annotation
        args = getattr(annotation, "__args__", ())
        from pydantic import BaseModel

        nested = next(
            (
                a
                for a in (annotation, *args)
                if isinstance(a, type) and issubclass(a, BaseModel)
            ),
            None,
        )
        if nested and isinstance(value, dict):
            problems += _unknown_keys(value, nested, f"{prefix}{key}.")
        elif nested and isinstance(value, list):
            for i, item in enumerate(value):
                problems += _unknown_keys(item, nested, f"{prefix}{key}[{i}].")
    return problems


def test_tdl_variables_are_read_by_the_loader(monkeypatch):
    import os

    from src.config.loader import _load_from_env
    from src.config.schema import Config

    variables = [
        cfg.attrib.get("Target")
        for cfg in _configs(_root())
        if cfg.attrib.get("Type") == "Variable"
        and (cfg.attrib.get("Target") or "").startswith("TDL_")
    ]
    assert variables, "template has no TDL_ variables"
    for key in list(os.environ):
        if key.startswith("TDL_"):
            monkeypatch.delenv(key)
    for name in variables:
        monkeypatch.setenv(name, "1")
    data = _load_from_env()
    assert _unknown_keys(data, Config) == [], f"unmapped TDL vars: {variables}"


def docker_run_preview(root: ET.Element | None = None) -> str:
    """Build a docker run command from template defaults (for a dry render)."""
    if root is None:
        root = _root()
    repository = _text(root, "Repository")
    lines = ["docker run --rm -it"]
    for cfg in _configs(root):
        kind = cfg.attrib.get("Type")
        target = cfg.attrib.get("Target") or ""
        default = cfg.attrib.get("Default") or ""
        required = cfg.attrib.get("Required") == "true"
        name = cfg.attrib.get("Name") or target
        if kind == "Path":
            host = default or f"<host-path-for-{name}>"
            mode = cfg.attrib.get("Mode") or "rw"
            lines.append(f"-v {host}:{target}:{mode}")
        elif kind == "Variable":
            value = default
            if not value and required:
                value = f"YOUR_{target}"
            if value:
                lines.append(f"-e {target}={value}")
    lines.append(repository)
    return " \\\n  ".join(lines)


def test_blank_optional_variables_would_still_load(monkeypatch):
    """Unraid exports blank optional fields as VAR=''. That must still validate."""
    import os

    from pydantic import ValidationError

    from src.config.loader import _load_from_env
    from src.config.schema import Config

    for key in list(os.environ):
        if key.startswith("TDL_"):
            monkeypatch.delenv(key)
    for cfg in _configs(_root()):
        if cfg.attrib.get("Type") != "Variable":
            continue
        target = cfg.attrib.get("Target") or ""
        if not target.startswith("TDL_"):
            continue
        value = cfg.attrib.get("Default") or ""
        if not value and cfg.attrib.get("Required") == "true":
            if target == "TDL_API_ID":
                value = "12345"
            elif target.endswith("_URL"):
                value = "https://t.me/example"
            else:
                value = "placeholder"
        monkeypatch.setenv(target, value)
    try:
        Config.model_validate(_load_from_env())
    except ValidationError as exc:
        raise AssertionError(
            "A template variable with an empty default would fail startup "
            "when Unraid exports it as an empty string"
        ) from exc


def test_docker_run_preview_includes_volumes_and_image():
    preview = docker_run_preview()
    assert "/downloads" in preview
    assert "/app/.sessions" in preview
    assert IMAGE in preview
    assert "TDL_API_ID" in preview
    assert "TDL_DAEMON_ENABLED=true" in preview


if __name__ == "__main__":
    print(docker_run_preview())
