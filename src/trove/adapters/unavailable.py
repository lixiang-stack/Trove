from __future__ import annotations

from trove.errors import ProcessingError
from trove.ports import OrganizationResult, StageContext


class UnavailableOrganizer:
    """The DeepSeek adapter is delivered by ticket 17; fail explicitly when enabled."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def organize(
        self,
        *,
        text: str,
        title: str,
        existing_tags: list[str],
        context: StageContext,
    ) -> OrganizationResult:
        if not self.enabled:
            return OrganizationResult(
                summary="",
                tags=[],
                model="disabled",
                prompt_version="disabled",
            )
        raise ProcessingError("llm.not_configured", "整理组件尚未配置，请稍后重试")
