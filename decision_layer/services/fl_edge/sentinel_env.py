from __future__ import annotations

from dataclasses import dataclass, field
from math import inf
from typing import Any, Mapping, Sequence

import numpy as np

try:  # pragma: no cover - optional runtime dependency
    import gymnasium as gym  # type: ignore[import-not-found]
    from gymnasium import spaces  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - lightweight fallback for environments without gymnasium
    try:
        import gym  # type: ignore[import-not-found]
        from gym import spaces  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # pragma: no cover
        from types import SimpleNamespace

        class _Env:
            pass

        class _Discrete:
            def __init__(self, n: int) -> None:
                self.n = n

            def contains(self, x: Any) -> bool:
                try:
                    value = int(x)
                except (TypeError, ValueError):
                    return False
                return 0 <= value < self.n

        class _Box:
            def __init__(self, low: float, high: float, shape: tuple[int, ...], dtype: Any) -> None:
                self.low = low
                self.high = high
                self.shape = shape
                self.dtype = dtype

        gym = SimpleNamespace(Env=_Env)
        spaces = SimpleNamespace(Discrete=_Discrete, Box=_Box)

from .state_space import SentinelState


@dataclass(frozen=True, slots=True)
class RewardWeights:
    """Tunable reward terms for SentinelEnv."""

    true_positive_auto_enforce: float = 3.0
    false_positive_auto_enforce: float = -5.0
    true_positive_hitl_routing: float = 0.8
    false_positive_hitl_routing: float = -0.4
    missed_infringement_whitelist: float = -4.0
    true_negative_whitelist: float = 1.5
    queue_depth_penalty_per_second: float = -0.005
    reviewer_idle_penalty_per_minute: float = -0.1
    privacy_budget_penalty: float = -1.0


@dataclass(frozen=True, slots=True)
class HistoricalOutcome:
    """Simulated environment outcome for a single Sentinel decision."""

    category: str
    is_infringing: bool
    action: int
    confidence: float
    source: str = "heuristic"
    match_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


class SentinelEnv(gym.Env):  # type: ignore[misc]
    """Gym-compatible SentinelAgent environment.

    Actions:
    - 0: whitelist
    - 1: route to HITL
    - 2: auto-enforce
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        historical_samples: Sequence[Mapping[str, Any]] | None = None,
        reward_weights: RewardWeights | None = None,
        max_steps: int = 200,
        initial_state: SentinelState | None = None,
    ) -> None:
        self.historical_samples = list(historical_samples or [])
        self.reward_weights = reward_weights or RewardWeights()
        self.max_steps = max(1, int(max_steps))
        self._initial_state = initial_state or SentinelState.from_raw({})
        self._state = self._initial_state
        self._step_count = 0
        self._history_index = 0

        self.action_space = spaces.Discrete(3)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(14,), dtype=np.float32)

    @property
    def state(self) -> SentinelState:
        return self._state

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[SentinelState, dict[str, Any]]:
        super().reset(seed=seed)
        self._step_count = 0
        self._history_index = 0
        self._state = self._state_from_history_index(0) or self._initial_state
        return self._state, {"history_index": self._history_index, "source": "reset"}

    def compute_reward(
        self,
        action: int,
        outcome: HistoricalOutcome,
        metrics: Mapping[str, Any],
    ) -> float:
        """Compute a modular reward so the weights can be tuned later."""

        weights = self.reward_weights
        reward = 0.0

        if outcome.category == "true_positive_auto_enforce":
            reward += weights.true_positive_auto_enforce
        elif outcome.category == "false_positive_auto_enforce":
            reward += weights.false_positive_auto_enforce
        elif outcome.category == "true_positive_hitl_routing":
            reward += weights.true_positive_hitl_routing
        elif outcome.category == "false_positive_hitl_routing":
            reward += weights.false_positive_hitl_routing
        elif outcome.category == "missed_infringement_whitelist":
            reward += weights.missed_infringement_whitelist
        elif outcome.category == "true_negative_whitelist":
            reward += weights.true_negative_whitelist

        queue_depth = self._metric_float(metrics, ("queue_depth", "hitl_queue_depth", "backlog"), default=0.0)
        elapsed_seconds = self._metric_float(metrics, ("elapsed_seconds", "dt", "step_seconds"), default=1.0)
        if queue_depth > 0.0:
            reward += weights.queue_depth_penalty_per_second * queue_depth * max(elapsed_seconds, 0.0)

        idle_minutes = self._metric_float(metrics, ("idle_minutes", "reviewer_idle_minutes"), default=0.0)
        if queue_depth > 0.0 and idle_minutes > 0.0:
            reward += weights.reviewer_idle_penalty_per_minute * idle_minutes

        if bool(metrics.get("fl_round_triggered", False)):
            reward += weights.privacy_budget_penalty

        return float(reward)

    def step(
        self,
        action: int,
    ) -> tuple[SentinelState, float, bool, bool, dict[str, Any]]:
        if not self.action_space.contains(action):
            raise ValueError("action must be one of {0, 1, 2}")

        current_state = self._state
        outcome = self._get_historical_outcome(current_state, action)
        metrics = self._build_metrics(current_state, action, outcome)
        reward = self.compute_reward(action=action, outcome=outcome, metrics=metrics)

        next_state = self._next_state(current_state, action, outcome, metrics)
        self._state = next_state
        self._step_count += 1
        self._history_index += 1

        done = self._history_index >= len(self.historical_samples)
        truncated = self._step_count >= self.max_steps

        info = {
            "action": int(action),
            "outcome": outcome.category,
            "is_infringing": outcome.is_infringing,
            "reward_breakdown": self._reward_breakdown(action, outcome, metrics),
            "history_index": self._history_index,
            "source": outcome.source,
            "match_score": outcome.match_score,
        }
        return next_state, reward, done, truncated, info

    def _get_historical_outcome(self, state: SentinelState, action: int) -> HistoricalOutcome:
        if self.historical_samples:
            sample = self._historical_sample_for_step()
            if sample is not None:
                return self._outcome_from_sample(sample, state, action)

        return self._heuristic_outcome(state, action)

    def _historical_sample_for_step(self) -> Mapping[str, Any] | None:
        if not self.historical_samples:
            return None
        index = min(self._history_index, len(self.historical_samples) - 1)
        sample = self.historical_samples[index]
        return sample

    def _outcome_from_sample(self, sample: Mapping[str, Any], state: SentinelState, action: int) -> HistoricalOutcome:
        sample_state = self._sample_state(sample)
        match_score = self._state_similarity(state, sample_state) if sample_state is not None else 0.0
        actual_infringing = self._sample_bool(sample, ("is_infringing", "ground_truth_infringing", "label"))
        if actual_infringing is None:
            actual_infringing = self._heuristic_is_infringing(state)

        return self._categorize_outcome(
            action=action,
            is_infringing=bool(actual_infringing),
            confidence=self._sample_float(sample, ("confidence", "score", "risk_score"), default=state.calibrated_confidence),
            source="historical",
            match_score=match_score,
            metadata=dict(sample),
        )

    def _heuristic_outcome(self, state: SentinelState, action: int) -> HistoricalOutcome:
        is_infringing = self._heuristic_is_infringing(state)
        return self._categorize_outcome(
            action=action,
            is_infringing=is_infringing,
            confidence=state.calibrated_confidence,
            source="heuristic",
            match_score=self._heuristic_match_score(state),
            metadata={"uncertainty": state.uncertainty},
        )

    def _categorize_outcome(
        self,
        *,
        action: int,
        is_infringing: bool,
        confidence: float,
        source: str,
        match_score: float,
        metadata: dict[str, Any],
    ) -> HistoricalOutcome:
        if action == 2:
            category = "true_positive_auto_enforce" if is_infringing else "false_positive_auto_enforce"
        elif action == 1:
            category = "true_positive_hitl_routing" if is_infringing else "false_positive_hitl_routing"
        else:
            category = "missed_infringement_whitelist" if is_infringing else "true_negative_whitelist"

        return HistoricalOutcome(
            category=category,
            is_infringing=is_infringing,
            action=action,
            confidence=float(np.clip(confidence, 0.0, 1.0)),
            source=source,
            match_score=float(np.clip(match_score, 0.0, 1.0)),
            metadata=metadata,
        )

    def _heuristic_is_infringing(self, state: SentinelState) -> bool:
        risk_signal = (
            0.55 * state.calibrated_confidence
            + 0.20 * state.uncertainty
            + 0.10 * state.false_positive_rate_2h
            + 0.10 * state.hitl_overturn_rate_2h
            + 0.05 * (1.0 - state.privacy_budget)
        )
        return risk_signal >= 0.55

    def _heuristic_match_score(self, state: SentinelState) -> float:
        queue_pressure = state.hitl_queue_depth
        reviewer_capacity = state.reviewer_capacity
        return float(np.clip(0.5 * state.calibrated_confidence + 0.25 * queue_pressure + 0.25 * (1.0 - reviewer_capacity), 0.0, 1.0))

    def _build_metrics(self, state: SentinelState, action: int, outcome: HistoricalOutcome) -> dict[str, Any]:
        queue_depth = self._state_queue_depth(state)
        idle_minutes = self._estimated_idle_minutes(state, action)
        return {
            "queue_depth": queue_depth,
            "idle_minutes": idle_minutes,
            "elapsed_seconds": 1.0,
            "fl_round_triggered": action == 2 and state.privacy_budget <= 0.25,
            "outcome": outcome.category,
            "confidence": outcome.confidence,
            "match_score": outcome.match_score,
        }

    def _reward_breakdown(
        self,
        action: int,
        outcome: HistoricalOutcome,
        metrics: Mapping[str, Any],
    ) -> dict[str, float]:
        weights = self.reward_weights
        breakdown = {
            "base": 0.0,
            "queue_depth_penalty": 0.0,
            "reviewer_idle_penalty": 0.0,
            "privacy_budget_penalty": 0.0,
        }

        if outcome.category == "true_positive_auto_enforce":
            breakdown["base"] = weights.true_positive_auto_enforce
        elif outcome.category == "false_positive_auto_enforce":
            breakdown["base"] = weights.false_positive_auto_enforce
        elif outcome.category == "true_positive_hitl_routing":
            breakdown["base"] = weights.true_positive_hitl_routing
        elif outcome.category == "false_positive_hitl_routing":
            breakdown["base"] = weights.false_positive_hitl_routing
        elif outcome.category == "missed_infringement_whitelist":
            breakdown["base"] = weights.missed_infringement_whitelist
        elif outcome.category == "true_negative_whitelist":
            breakdown["base"] = weights.true_negative_whitelist

        queue_depth = self._metric_float(metrics, ("queue_depth", "hitl_queue_depth", "backlog"), default=0.0)
        elapsed_seconds = self._metric_float(metrics, ("elapsed_seconds", "dt", "step_seconds"), default=1.0)
        breakdown["queue_depth_penalty"] = weights.queue_depth_penalty_per_second * queue_depth * max(elapsed_seconds, 0.0)

        idle_minutes = self._metric_float(metrics, ("idle_minutes", "reviewer_idle_minutes"), default=0.0)
        if queue_depth > 0.0:
            breakdown["reviewer_idle_penalty"] = weights.reviewer_idle_penalty_per_minute * idle_minutes

        if bool(metrics.get("fl_round_triggered", False)):
            breakdown["privacy_budget_penalty"] = weights.privacy_budget_penalty

        return breakdown

    def _next_state(
        self,
        current_state: SentinelState,
        action: int,
        outcome: HistoricalOutcome,
        metrics: Mapping[str, Any],
    ) -> SentinelState:
        historical_next = self._state_from_history_index(self._history_index + 1)
        if historical_next is not None:
            return historical_next

        queue_depth = self._state_queue_depth(current_state)
        reviewer_capacity = current_state.reviewer_capacity
        privacy_budget = current_state.privacy_budget
        model_age = current_state.model_age

        if action == 1:
            queue_depth = max(0.0, queue_depth - 0.08)
        elif action == 2:
            queue_depth = max(0.0, queue_depth - 0.12)
            privacy_budget = max(0.0, privacy_budget - 0.02)
        else:
            queue_depth = min(1.0, queue_depth + 0.02)

        if bool(metrics.get("fl_round_triggered", False)):
            privacy_budget = max(0.0, privacy_budget - 0.1)

        if outcome.category in {"false_positive_auto_enforce", "false_positive_hitl_routing"}:
            reviewer_capacity = max(0.0, reviewer_capacity - 0.05)
        elif outcome.category == "true_positive_hitl_routing":
            reviewer_capacity = min(1.0, reviewer_capacity + 0.01)

        model_age = min(1.0, model_age + 1.0 / 365.0)
        time_sin, time_cos = current_state.time_of_day_sin, current_state.time_of_day_cos

        return SentinelState(
            calibrated_confidence=float(np.clip(current_state.calibrated_confidence, 0.0, 1.0)),
            uncertainty=float(np.clip(current_state.uncertainty, 0.0, 1.0)),
            content_type_text=current_state.content_type_text,
            content_type_image=current_state.content_type_image,
            content_type_audio=current_state.content_type_audio,
            content_type_video=current_state.content_type_video,
            hitl_queue_depth=float(np.clip(queue_depth, 0.0, 1.0)),
            reviewer_capacity=float(np.clip(reviewer_capacity, 0.0, 1.0)),
            false_positive_rate_2h=current_state.false_positive_rate_2h,
            hitl_overturn_rate_2h=current_state.hitl_overturn_rate_2h,
            privacy_budget=float(np.clip(privacy_budget, 0.0, 1.0)),
            model_age=float(np.clip(model_age, 0.0, 1.0)),
            time_of_day_sin=time_sin,
            time_of_day_cos=time_cos,
            vector=np.asarray(
                [
                    current_state.calibrated_confidence,
                    current_state.uncertainty,
                    current_state.content_type_text,
                    current_state.content_type_image,
                    current_state.content_type_audio,
                    current_state.content_type_video,
                    float(np.clip(queue_depth, 0.0, 1.0)),
                    float(np.clip(reviewer_capacity, 0.0, 1.0)),
                    current_state.false_positive_rate_2h,
                    current_state.hitl_overturn_rate_2h,
                    float(np.clip(privacy_budget, 0.0, 1.0)),
                    float(np.clip(model_age, 0.0, 1.0)),
                    time_sin,
                    time_cos,
                ],
                dtype=np.float32,
            ),
        )

    def _state_from_history_index(self, index: int) -> SentinelState | None:
        if not self.historical_samples:
            return None
        if index < 0 or index >= len(self.historical_samples):
            return None
        sample = self.historical_samples[index]
        raw_state = sample.get("state") if isinstance(sample, Mapping) else None
        if isinstance(raw_state, Mapping):
            return SentinelState.from_raw(raw_state)

        if isinstance(sample, Mapping):
            state_keys = {
                key: sample[key]
                for key in (
                    "calibrated_confidence",
                    "confidence",
                    "uncertainty",
                    "content_type",
                    "hitl_queue_depth",
                    "queue_depth",
                    "reviewer_capacity",
                    "reviewer_count",
                    "false_positive_rate_2h",
                    "false_positive_rate",
                    "hitl_overturn_rate_2h",
                    "overturn_rate",
                    "privacy_budget",
                    "privacy_budget_remaining",
                    "model_age",
                    "model_age_days",
                    "model_age_hours",
                    "hour",
                    "hour_of_day",
                )
                if key in sample
            }
            if state_keys:
                return SentinelState.from_raw(state_keys)
        return None

    def _sample_state(self, sample: Mapping[str, Any]) -> SentinelState | None:
        raw_state = sample.get("state")
        if isinstance(raw_state, Mapping):
            return SentinelState.from_raw(raw_state)
        return self._state_from_history_index(self._history_index)

    def _sample_bool(self, sample: Mapping[str, Any], keys: Sequence[str]) -> bool | None:
        for key in keys:
            if key not in sample:
                continue
            value = sample[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "infringing", "positive"}:
                    return True
                if normalized in {"0", "false", "no", "whitelist", "negative"}:
                    return False
            try:
                return bool(int(value))
            except (TypeError, ValueError):
                continue
        return None

    def _sample_float(self, sample: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
        for key in keys:
            if key not in sample:
                continue
            try:
                return float(sample[key])
            except (TypeError, ValueError):
                continue
        return float(default)

    def _state_similarity(self, left: SentinelState, right: SentinelState | None) -> float:
        if right is None:
            return 0.0
        delta = left.as_array() - right.as_array()
        distance = float(np.linalg.norm(delta))
        return float(np.clip(1.0 - min(distance, np.sqrt(delta.size)), 0.0, 1.0))

    def _state_queue_depth(self, state: SentinelState) -> float:
        return float(np.clip(state.hitl_queue_depth * 200.0, 0.0, inf))

    def _estimated_idle_minutes(self, state: SentinelState, action: int) -> float:
        if action == 1:
            return max(0.0, 10.0 * (1.0 - state.reviewer_capacity))
        if action == 0:
            return max(0.0, 15.0 * state.hitl_queue_depth)
        return max(0.0, 5.0 * state.hitl_queue_depth)

    @staticmethod
    def _metric_float(metrics: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
        for key in keys:
            value = metrics.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return float(default)


__all__ = ["HistoricalOutcome", "RewardWeights", "SentinelEnv"]
