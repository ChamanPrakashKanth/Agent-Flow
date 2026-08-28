from __future__ import annotations

import os
from local_news_agent.config import Settings
from local_news_agent.model import LocalModel
from local_news_agent.memory.budgeted_working_memory import BudgetedWorkingMemory
from scripts.demonstrate_kv_compression import calculate_llama32_3b_kv_cache


def test_settings_kv_cache_defaults():
    s = Settings.from_env()
    assert s.ollama_flash_attention is True
    assert s.ollama_kv_cache_type == "q4_0"


def test_local_model_sets_kv_environment():
    s = Settings(model_backend="ollama", ollama_flash_attention=True, ollama_kv_cache_type="q4_0")
    model = LocalModel(s)
    assert os.environ.get("OLLAMA_FLASH_ATTENTION") == "1"
    assert os.environ.get("OLLAMA_KV_CACHE_TYPE") == "q4_0"


def test_llama32_3b_kv_cache_calculation():
    fp16_calc = calculate_llama32_3b_kv_cache(context_tokens=8192, kv_type="fp16")
    q4_calc = calculate_llama32_3b_kv_cache(context_tokens=8192, kv_type="q4_0")

    # Verify FP16: 8192 * (2 * 28 * 8 * 128 * 2) bytes = 896 MB
    assert fp16_calc["total_mb"] == 896.0
    # Verify q4_0 achieves >70% memory reduction
    assert q4_calc["total_mb"] < 250.0
    reduction = (1 - q4_calc["total_mb"] / fp16_calc["total_mb"]) * 100
    assert reduction > 70.0


def test_combined_budgeted_memory_and_kv_compression():
    bwm = BudgetedWorkingMemory(budget_nodes=8, pressure_threshold=0.60)
    for i in range(12):
        bwm.tick(i)
        bwm.ingest_search_result(f"News {i}", f"Snippet details for news item {i}", f"https://source{i}.com")
    
    summary = bwm.get_budgeted_summary()
    assert len(summary["active_concepts"]) <= 4
    assert summary["consolidations"] >= 1
