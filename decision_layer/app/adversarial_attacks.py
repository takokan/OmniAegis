from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn.functional as F


class AdversarialAttackError(RuntimeError):
    """Raised when adversarial attack operations fail."""


class FGSM:
    """Fast Gradient Sign Method attack for generating adversarial examples."""

    def __init__(self, epsilon: float = 0.03) -> None:
        """Initialize FGSM attacker.

        Args:
            epsilon: Perturbation magnitude (L-infinity bound).
        """
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")
        self.epsilon = epsilon

    def __call__(
        self,
        model: torch.nn.Module,
        x: torch.Tensor,
        y: torch.Tensor,
        loss_fn: torch.nn.Module | None = None,
    ) -> torch.Tensor:
        """Generate adversarial examples using FGSM.

        Args:
            model: PyTorch model to attack (must be in eval mode).
            x: Input tensor (batch_size, ...).
            y: Target labels tensor.
            loss_fn: Loss function (default: CrossEntropyLoss).

        Returns:
            Adversarial examples with same shape as x.
        """
        if loss_fn is None:
            loss_fn = torch.nn.CrossEntropyLoss()

        x_adv = x.clone().detach().requires_grad_(True)
        device = x.device

        output = model(x_adv)
        loss = loss_fn(output, y)

        if x_adv.grad is not None:
            x_adv.grad.zero_()

        loss.backward()

        if x_adv.grad is None:
            raise AdversarialAttackError("Gradient computation failed in FGSM")

        grad_sign = x_adv.grad.sign()

        x_adv = x + self.epsilon * grad_sign
        x_adv = torch.clamp(x_adv, 0, 1)

        return x_adv.detach()


class PGD:
    """Projected Gradient Descent attack with multiple random restarts."""

    def __init__(
        self,
        epsilon: float = 0.03,
        alpha: float = 0.003,
        num_steps: int = 20,
        num_restarts: int = 5,
    ) -> None:
        """Initialize PGD attacker.

        Args:
            epsilon: Perturbation magnitude (L-infinity bound).
            alpha: Step size per iteration.
            num_steps: Number of optimization steps.
            num_restarts: Number of random restarts.
        """
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if num_steps <= 0:
            raise ValueError("num_steps must be positive")
        if num_restarts <= 0:
            raise ValueError("num_restarts must be positive")

        self.epsilon = epsilon
        self.alpha = alpha
        self.num_steps = num_steps
        self.num_restarts = num_restarts

    def __call__(
        self,
        model: torch.nn.Module,
        x: torch.Tensor,
        y: torch.Tensor,
        loss_fn: torch.nn.Module | None = None,
    ) -> torch.Tensor:
        """Generate adversarial examples using PGD with random restarts.

        Args:
            model: PyTorch model to attack (must be in eval mode).
            x: Input tensor (batch_size, ...).
            y: Target labels tensor.
            loss_fn: Loss function (default: CrossEntropyLoss).

        Returns:
            Adversarial examples with same shape as x.
        """
        if loss_fn is None:
            loss_fn = torch.nn.CrossEntropyLoss()

        best_adv = None
        best_loss = float("-inf")
        device = x.device

        for restart in range(self.num_restarts):
            delta = torch.empty_like(x).uniform_(-self.epsilon, self.epsilon)
            delta = delta.to(device)

            delta.requires_grad = True
            optimizer = torch.optim.SGD([delta], lr=self.alpha)

            for step in range(self.num_steps):
                optimizer.zero_grad()

                x_adv = x + delta
                x_adv = torch.clamp(x_adv, 0, 1)

                output = model(x_adv)
                loss = loss_fn(output, y)

                loss.backward()
                optimizer.step()

                delta.data = torch.clamp(delta.data, -self.epsilon, self.epsilon)

            x_adv = torch.clamp(x + delta.detach(), 0, 1)

            with torch.no_grad():
                output = model(x_adv)
                loss_val = loss_fn(output, y).item()

            if loss_val > best_loss:
                best_loss = loss_val
                best_adv = x_adv.detach()

            if restart < self.num_restarts - 1:
                delta.detach_()
                del optimizer

        if best_adv is None:
            raise AdversarialAttackError("PGD attack failed to generate adversarial examples")

        return best_adv

    def eval_batch(
        self,
        model: torch.nn.Module,
        x_batch: torch.Tensor,
        y_batch: torch.Tensor,
        loss_fn: torch.nn.Module | None = None,
        batch_size: int = 32,
    ) -> tuple[torch.Tensor, float]:
        """Evaluate model on PGD-attacked examples.

        Args:
            model: PyTorch model to attack.
            x_batch: Batch of inputs.
            y_batch: Batch of labels.
            loss_fn: Loss function.
            batch_size: Process in chunks to save memory.

        Returns:
            Tuple of (adversarial_examples, accuracy).
        """
        device = x_batch.device
        all_adv = []
        correct = 0
        total = 0

        for i in range(0, len(x_batch), batch_size):
            x_chunk = x_batch[i : i + batch_size].to(device)
            y_chunk = y_batch[i : i + batch_size].to(device)

            x_adv_chunk = self(model, x_chunk, y_chunk, loss_fn)
            all_adv.append(x_adv_chunk)

            with torch.no_grad():
                output = model(x_adv_chunk)
                pred = output.argmax(dim=1)
                correct += (pred == y_chunk).sum().item()
                total += y_chunk.size(0)

        x_adv_all = torch.cat(all_adv, dim=0)
        accuracy = correct / total if total > 0 else 0.0

        return x_adv_all, accuracy


__all__ = [
    "FGSM",
    "PGD",
    "AdversarialAttackError",
]
