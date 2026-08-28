import json
from unittest.mock import MagicMock, patch

import pytest
from local_news_agent.config import Settings
from local_news_agent.hermes.caller import (
    ContextBudgetManager,
    HermesToolCaller,
    ParsedToolCall,
    ToolRegistry,
)
from local_news_agent.hermes.tools import HermesNativeTools
from local_news_agent.model import LocalModel, ModelReply, estimate_tokens
from local_news_agent.schemas import Evidence, SearchResult


def test_tool_registry_registration_and_schema():
    registry = ToolRegistry()

    @registry.register(description="Calculate sum of two numbers")
    def add(a: int, b: int) -> int:
        return a + b

    tool_def = registry.get("add")
    assert tool_def is not None
    assert tool_def.name == "add"
    assert tool_def.description == "Calculate sum of two numbers"
    assert tool_def.parameters["properties"]["a"]["type"] == "integer"
    assert tool_def.parameters["properties"]["b"]["type"] == "integer"
    assert "a" in tool_def.parameters["required"]
    assert "b" in tool_def.parameters["required"]

    schemas = registry.to_hermes_tools_schema()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "add"


def test_hermes_prompt_builder():
    registry = ToolRegistry()
    registry.add_tool(
        name="web_search",
        handler=lambda query, limit=5: [],
        description="Search breaking news",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    )
    mock_model = MagicMock(spec=LocalModel)
    caller = HermesToolCaller(model=mock_model, registry=registry)

    prompt = caller.build_system_prompt()
    assert "<tools>" in prompt
    assert "</tools>" in prompt
    assert "web_search" in prompt
    assert "<tool_call>" in prompt


def test_extract_tool_calls_xml_and_fallbacks():
    # 1. Valid XML <tool_call>
    xml_text = """I will search for the latest AI news.
<tool_call>
{"name": "web_search", "arguments": {"query": "DeepSeek V3", "limit": 3}}
</tool_call>
"""
    calls = HermesToolCaller.extract_tool_calls(xml_text)
    assert len(calls) == 1
    assert calls[0].name == "web_search"
    assert calls[0].arguments == {"query": "DeepSeek V3", "limit": 3}

    # 2. Multiple XML <tool_call> blocks
    multi_xml = """<tool_call>
{"name": "web_search", "arguments": {"query": "quantum computing"}}
</tool_call>
<tool_call>
{"name": "web_extract", "arguments": {"url": "https://example.com/quantum"}}
</tool_call>"""
    multi_calls = HermesToolCaller.extract_tool_calls(multi_xml)
    assert len(multi_calls) == 2
    assert multi_calls[0].name == "web_search"
    assert multi_calls[1].name == "web_extract"

    # 3. Markdown JSON code block fallback
    code_block_text = """Let me call the search tool:
```json
{"name": "web_search", "arguments": {"query": "semiconductors"}}
```"""
    cb_calls = HermesToolCaller.extract_tool_calls(code_block_text)
    assert len(cb_calls) == 1
    assert cb_calls[0].name == "web_search"
    assert cb_calls[0].arguments["query"] == "semiconductors"


def test_context_budget_manager_16k_pruning():
    # Test context pruner under heavy message volume
    manager = ContextBudgetManager(
        max_context_tokens=16384,
        reserved_completion_tokens=2048,
        max_observation_chars=1000,
    )
    # Budget ceiling is 16384 - 2048 = 14336 tokens

    # Large tool output truncation
    huge_output = "A" * 5000
    sanitized = manager.sanitize_observation(huge_output)
    assert len(sanitized) <= 1200
    assert "truncated" in sanitized

    # Message history pruning
    system_msg = {"role": "system", "content": "You are Hermes."}
    user_msg = {"role": "user", "content": "Find quantum news."}
    # Create 20 intermediate turns with large observations
    messages = [system_msg, user_msg]
    for i in range(10):
        messages.append({"role": "assistant", "content": f"<tool_call>{{\"name\": \"web_search\", \"arguments\": {{\"query\": \"q{i}\"}}}}</tool_call>"})
        messages.append({"role": "user", "content": f"<tool_response>{{\"name\": \"web_search\", \"content\": \"{'Long observation ' * 1000}\"}}</tool_response>"})

    pruned = manager.prune_context(messages)
    # Ensure system prompt and user prompt remain intact
    assert pruned[0]["role"] == "system"
    assert pruned[1]["role"] == "user"
    # Ensure tokens are bounded within budget
    from local_news_agent.model import count_messages_tokens
    assert count_messages_tokens(pruned) <= manager.budget_ceiling


def test_hermes_tool_caller_autonomous_loop():
    registry = ToolRegistry()

    @registry.register()
    def web_search(query: str, limit: int = 5) -> list[dict]:
        return [{"title": "Quantum Breakthrough", "url": "https://example.com/quantum"}]

    mock_model = MagicMock(spec=LocalModel)
    # First turn: model calls tool. Second turn: model returns final answer.
    mock_model.chat_messages.side_effect = [
        ModelReply(text='<tool_call>{"name": "web_search", "arguments": {"query": "quantum"}}\n</tool_call>', prompt_tokens=100, completion_tokens=50),
        ModelReply(text='{"summary": "Quantum computing achieved major breakthrough", "status": "CONFIRMED"}', prompt_tokens=200, completion_tokens=40),
    ]

    caller = HermesToolCaller(model=mock_model, registry=registry)
    result = caller.run("Find quantum breakthroughs")

    assert result.success is True
    assert result.turns == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call.name == "web_search"
    assert result.tool_calls[0].success is True
    assert result.parsed_json == {"summary": "Quantum computing achieved major breakthrough", "status": "CONFIRMED"}


def test_hermes_native_tools_news_integration():
    settings = Settings(model_context_tokens=16384, tool_backend="hermes")
    mock_model = MagicMock(spec=LocalModel)
    tools = HermesNativeTools(settings=settings, model=mock_model)

    with patch.object(tools.extension_tools, "search", return_value=[SearchResult(title="AI News", url="https://ai.test", snippet="...", published_at="", source="Test")]):
        results = tools.search("AI", limit=2)
        assert len(results) == 1
        assert results[0].title == "AI News"

    with patch.object(tools.extension_tools, "extract", return_value=Evidence(url="https://ai.test", title="AI News", publisher="Test", excerpt="Excerpt")):
        ev = tools.extract("https://ai.test")
        assert ev.title == "AI News"
        assert ev.url == "https://ai.test"
