"""Проверка ответов API по контракту ``contracts/openapi/beauty.yaml``.

Схемы компонентов OpenAPI 3.1 — это JSON Schema 2020-12: валидатор получает весь
документ как ресурс реестра, поэтому ``$ref`` внутри контракта разрешаются как есть.
Расхождение реализации с контрактом роняет интеграционный тест.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "beauty.yaml"
_URI = "urn:beauty:contract"


@cache
def _registry() -> Registry[Any]:
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return Registry().with_resource(_URI, Resource.from_contents(document, default_specification=DRAFT202012))


def assert_matches_schema(instance: Any, schema_name: str) -> None:
    """Проверить JSON по схеме ``#/components/schemas/<schema_name>``."""
    validator = Draft202012Validator(
        {"$ref": f"{_URI}#/components/schemas/{schema_name}"},
        registry=_registry(),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)
