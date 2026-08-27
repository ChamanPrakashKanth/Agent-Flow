# Flow-GRPO path

This prototype collects every state/action/observation transition and terminal reward in `logs/trajectories.jsonl`. Failed tool calls and safe `NO_POST` outcomes are retained.

To move to the official AgentFlow training stack:

1. Freeze a benchmark and split trajectories by event (not by URL) to avoid leakage.
2. Convert planner turns to the official AgentFlow dataset fields (`prompt`, sampled action completion, tool transition, terminal outcome reward).
3. Start from supervised fine-tuning on valid structured actions and recovery examples.
4. Run Flow-GRPO only on the planner using grouped on-policy rollouts; keep executor, verifier, and generator fixed initially.
5. Reward factual outcome, source independence, deduplication, recovery and efficiency. Give correct `NO_POST` positive reward.
6. Evaluate against the untouched temporal split and all A-E ablations before enabling any publishing experiment.

The official implementation is intentionally not vendored: it brings a distributed vLLM/VeRL training stack and its published quick start targets a 7B planner. This repository produces the trajectories needed to justify that cost first.

