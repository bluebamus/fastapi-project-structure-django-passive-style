"""Catalog 도메인 스키마 — 상품 CRUD 요청/응답 (Pydantic v2)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    """상품 공통 필드."""

    sku: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="재고 관리 코드(전역 고유)",
        examples=["SKU-1001"],
    )
    name: str = Field(
        ..., min_length=1, max_length=200, description="상품명", examples=["기계식 키보드"]
    )
    description: str | None = Field(None, description="상품 설명(선택)", examples=["적축 87키"])
    price: Decimal = Field(
        ..., ge=0, max_digits=12, decimal_places=2, description="판매가", examples=["129000.00"]
    )
    stock: int = Field(0, ge=0, description="재고 수량", examples=[25])
    is_active: bool = Field(True, description="판매 여부", examples=[True])


class ProductCreate(ProductBase):
    """상품 생성 요청."""


class ProductUpdate(BaseModel):
    """상품 수정 요청 — 전달된 필드만 부분 수정한다.

    예시가 **일부 필드만** 담고 있는 것이 의도다. 전체를 보내는 모양을 예시로 두면
    PATCH 를 PUT 처럼 쓰게 되고, 빠뜨린 필드가 덮어써진다고 오해하게 된다.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{"price": "119000.00", "stock": 12}]})

    name: str | None = Field(None, min_length=1, max_length=200, description="상품명")
    description: str | None = Field(None, description="상품 설명")
    price: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2, description="판매가")
    stock: int | None = Field(None, ge=0, description="재고 수량")
    is_active: bool | None = Field(None, description="판매 여부")


class ProductResponse(ProductBase):
    """상품 응답.

    ``from_attributes=True`` 는 **ORM 객체**를 받기 때문에 쓴다. Raw 예제의 응답
    DTO 에는 이 설정이 없다 — 거기는 ORM 객체가 아니라 ``RowMapping`` 을 받는다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="상품 ID(UUID)")
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    """상품 목록 응답(페이지네이션)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "3f1c9c2e-0b1a-4a5e-9f3d-2c7b8a4d5e6f",
                            "sku": "SKU-1001",
                            "name": "기계식 키보드",
                            "description": "적축 87키",
                            "price": "129000.00",
                            "stock": 25,
                            "is_active": True,
                            "created_at": "2026-08-01T10:30:00+09:00",
                            "updated_at": "2026-08-01T10:30:00+09:00",
                        }
                    ],
                    "total": 1,
                    "skip": 0,
                    "limit": 50,
                }
            ]
        }
    )

    items: list[ProductResponse]
    total: int = Field(ge=0, description="전체 상품 수")
    skip: int = Field(ge=0, description="건너뛴 레코드 수")
    limit: int = Field(ge=1, description="페이지 크기")
