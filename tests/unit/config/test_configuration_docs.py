"""
Every TDL_* variable named in docs/configuration.md must reach a real
config field through the env loader. A name the loader does not map is
silently dropped, so a wrong name in the docs fails here instead.
"""
import os
import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.config.loader import _load_from_env
from src.config.schema import Config

DOC = Path(__file__).resolve().parents[3] / "docs" / "configuration.md"

# Date filter names are being fixed in #95; drop these once it merges.
KNOWN_DATE_FILTER_NAMES = {
    "TDL_SOURCES_0_FILTERS_MIN_DATE",
    "TDL_SOURCES_0_FILTERS_MAX_DATE",
}


def documented_env_vars() -> list[str]:
    names = set()
    for line in DOC.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            names.update(re.findall(r"`(TDL_[A-Z0-9_]+)`", stripped))
        else:
            match = re.match(r"-\s+(TDL_[A-Z0-9_]+)=", stripped)
            if match:
                names.add(match.group(1))
    # TDL_SOURCES_N_* in tables means any index
    return sorted({n.replace("_N_", "_0_") for n in names} - KNOWN_DATE_FILTER_NAMES)


def unknown_keys(data, model: type[BaseModel], prefix: str = "") -> list[str]:
    """Keys in a loader dict that are not fields on the pydantic model."""
    problems = []
    for key, value in data.items():
        field = model.model_fields.get(key)
        if field is None:
            problems.append(f"{prefix}{key}")
            continue
        annotation = field.annotation
        args = getattr(annotation, "__args__", ())
        nested = next(
            (a for a in (annotation, *args) if isinstance(a, type) and issubclass(a, BaseModel)),
            None,
        )
        if nested and isinstance(value, dict):
            problems += unknown_keys(value, nested, f"{prefix}{key}.")
        elif nested and isinstance(value, list):
            for i, item in enumerate(value):
                problems += unknown_keys(item, nested, f"{prefix}{key}[{i}].")
    return problems


def test_docs_name_some_env_vars():
    assert len(documented_env_vars()) > 20


@pytest.mark.parametrize("name", documented_env_vars())
def test_documented_env_var_is_read_by_loader(name, monkeypatch):
    for key in list(os.environ):
        if key.startswith("TDL_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv(name, "1")

    data = _load_from_env()

    assert unknown_keys(data, Config) == [], f"{name} is not read by the loader"
