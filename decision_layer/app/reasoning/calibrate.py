from __future__ import annotations

import argparse
import json
from importlib import import_module
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


def _binary_nll(logits: np.ndarray, targets: np.ndarray, temperature: float) -> float:
    t = max(float(temperature), 1e-6)
    probs = expit(logits / t)
    probs = np.clip(probs, 1e-9, 1.0 - 1e-9)
    nll = -(targets * np.log(probs) + (1.0 - targets) * np.log(1.0 - probs)).mean()
    return float(nll)


def fit_temperature(logits: np.ndarray, targets: np.ndarray, init_temperature: float = 1.0) -> float:
    logits = np.asarray(logits, dtype=np.float64).reshape(-1)
    targets = np.asarray(targets, dtype=np.float64).reshape(-1)

    if logits.size == 0 or targets.size == 0:
        raise ValueError("Validation logits/targets cannot be empty")
    if logits.size != targets.size:
        raise ValueError("logits and targets must have the same length")

    # Optimize in log-space to enforce T > 0.
    x0 = np.array([np.log(max(init_temperature, 1e-6))], dtype=np.float64)

    def objective(log_t: np.ndarray) -> float:
        t = float(np.exp(log_t[0]))
        return _binary_nll(logits, targets, t)

    result = minimize(objective, x0=x0, method="L-BFGS-B")
    if not result.success:
        raise RuntimeError(f"Temperature optimization failed: {result.message}")

    return float(np.exp(result.x[0]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate RightsGNN logits using temperature scaling")
    parser.add_argument("--input", required=True, help="Path to .npz containing arrays: logits, targets")
    parser.add_argument("--output", default="temperature.json", help="Output JSON path")
    parser.add_argument("--init-temperature", type=float, default=1.0, help="Initial temperature")
    args = parser.parse_args()

    data = np.load(args.input)
    if "logits" not in data or "targets" not in data:
        raise ValueError("Input .npz must contain `logits` and `targets`")

    logits = np.asarray(data["logits"], dtype=np.float64).reshape(-1)
    targets = np.asarray(data["targets"], dtype=np.float64).reshape(-1)

    optimal_t = fit_temperature(logits=logits, targets=targets, init_temperature=args.init_temperature)

    calibration_module = import_module("decision_layer_gate.app.reasoning.calibration")
    compute_ece = getattr(calibration_module, "compute_ece")

    raw_probs = expit(logits)
    cal_probs = expit(logits / max(optimal_t, 1e-6))

    report = {
        "temperature": optimal_t,
        "n_samples": int(logits.size),
        "nll_before": _binary_nll(logits, targets, 1.0),
        "nll_after": _binary_nll(logits, targets, optimal_t),
        "ece_before": compute_ece(raw_probs, targets.astype(np.int64), n_bins=10),
        "ece_after": compute_ece(cal_probs, targets.astype(np.int64), n_bins=10),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
