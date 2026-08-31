"""A trivial module, used only where torch is installed."""

import torch
from torch import nn


class Doubler(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * 2
