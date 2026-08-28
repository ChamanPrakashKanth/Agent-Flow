from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path
import httpx
from .config import Settings
from .evaluation.benchmark import run_benchmark
from .hermes.fixture import FixtureTools
from .hermes.tools import ChromeExtensionWebTools, DirectWebTools, HermesCLITools, HermesNativeTools
from .job_toolcaller import CustomJobToolCaller
from .memory.store import MemoryStore
from .model import LocalModel
from .orchestrator import NewsAgent
from .planner.planner import Planner
from .publisher.queue import Publisher
from .publisher.hermes_browser import publish_one_due
from .scheduler.daemon import run_forever
from .training.trajectory import TrajectoryLogger
from .autonomy.service import QwenHarness
from .autonomy.storage import RunStore


def build(settings: Settings) -> NewsAgent:
    settings.ensure_dirs(); model = LocalModel(settings); planner = Planner(model)
    tools = {
        "custom": CustomJobToolCaller,
        "direct": DirectWebTools,
        "hermes": HermesNativeTools,
        "hermes_native": HermesNativeTools,
        "hermes_cli": HermesCLITools,
        "fixture": FixtureTools,
        "extension": ChromeExtensionWebTools,
        "chrome": ChromeExtensionWebTools,
    }[settings.tool_backend]
    if settings.tool_backend == "custom":
        tool_instance = CustomJobToolCaller(settings, model=model)
    elif settings.tool_backend in {"hermes", "hermes_native"}:
        tool_instance = tools(settings, model=model)
    elif settings.tool_backend == "hermes_cli":
        tool_instance = tools(settings)
    else:
        tool_instance = tools()
    return NewsAgent(
        settings,
        planner,
        tool_instance,
        MemoryStore(settings.database_path),
        Publisher(settings.publish_mode, settings.queue_path, settings.threads_publish_enabled),
        TrajectoryLogger(settings.trajectory_path),
    )


def doctor(settings: Settings) -> int:
    checks = {
        "python": sys.version.split()[0],
        "model_backend": settings.model_backend,
        "model": settings.model_name,
        "tool_backend": settings.tool_backend,
        "publish_backend": settings.publish_backend,
        "context_budget": f"{settings.model_context_tokens} tokens (bounded local runtime)",
        "tool_caller": "custom_dedicated" if settings.tool_backend == "custom" else settings.tool_backend,
        "kv_cache_compression": f"{settings.ollama_kv_cache_type} (Flash Attention: {settings.ollama_flash_attention})",
        "budgeted_memory": f"B={settings.memory_budget_nodes}, tau={settings.memory_consolidation_threshold}",
        "pexels_api": "configured" if bool(settings.pexels_api_key) else "not configured (using ambient background)",
        "hermes_cli": shutil.which(settings.hermes_command) or (settings.hermes_command if Path(settings.hermes_command).is_file() else None),
        "ollama_cli": shutil.which("ollama") or shutil.which(Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")).as_posix()) or (str(Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"))) if Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")).is_file() else None),
    }
    try:
        response = httpx.get(f"{settings.model_base_url}/api/tags", timeout=3)
        checks["model_endpoint"] = "ok" if response.is_success else f"HTTP {response.status_code}"
        checks["model_installed"] = any(x.get("name", "").split(":")[0] == settings.model_name.split(":")[0] for x in response.json().get("models", []))
    except Exception as exc:
        checks["model_endpoint"] = f"unavailable: {type(exc).__name__}"
    settings.ensure_dirs()
    checks["database_path"] = str(settings.database_path.resolve())
    print(json.dumps(checks, indent=2))
    model_ok = checks.get("model_endpoint") == "ok"
    return 0 if model_ok or settings.tool_backend in {"custom", "direct", "fixture"} else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="news-agent", description="Local News Research Agent with Custom Anti-OOM ToolCaller")
    p.add_argument("--tools", choices=["custom", "direct", "hermes", "hermes_native", "hermes_cli", "fixture", "extension", "chrome"], help="override configured tool backend")
    sub=p.add_subparsers(dest="command",required=True)
    all_topics = "artificial intelligence, semiconductors, quantum computing, defense technology, military systems, mechanical engineering, physics"
    one = sub.add_parser("run", help="run one research cycle")
    one.add_argument("--topic", default=all_topics)
    one.add_argument("--publish", action="store_true", help="immediately publish queued draft after research cycle")
    daemon = sub.add_parser("daemon", help="run research independently on a fixed interval")
    daemon.add_argument("--topic", default=all_topics)
    daemon.add_argument("--every-minutes", type=int, default=60)
    sub.add_parser("doctor", help="check local runtime")
    sub.add_parser("publish-due", help="publish verified X/Threads drafts; YouTube stays local draft-only")
    qwen = sub.add_parser("qwen-run", help="run the bounded Qwen Coder / llama.cpp harness")
    qwen.add_argument("--topic", default=None)
    qwen.add_argument("--browser", choices=["direct", "extension"], default="extension")
    inspect = sub.add_parser("inspect-run", help="inspect persisted Qwen harness run state")
    inspect.add_argument("run_id")
    bench = sub.add_parser("benchmark", help="run 30-task A-E offline benchmark")
    bench.add_argument("--output", type=Path, default=Path("evaluation/results/latest.json"))
    args = p.parse_args(argv)
    settings = Settings.from_env()
    if args.tools: settings = replace(settings, tool_backend=args.tools)
    if args.command == "qwen-run" and not args.topic:
        args.topic = settings.qwen_default_topics
    if args.command == "doctor": return doctor(settings)
    if args.command == "inspect-run":
        print(json.dumps(RunStore(settings.database_path).inspect(args.run_id), indent=2)); return 0
    if args.command == "qwen-run":
        result = QwenHarness(settings, args.browser).run(args.topic)
        print(json.dumps(result.__dict__, indent=2)); return 0
    if args.command == "publish-due":
        result = publish_one_due(settings)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in {"POSTED", "NO_VERIFIED_DRAFT"} else 2
    if args.command == "benchmark":
        report = run_benchmark(args.output)
        print(json.dumps(report["levels"], indent=2))
        print(f"Full report: {args.output.resolve()}")
        return 0
    agent = build(settings)
    def cycle():
        state = agent.run(args.topic)
        output = {
            "run_id": state.run_id,
            "result": state.final_result,
            "steps": state.step,
            "searches": state.searches,
            "page_reads": state.page_reads,
            "tokens": state.tokens_prompt + state.tokens_completion,
            "errors": state.errors
        }
        print(json.dumps(output, indent=2))
        return state
    if args.command == "run":
        state = cycle()
        if getattr(args, "publish", False):
            print("\n[PUBLISHER] Publishing due verified drafts...")
            pub_result = publish_one_due(settings)
            print(json.dumps(pub_result, indent=2))
        return 0
    run_forever(cycle, args.every_minutes)
    return 0


if __name__ == "__main__": raise SystemExit(main())
