"""
Reply v1 API 엔드포인트 — 댓글 CRUD.

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
from app.features.reply.dependencies.reply_dependencies import (
    get_reply_service,
    get_reply_service_readonly,
)
from app.features.reply.schemas.reply_schema import (
    ReplyCreate,
    ReplyListResponse,
    ReplyResponse,
    ReplyUpdate,
)
from app.features.reply.services.reply_service import ReplyService

router = APIRouter()

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "댓글을 찾을 수 없음"}
}
#: 수정·삭제 — 소유자 또는 슈퍼유저만(ADR-018). 존재 확인(404)이 권한 확인(403)보다 먼저다.
_OWNER_ONLY = {**_NOT_FOUND, **UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE}


@router.post(
    "/replies",
    response_model=ReplyResponse,
    status_code=status.HTTP_201_CREATED,
    responses=UNAUTHORIZED_RESPONSE,
    summary="댓글 생성",
    description="새 댓글을 생성합니다.",
    operation_id="createReply",
)
async def create_reply(
    payload: ReplyCreate,
    principal: CurrentPrincipal,
    service: ReplyService = Depends(get_reply_service),
) -> ReplyResponse:
    reply = await service.create_reply(payload, principal)
    response = ReplyResponse.model_validate(reply)  # 검증 실패면 커밋하지 않는다
    await service.commit()
    return response


@router.get(
    "/replies",
    response_model=ReplyListResponse,
    summary="댓글 목록 조회",
    description="댓글 목록을 페이지네이션하여 조회합니다.",
    dependencies=[Public],
    operation_id="listReplies",
)
async def list_replies(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: ReplyService = Depends(get_reply_service_readonly),
) -> ReplyListResponse:
    replies, total = await service.list_replies(skip=skip, limit=limit)
    return ReplyListResponse(
        items=[ReplyResponse.model_validate(r) for r in replies],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/replies/{reply_id}",
    response_model=ReplyResponse,
    responses=_NOT_FOUND,
    summary="댓글 단건 조회",
    description="ID로 댓글을 조회합니다.",
    dependencies=[Public],
    operation_id="getReply",
)
async def get_reply(
    reply_id: str = Path(..., description="댓글 ID(UUID)"),
    service: ReplyService = Depends(get_reply_service_readonly),
) -> ReplyResponse:
    reply = await service.get_reply(reply_id)
    return ReplyResponse.model_validate(reply)


@router.patch(
    "/replies/{reply_id}",
    response_model=ReplyResponse,
    responses=_OWNER_ONLY,
    summary="댓글 수정",
    description="댓글을 부분 수정합니다(전달한 필드만).",
    operation_id="updateReply",
)
async def update_reply(
    payload: ReplyUpdate,
    principal: CurrentPrincipal,
    reply_id: str = Path(..., description="댓글 ID(UUID)"),
    service: ReplyService = Depends(get_reply_service),
) -> ReplyResponse:
    reply = await service.update_reply(reply_id, payload, principal)
    response = ReplyResponse.model_validate(reply)  # 검증 실패면 커밋하지 않는다
    await service.commit()
    return response


@router.delete(
    "/replies/{reply_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_OWNER_ONLY,
    summary="댓글 삭제",
    description="댓글을 삭제합니다.",
    operation_id="deleteReply",
)
async def delete_reply(
    principal: CurrentPrincipal,
    reply_id: str = Path(..., description="댓글 ID(UUID)"),
    service: ReplyService = Depends(get_reply_service),
) -> None:
    await service.delete_reply(reply_id, principal)
    await service.commit()
