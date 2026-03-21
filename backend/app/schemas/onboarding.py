"""온보딩 관련 Pydantic v2 스키마"""

from pydantic import BaseModel, Field


class OnboardingCompleteRequest(BaseModel):
    """온보딩 완료 요청"""
    disclaimer_agreed: bool = Field(..., description="면책 조항 동의 여부")
    selected_asset_types: list[str] = Field(
        default=[], description="사용자가 선택한 자산 유형 목록"
    )


class OnboardingCompleteResponse(BaseModel):
    """온보딩 완료 응답"""
    onboarding_completed: bool
    message: str
