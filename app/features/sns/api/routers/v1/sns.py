"""
SNS v1 API 엔드포인트 — 피드 게시물 CRUD.

인가: 조회는 공개, 생성은 인증(``CurrentPrincipal`` — 작성자는 서버가 채운다), 수정·삭제는
소유자 또는 슈퍼유저(서비스가 주입받은 ``OwnershipPolicy`` 로 판정한다).
view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직은 services, 세션 선택·Service 조립은 dependencies 가 맡는다.
쓰기 핸들러는 응답 DTO 를 먼저 검증한 뒤 `await service.commit()` 으로 한 번 커밋한다(별도 UnitOfWork 없음).
검증이 실패하면 커밋하지 않는다(tests/test_validate_before_commit.py).
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.core.security.access import Public
from app.core.security.dependencies import (
    FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    CurrentPrincipal,
)
from app.features.sns.dependencies.sns_dependencies import (
    get_sns_service,
    get_sns_service_readonly,
)
from app.features.sns.schemas.sns_schema import (
    SnsPostCreate,
    SnsPostListResponse,
    SnsPostResponse,
    SnsPostUpdate,
)
from app.features.sns.services.sns_service import SnsService

router = APIRouter()

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "피드 게시물을 찾을 수 없음"}
}
#: 수정·삭제 — 소유자 또는 슈퍼유저만(ADR-018). 존재 확인(404)이 권한 확인(403)보다 먼저다.
_OWNER_ONLY = {**_NOT_FOUND, **UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE}


@router.post(
    "/posts",
    response_model=SnsPostResponse,
    status_code=status.HTTP_201_CREATED,
    responses=UNAUTHORIZED_RESPONSE,
    summary="피드 게시물 생성",
    description="새 피드 게시물을 생성합니다.",
    operation_id="createSnsPost",
)
async def create_post(
    payload: SnsPostCreate,
    principal: CurrentPrincipal,
    service: SnsService = Depends(get_sns_service),
) -> SnsPostResponse:
    post = await service.create_post(payload, principal)
    response = SnsPostResponse.model_validate(post)  # 검증 실패면 커밋하지 않는다
    await service.commit()
    return response


@router.get(
    "/posts",
    response_model=SnsPostListResponse,
    summary="피드 게시물 목록 조회",
    description="피드 게시물 목록을 페이지네이션하여 조회합니다.",
    dependencies=[Public],
    operation_id="listSnsPosts",
)
async def list_posts(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: SnsService = Depends(get_sns_service_readonly),
) -> SnsPostListResponse:
    posts, total = await service.list_posts(skip=skip, limit=limit)
    return SnsPostListResponse(
        items=[SnsPostResponse.model_validate(p) for p in posts],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/posts/{post_id}",
    response_model=SnsPostResponse,
    responses=_NOT_FOUND,
    summary="피드 게시물 단건 조회",
    description="ID로 피드 게시물을 조회합니다.",
    dependencies=[Public],
    operation_id="getSnsPost",
)
async def get_post(
    post_id: str = Path(..., description="피드 게시물 ID(UUID)"),
    service: SnsService = Depends(get_sns_service_readonly),
) -> SnsPostResponse:
    post = await service.get_post(post_id)
    return SnsPostResponse.model_validate(post)


@router.patch(
    "/posts/{post_id}",
    response_model=SnsPostResponse,
    responses=_OWNER_ONLY,
    summary="피드 게시물 수정",
    description="피드 게시물을 부분 수정합니다(전달한 필드만).",
    operation_id="updateSnsPost",
)
async def update_post(
    payload: SnsPostUpdate,
    principal: CurrentPrincipal,
    post_id: str = Path(..., description="피드 게시물 ID(UUID)"),
    service: SnsService = Depends(get_sns_service),
) -> SnsPostResponse:
    post = await service.update_post(post_id, payload, principal)
    response = SnsPostResponse.model_validate(post)  # 검증 실패면 커밋하지 않는다
    await service.commit()
    return response


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_OWNER_ONLY,
    summary="피드 게시물 삭제",
    description="피드 게시물을 삭제합니다.",
    operation_id="deleteSnsPost",
)
async def delete_post(
    principal: CurrentPrincipal,
    post_id: str = Path(..., description="피드 게시물 ID(UUID)"),
    service: SnsService = Depends(get_sns_service),
) -> None:
    await service.delete_post(post_id, principal)
    await service.commit()
