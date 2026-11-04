from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_tenant
from app.api.v1.schemas import GenerateRequest, GenerateResponse
from app.auth.keys import AuthenticatedTenant

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    request: Request,
    auth: Annotated[AuthenticatedTenant, Depends(require_tenant)],
) -> GenerateResponse:
    response: GenerateResponse = await request.app.state.gateway.generate(
        auth, body, request.state.request_id
    )
    return response
