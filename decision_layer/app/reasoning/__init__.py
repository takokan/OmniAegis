from .calibration import TemperatureScaler, compute_ece
from .explainers import GraphExplainer, VisualExplainer
try:  # optional torch_geometric stack
    from .graph_builder import GraphBuilder
    from .graph_engine import HeteroGATReasoner
    from .model import RightsGNN
except Exception:  # pragma: no cover
    GraphBuilder = None  # type: ignore[assignment]
    HeteroGATReasoner = None  # type: ignore[assignment]
    RightsGNN = None  # type: ignore[assignment]
from .reasoning_gate import DecisionLabel, ReasoningGate, ReasoningResult, reason_about_asset
try:
    from .reasoning_inference import ReasoningInferenceEngine, ReasoningInferenceResult, predict_reasoning
    from .trainer import RightsGNNTrainer, TrainMetrics
except Exception:  # pragma: no cover
    ReasoningInferenceEngine = None  # type: ignore[assignment]
    ReasoningInferenceResult = None  # type: ignore[assignment]
    predict_reasoning = None  # type: ignore[assignment]
    RightsGNNTrainer = None  # type: ignore[assignment]
    TrainMetrics = None  # type: ignore[assignment]

__all__ = [
    "TemperatureScaler",
    "compute_ece",
    "VisualExplainer",
    "GraphExplainer",
    "GraphBuilder",
    "HeteroGATReasoner",
    "RightsGNN",
    "RightsGNNTrainer",
    "TrainMetrics",
    "DecisionLabel",
    "ReasoningGate",
    "ReasoningResult",
    "reason_about_asset",
    "ReasoningInferenceEngine",
    "ReasoningInferenceResult",
    "predict_reasoning",
]
