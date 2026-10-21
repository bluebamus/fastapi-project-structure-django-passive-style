"""응답을 앱이 광고하는 OpenAPI 스키마와 대조한다.

``DEBUG=false`` 로 띄운 e2e 서버는 ``/openapi.json`` 을 내지 않는다 — 같은 코드로 조립한 앱의
``app.openapi()`` 를 정본으로 쓴다(스키마는 설정값에 따라 달라지지 않는다).
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


@cache
def operations() -> dict[str, tuple[str, str]]:
    """operationId → (METHOD, path)."""
    return {
        op["operationId"]: (method.upper(), path)
        for path, item in spec()["paths"].items()
        for method, op in item.items()
    }


def path_methods(path: str) -> set[str]:
    return {m.upper() for m in spec()["paths"][path]}


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


def response_errors(operation_id: str, status: int, body: Any) -> list[str]:
    """그 operation 의 ``status`` 응답 스키마와 ``body`` 의 차이. 스키마가 없으면 그 사실이 오류다."""
    method, path = operations()[operation_id]
    responses = spec()["paths"][path][method.lower()]["responses"]
    declared = responses.get(str(status))
    if declared is None:
        return [f"{operation_id}: {status} 응답이 OpenAPI 에 없다"]
    content = declared.get("content", {}).get("application/json")
    if content is None:
        return (
            [] if body in (None, b"", "") else [f"{operation_id}: 본문 없는 응답인데 본문이 있다"]
        )
    return errors(content["schema"], body)
