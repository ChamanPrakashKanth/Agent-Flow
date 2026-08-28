from __future__ import annotations

import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Settings
from ..model import LocalModel, ModelReply, count_messages_tokens, estimate_tokens, first_json

logger = logging.getLogger(__name__)

# Standard 2K anti-OOM context limit (2,048 tokens)
DEFAULT_MAX_CONTEXT_TOKENS = 2048
DEFAULT_RESERVED_COMPLETION_TOKENS = 512


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def to_hermes_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry of tools available for Hermes function calling."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str | None = None,
        description: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a python function as a Hermes tool."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or f"Execute {tool_name}").strip()
            tool_params = parameters or self._inspect_parameters(func)
            self._tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                parameters=tool_params,
                handler=func,
            )
            return func

        return decorator

    def add_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> None:
        tool_desc = description or (handler.__doc__ or f"Execute {name}").strip()
        tool_params = parameters or self._inspect_parameters(handler)
        self._tools[name] = ToolDefinition(
            name=name,
            description=tool_desc,
            parameters=tool_params,
            handler=handler,
        )

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def to_hermes_tools_schema(self) -> list[dict[str, Any]]:
        return [t.to_hermes_schema() for t in self._tools.values()]

    @staticmethod
    def _inspect_parameters(func: Callable[..., Any]) -> dict[str, Any]:
        sig = inspect.signature(func)
        properties: dict[str, Any] = {}
        required: list[str] = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        for param_name, param in sig.parameters.items():
            if param_name in {"self", "cls"}:
                continue
            prop_type = type_map.get(param.annotation, "string")
            prop: dict[str, Any] = {"type": prop_type}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
            else:
                prop["default"] = param.default
            properties[param_name] = prop

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


class ContextBudgetManager:
    """Enforces strict token context limit and prunes old context to prevent OOM."""

    def __init__(
        self,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        reserved_completion_tokens: int = DEFAULT_RESERVED_COMPLETION_TOKENS,
        max_observation_chars: int = 1500,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.reserved_completion_tokens = reserved_completion_tokens
        self.max_observation_chars = max_observation_chars
        self.budget_ceiling = max(512, self.max_context_tokens - self.reserved_completion_tokens)

    def sanitize_observation(self, output: Any) -> str:
        """Format and clamp tool outputs to prevent giant payload blowups."""
        if isinstance(output, (dict, list)):
            text = json.dumps(output, ensure_ascii=False)
        else:
            text = str(output)
        if len(text) > self.max_observation_chars:
            head = text[: self.max_observation_chars - 300]
            tail = text[-200:]
            return f"{head}\n\n[...truncated {len(text) - self.max_observation_chars} chars to avoid context overflow...]\n\n{tail}"
        return text

    def prune_context(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prune older intermediate tool responses if total tokens approach the 16k budget."""
        current_tokens = count_messages_tokens(messages)
        if current_tokens <= self.budget_ceiling or len(messages) <= 3:
            return messages

        pruned = [dict(m) for m in messages]
        # Iterate over intermediate turns (skip system prompt [0] and initial user prompt [1])
        # Truncate old tool responses and assistant tool calls first
        for i in range(2, len(pruned) - 1):
            if current_tokens <= self.budget_ceiling:
                break
            msg = pruned[i]
            content = str(msg.get("content", ""))
            if len(content) > 400:
                truncated_content = content[:250] + "\n[...prior observation pruned for 16k context budget...]"
                saved_tokens = estimate_tokens(content) - estimate_tokens(truncated_content)
                msg["content"] = truncated_content
                current_tokens -= max(0, saved_tokens)

        # If still over budget, aggressively drop oldest non-system pairs
        while current_tokens > self.budget_ceiling and len(pruned) > 4:
            # Remove message at index 2 (oldest intermediate turn)
            removed = pruned.pop(2)
            current_tokens -= estimate_tokens(str(removed.get("content", ""))) + 4

        return pruned


@dataclass
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]
    raw: str


@dataclass
class ToolExecutionResult:
    call: ParsedToolCall
    output: Any
    success: bool
    error: str = ""


@dataclass
class ToolCallResult:
    final_text: str
    tool_calls: list[ToolExecutionResult] = field(default_factory=list)
    tokens_prompt: int = 0
    tokens_completion: int = 0
    turns: int = 0
    success: bool = True
    parsed_json: dict[str, Any] | None = None


class HermesToolCaller:
    """Native Python implementation of Nous Hermes 16K tool calling engine."""

    def __init__(
        self,
        model: LocalModel,
        registry: ToolRegistry | None = None,
        settings: Settings | None = None,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> None:
        self.model = model
        self.registry = registry or ToolRegistry()
        self.settings = settings
        context_limit = (
            settings.model_context_tokens
            if settings and hasattr(settings, "model_context_tokens")
            else max_context_tokens
        )
        self.budget_manager = ContextBudgetManager(
            max_context_tokens=context_limit,
            max_observation_chars=getattr(settings, "max_observation_chars", 1500) if settings else 1500,
        )

    def build_system_prompt(self, base_system: str | None = None) -> str:
        """Construct Nous Hermes ChatML system prompt including tool definitions."""
        tools_schema = self.registry.to_hermes_tools_schema()
        tools_json = json.dumps(tools_schema, indent=2, ensure_ascii=False)

        system = base_system or (
            "You are a helpful, factual research assistant equipped with external tools. "
            "Think step-by-step. Whenever you need fresh real-time facts or external validation, "
            "call the appropriate tool using <tool_call> tags."
        )

        return (
            f"{system}\n\n"
            "# Tools\n\n"
            "You have access to the following tools:\n"
            f"<tools>\n{tools_json}\n</tools>\n\n"
            "To call a tool, respond ONLY with a <tool_call> XML block containing a valid JSON object with 'name' and 'arguments'. Example:\n"
            "<tool_call>\n"
            '{"name": "web_search", "arguments": {"query": "artificial intelligence news"}}\n'
            "</tool_call>\n\n"
            "When the tool executes, the result will be provided in a <tool_response> block. "
            "Once you have enough information to fulfill the user request, provide your final response without <tool_call> tags."
        )

    @staticmethod
    def extract_tool_calls(text: str) -> list[ParsedToolCall]:
        """Extract tool calls from <tool_call> blocks or JSON fallbacks."""
        calls: list[ParsedToolCall] = []
        if not text:
            return calls

        # 1. Match official Nous Hermes <tool_call> blocks
        pattern = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)

        for match in matches:
            raw = match.strip()
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and "name" in data:
                    calls.append(ParsedToolCall(
                        name=data["name"],
                        arguments=data.get("arguments", {}),
                        raw=raw,
                    ))
            except Exception:
                # Try finding JSON object within the tag
                try:
                    data = first_json(raw)
                    if isinstance(data, dict) and "name" in data:
                        calls.append(ParsedToolCall(
                            name=data["name"],
                            arguments=data.get("arguments", {}),
                            raw=raw,
                        ))
                except Exception:
                    continue

        if calls:
            return calls

        # 2. Match Markdown ```json code blocks with {"name": ..., "arguments": ...}
        code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        for block in code_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "name" in data and ("arguments" in data or "query" in data or "url" in data):
                    args = data.get("arguments") if "arguments" in data else {k: v for k, v in data.items() if k != "name"}
                    calls.append(ParsedToolCall(name=data["name"], arguments=args, raw=block))
            except Exception:
                continue

        return calls

    def format_tool_response(self, name: str, output: Any) -> str:
        """Format tool output into Nous Hermes <tool_response> tag."""
        sanitized = self.budget_manager.sanitize_observation(output)
        payload = {"name": name, "content": sanitized}
        return f"<tool_response>\n{json.dumps(payload, ensure_ascii=False)}\n</tool_response>"

    def execute_tool(self, call: ParsedToolCall) -> ToolExecutionResult:
        """Execute a tool handler by name with error handling."""
        tool_def = self.registry.get(call.name)
        if not tool_def:
            err = f"Tool '{call.name}' not found in registered tools"
            logger.warning(err)
            return ToolExecutionResult(call=call, output={"error": err}, success=False, error=err)

        try:
            kwargs = call.arguments if isinstance(call.arguments, dict) else {}
            sig = inspect.signature(tool_def.handler)
            valid_kwargs = {}
            for param_name in sig.parameters:
                if param_name in kwargs:
                    valid_kwargs[param_name] = kwargs[param_name]

            # Run handler
            result = tool_def.handler(**valid_kwargs) if valid_kwargs or not kwargs else tool_def.handler(**kwargs)
            return ToolExecutionResult(call=call, output=result, success=True)
        except Exception as exc:
            err = f"Execution failed for tool '{call.name}': {type(exc).__name__}: {str(exc)}"
            logger.error(err, exc_info=True)
            return ToolExecutionResult(call=call, output={"error": err}, success=False, error=err)

    def run(
        self,
        task: str,
        system_override: str | None = None,
        max_turns: int = 6,
        temperature: float = 0.1,
    ) -> ToolCallResult:
        """Run full autonomous multi-turn Hermes tool calling loop with 16k context budgeting."""
        system_content = self.build_system_prompt(system_override)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": task},
        ]

        total_prompt_tokens = 0
        total_completion_tokens = 0
        all_executions: list[ToolExecutionResult] = []
        turn = 0

        while turn < max_turns:
            turn += 1
            # Apply strict 16K anti-OOM context pruning before making the LLM call
            messages = self.budget_manager.prune_context(messages)

            reply: ModelReply = self.model.chat_messages(
                messages=messages,
                json_mode=False,
                temperature=temperature,
            )
            total_prompt_tokens += reply.prompt_tokens
            total_completion_tokens += reply.completion_tokens

            model_text = reply.text.strip()
            tool_calls = self.extract_tool_calls(model_text)

            # If no tool calls requested, model has reached its final answer
            if not tool_calls:
                parsed_json = None
                try:
                    parsed_json = first_json(model_text)
                except Exception:
                    pass

                return ToolCallResult(
                    final_text=model_text,
                    tool_calls=all_executions,
                    tokens_prompt=total_prompt_tokens,
                    tokens_completion=total_completion_tokens,
                    turns=turn,
                    success=True,
                    parsed_json=parsed_json,
                )

            # Record assistant's tool call turn
            messages.append({"role": "assistant", "content": model_text})

            # Execute all tool calls
            responses: list[str] = []
            for call in tool_calls:
                exec_result = self.execute_tool(call)
                all_executions.append(exec_result)
                tool_resp_str = self.format_tool_response(call.name, exec_result.output)
                responses.append(tool_resp_str)

            # Append tool responses as user/tool feedback
            combined_responses = "\n\n".join(responses)
            messages.append({"role": "user", "content": combined_responses})

        # Hit max turns limit
        final_text = messages[-1].get("content", "")
        return ToolCallResult(
            final_text=final_text,
            tool_calls=all_executions,
            tokens_prompt=total_prompt_tokens,
            tokens_completion=total_completion_tokens,
            turns=turn,
            success=False,
        )
