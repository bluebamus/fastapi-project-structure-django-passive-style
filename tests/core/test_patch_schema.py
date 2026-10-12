"""``PatchSchema`` — PATCH 의 명시적 null 거부 (service-hardening ADR-007 · F-009).

``X | None = None`` 로 선언한 PATCH 필드는 ``{"title": null}`` 도 통과시킨다. NOT NULL 컬럼이면
MySQL 이 1048 로 거부하고 그것이 500 이 됐다(SQLite 단위 테스트는 409 로 가렸다). 공통 기반
클래스가 422 로 막는지, 그리고 모든 기능의 Update 스키마가 그 기반을 상속하는지 본다.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from pydantic import Field, ValidationError
from sqlalchemy import inspect as sa_inspect

import app.features
from app.core.schemas import PatchSchema
from app.features.blog.schemas.blog_schema import PostUpdate


class _Sample(PatchSchema):
    nullable_fields = frozenset({"note"})

    title: str | None = Field(None, min_length=1)
    note: str | None = None


def test_explicit_null_on_a_non_nullable_field_is_rejected():
    with pytest.raises(ValidationError, match="title"):
        _Sample.model_validate({"title": None})


def test_explicit_null_on_a_nullable_field_is_kept():
    sample = _Sample.model_validate({"note": None})

    assert sample.model_dump(exclude_unset=True) == {"note": None}


def test_omitted_fields_are_not_checked():
    """보내지 않은 필드는 기본값 None 이어도 거부하지 않는다 — 부분 수정의 핵심."""
    assert _Sample.model_validate({}).model_dump(exclude_unset=True) == {}
    assert _Sample.model_validate({"title": "x"}).model_dump(exclude_unset=True) == {"title": "x"}


def test_blog_update_rejects_null_title():
    """작성자는 서버가 채우므로(service-hardening ADR-018) 수정 스키마에 nullable 필드가 없다."""
    with pytest.raises(ValidationError):
        PostUpdate.model_validate({"title": None})
    assert "author" not in PostUpdate.model_fields


def _update_schemas() -> list[type[PatchSchema]]:
    """``app.features.*.schemas`` 의 ``*Update`` 클래스 전부."""
    found = []
    for feature in pkgutil.iter_modules(app.features.__path__):
        try:
            schemas = importlib.import_module(f"app.features.{feature.name}.schemas")
        except ModuleNotFoundError:
            continue
        for module_info in pkgutil.iter_modules(schemas.__path__):
            module = importlib.import_module(f"{schemas.__name__}.{module_info.name}")
            found.extend(
                obj
                for name, obj in vars(module).items()
                if name.endswith("Update")
                and isinstance(obj, type)
                and obj.__module__ == module.__name__
            )
    return found


def test_every_update_schema_inherits_patch_schema():
    schemas = _update_schemas()

    assert len(schemas) >= 5, f"Update 스키마를 못 찾았다 — 검사가 헛통과한다: {schemas}"
    offenders = [cls.__qualname__ for cls in schemas if not issubclass(cls, PatchSchema)]
    assert not offenders, f"PatchSchema 를 상속하지 않는 Update 스키마: {offenders}"


@pytest.mark.parametrize(
    ("schema_path", "model_path"),
    [
        (
            "app.features.blog.schemas.blog_schema.PostUpdate",
            "app.features.blog.models.models.Post",
        ),
        (
            "app.features.catalog.schemas.product_schema.ProductUpdate",
            "app.features.catalog.models.models.Product",
        ),
        (
            "app.features.reply.schemas.reply_schema.ReplyUpdate",
            "app.features.reply.models.models.Reply",
        ),
        (
            "app.features.sns.schemas.sns_schema.SnsPostUpdate",
            "app.features.sns.models.models.SnsPost",
        ),
        (
            "app.features.user.schemas.user_schema.UserUpdate",
            "app.features.user.models.models.User",
        ),
    ],
)
def test_nullable_fields_match_the_model_columns(schema_path: str, model_path: str):
    """허용 목록은 모델 컬럼이 nullable 인 필드와 정확히 같다 — 둘이 어긋나면 500 이나 과잉 거부가 된다."""

    def _load(path: str) -> type:
        module, _, name = path.rpartition(".")
        return getattr(importlib.import_module(module), name)

    schema = _load(schema_path)
    columns = sa_inspect(_load(model_path)).columns
    nullable_in_model = {name for name in schema.model_fields if columns[name].nullable}

    assert schema.nullable_fields == nullable_in_model
