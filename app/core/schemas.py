"""
공통 요청 스키마 기반 클래스

모든 기능의 부분 수정(PATCH) 스키마가 상속한다(service-hardening ADR-007).
"""

from typing import ClassVar, Self

from pydantic import BaseModel, model_validator


class PatchSchema(BaseModel):
    """부분 수정 스키마의 기반 클래스.

    PATCH 스키마는 "보내지 않은 필드는 바꾸지 않는다" 를 표현하려고 모든 필드를 ``X | None = None``
    으로 선언한다. 그러면 ``{"title": null}`` 처럼 **명시적으로 보낸 null** 도 검증을 통과해
    NOT NULL 컬럼에 None 을 쓰게 된다 — MySQL 은 1048 로 거부하고, 그 오류가 500 이 된다.

    여기서 ``model_fields_set``(클라이언트가 실제로 보낸 필드) 안의 None 을 검사해, 컬럼이
    nullable 이라고 선언한 필드(``nullable_fields``) 밖이면 422 로 거부한다.
    """

    #: 명시적 null 을 허용하는 필드 — 모델 컬럼이 ``nullable=True`` 인 것만 적는다.
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> Self:
        rejected = sorted(
            name
            for name in self.model_fields_set
            if getattr(self, name) is None and name not in self.nullable_fields
        )
        if rejected:
            raise ValueError(f"null 로 바꿀 수 없는 필드: {', '.join(rejected)}")
        return self
