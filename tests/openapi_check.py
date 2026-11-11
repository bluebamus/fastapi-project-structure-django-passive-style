"""응답을 앱이 광고하는 OpenAPI 스키마와 대조한다.

정본은 ``main.app`` 의 ``app.openapi()`` 다.
검사기는 이 저장소 스키마가 쓰는 부분(``$ref``·``anyOf``·``type``·``required``·``properties``·``items``)만
본다 — 새 의존성(jsonschema)을 들이지 않는다.
"""

from __future__ import annotations

from functools import cache
from typing import Any

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


@cache
def spec() -> dict[str, Any]:
    from main import app

    return app.openapi()


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = spec()["components"]["schemas"][name]
    return schema


def errors(schema: dict[str, Any], value: Any, where: str = "$") -> list[str]:
    schema = _resolve(schema)
    if "anyOf" in schema:
        options = [errors(option, value, where) for option in schema["anyOf"]]
        return [] if any(not found for found in options) else [f"{where}: anyOf 불일치 {value!r}"]
    kind = schema.get("type")
    if kind is None:
        return []
    if isinstance(value, bool) and kind in ("integer", "number"):
        return [f"{where}: {kind} 자리에 bool"]
    if not isinstance(value, _TYPES[kind]):
        return [f"{where}: {kind} 가 아니다 ({type(value).__name__})"]
    found: list[str] = []
    if kind == "object":
        found += [
            f"{where}.{key}: 필수 누락" for key in schema.get("required", []) if key not in value
        ]
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                found += errors(sub, value[key], f"{where}.{key}")
    if kind == "array":
        for index, item in enumerate(value):
            found += errors(schema.get("items", {}), item, f"{where}[{index}]")
    return found
