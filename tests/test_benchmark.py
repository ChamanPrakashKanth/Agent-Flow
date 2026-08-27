from local_news_agent.evaluation.benchmark import run_benchmark


def test_benchmark_has_30_tasks_and_ablation_improves(tmp_path):
    report=run_benchmark(tmp_path/"r.json")
    assert len(report["tasks"]) >= 30
    assert report["levels"]["E"]["metrics"]["task_completion_pct"] >= report["levels"]["A"]["metrics"]["task_completion_pct"]
    assert report["levels"]["E"]["metrics"]["duplicate_rate"] == 0
