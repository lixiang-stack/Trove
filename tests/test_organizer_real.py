from __future__ import annotations

import httpx
import pytest

from trove.adapters.openai_chat import OpenAICompatibleChatClient
from trove.config import load_config
from trove.ports import StageContext
from trove.services.organization import OrganizationWorkflow


def _context(tmp_path) -> StageContext:
    return StageContext(
        item_id="item-1",
        run_id="run-1",
        work_dir=tmp_path,
        should_cancel=lambda: False,
        log=lambda message: None,
    )


# The default test run excludes network tests. Run with real model access from
# ~/Trove/config.toml [llm]:
#   uv run pytest -q -o addopts="" -m network tests/test_organizer_real.py -rs
# To run only this test:
#   uv run pytest -q -o addopts="" -m network \
#     tests/test_organizer_real.py::test_real_organizer -rs
@pytest.mark.network
def test_real_organizer(tmp_path):
    config = load_config()
    if not (config.llm.model and config.llm.base_url and config.llm.api_key):
        pytest.skip("LLM config is missing from ~/Trove/config.toml [llm]")
    with httpx.Client(timeout=config.llm.timeout_seconds) as client:
        organizer = OrganizationWorkflow(
            config.llm, OpenAICompatibleChatClient(config.llm, client)
        )
        result = organizer.organize(
            text="记忆是智能体的瓶颈。上下文窗口是临时的，记忆需要被选择、压缩和遗忘。",
            title="记忆与智能体",
            existing_tags=["智能体"],
            context=_context(tmp_path),
        )
    assert result.summary
    assert 1 <= len(result.tags) <= 3
    assert result.input_tokens > 0
    assert result.output_tokens > 0
