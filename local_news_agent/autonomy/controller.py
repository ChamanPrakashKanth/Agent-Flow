from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPolicy:
    retry_budget: int
    reflection_depth: int
    retrieval_limit: int
    verification_intensity: int
    planning_depth: int
    min_tool_confidence: float
    require_human: bool


class ForecastController:
    """EMA-smoothed MFE/MAD/MSE controller for bounded agent adaptation."""

    def __init__(self, alpha: float = 0.3, weights: tuple[float, float, float] = (0.25, 0.35, 0.40), scales: tuple[float, float, float] = (1.0, 1.0, 1.0)):
        self.alpha = min(1.0, max(0.01, alpha)); self.weights = weights; self.scales = tuple(max(1e-6, x) for x in scales)
        self.count = 0; self._sum = self._abs_sum = self._sq_sum = 0.0
        self.mfe = self.mad = self.mse = self.guidance = 0.0

    def update(self, observed: float, expected: float) -> float:
        error = float(observed) - float(expected)
        self.count += 1; self._sum += error; self._abs_sum += abs(error); self._sq_sum += error * error
        raw = (self._sum / self.count, self._abs_sum / self.count, self._sq_sum / self.count)
        self.mfe = self.alpha * raw[0] + (1 - self.alpha) * self.mfe
        self.mad = self.alpha * raw[1] + (1 - self.alpha) * self.mad
        self.mse = self.alpha * raw[2] + (1 - self.alpha) * self.mse
        values = (abs(self.mfe) / self.scales[0], self.mad / self.scales[1], self.mse / self.scales[2])
        self.guidance = min(1.0, max(0.0, sum(w * v for w, v in zip(self.weights, values))))
        return self.guidance

    def policy(self) -> ControlPolicy:
        g = self.guidance
        if g >= 0.75:
            return ControlPolicy(0, 2, 6, 3, 4, 0.85, True)
        if g >= 0.35:
            return ControlPolicy(1, 1, 4, 2, 3, 0.65, False)
        return ControlPolicy(2, 0, 2, 1, 2, 0.45, False)

    def snapshot(self) -> dict[str, float | int]:
        return {"samples": self.count, "mfe": round(self.mfe, 4), "mad": round(self.mad, 4), "mse": round(self.mse, 4), "guidance": round(self.guidance, 4)}
