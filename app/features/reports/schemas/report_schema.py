"""Reports 도메인 스키마 — Raw 집계 결과 DTO (Pydantic v2).

**``from_attributes=True`` 가 없다.** 여기로 들어오는 것은 ORM 객체가 아니라
``RowMapping`` 이고, 그것을 ``dict()`` 로 바꿔 명시적으로 검증한다. ORM 예제의
``ProductResponse`` 와 정확히 이 지점이 다르다.

검증을 거치는 이유는 형식 때문만이 아니다. Raw SQL 의 컬럼 alias 가 바뀌면
(``AS sales_date`` → ``AS day``) 여기서 즉시 실패한다 — dict 로 흘려보내면 그 오류는
클라이언트까지 조용히 간다.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySalesItem(BaseModel):
    """일자별 집계 한 줄 — Raw SQL 의 컬럼 alias 와 필드명이 1:1 이다."""

    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="총 매출", examples=["5120.50"])


class DailySalesReportResponse(BaseModel):
    """일별 매출 리포트 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "order_count": 42,
                    "items": [
                        {
                            "sales_date": "2026-08-01",
                            "order_count": 42,
                            "gross_amount": "5120.50",
                        }
                    ],
                }
            ]
        }
    )

    start_date: date = Field(description="조회 시작일(포함)")
    end_date: date = Field(description="조회 종료일(포함)")
    order_count: int = Field(ge=0, description="기간 전체 주문 수")
    items: list[DailySalesItem] = Field(description="일자별 집계")
