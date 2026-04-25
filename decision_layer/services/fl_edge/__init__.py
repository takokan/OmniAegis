"""Federated edge client package for SentinelAgent Phase-3 privacy layer."""

from .redis_experience_buffer import RedisExperienceBuffer, RedisExperienceBufferConfig, RedisExperienceBufferError
from .shadow_mode import ShadowExecutionManager, ShadowLogger, ShadowMetrics, ShadowModeConfig, ShadowRecord
from .sentinel_env import HistoricalOutcome, RewardWeights, SentinelEnv
from .state_space import SentinelState

__all__ = [
    "HistoricalOutcome",
    "RedisExperienceBuffer",
    "RedisExperienceBufferConfig",
    "RedisExperienceBufferError",
    "RewardWeights",
    "ShadowExecutionManager",
    "ShadowLogger",
    "ShadowMetrics",
    "ShadowModeConfig",
    "ShadowRecord",
    "SentinelEnv",
    "SentinelState",
]
