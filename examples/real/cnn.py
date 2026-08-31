"""A small convolutional net, trained for real on MNIST.

Deliberately a genuine trained model rather than random weights: the point of adapting a
CNN is that its judgements mean something, and a participant whose outputs are noise proves
nothing about whether the abstraction carries real work.
"""

from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

WEIGHTS = Path(__file__).parent / "mnist_cnn.pt"
DATA = Path(__file__).parent / "data"
CLASSES = tuple(str(d) for d in range(10))


class DigitCNN(nn.Module):
    """Two conv blocks and a classifier. Small enough to train on a laptop in a minute."""

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(32 * 7 * 7, 128),
            nn.ReLU(),
            nn.Dropout(0.25),
            nn.Linear(128, len(CLASSES)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 2:
            x = x.unsqueeze(0).unsqueeze(0)
        elif x.dim() == 3:
            x = x.unsqueeze(1)
        return self.classifier(self.features(x))


def device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def loaders(batch: int = 128) -> tuple[DataLoader, DataLoader]:
    from torchvision import datasets, transforms

    tensorise = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
    )
    train = datasets.MNIST(DATA, train=True, download=True, transform=tensorise)
    test = datasets.MNIST(DATA, train=False, download=True, transform=tensorise)
    return DataLoader(train, batch_size=batch, shuffle=True), DataLoader(test, batch_size=512)


def train(epochs: int = 1) -> float:
    torch.manual_seed(1729)
    model = DigitCNN().to(device())
    train_loader, test_loader = loaders()
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(epochs):
        for step, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device()), labels.to(device())
            optimiser.zero_grad()
            loss_fn(model(images), labels).backward()
            optimiser.step()
            if step % 100 == 0:
                print(f"  epoch {epoch + 1} step {step:>4}", flush=True)

    accuracy = evaluate(model, test_loader)
    torch.save(model.state_dict(), WEIGHTS)
    print(f"  test accuracy {accuracy:.2%}  ->  {WEIGHTS.name}")
    return accuracy


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader) -> float:
    model.eval()
    correct = total = 0
    for images, labels in loader:
        predicted = model(images.to(device())).argmax(dim=1).cpu()
        correct += int((predicted == labels).sum())
        total += len(labels)
    return correct / total


def load() -> DigitCNN:
    if not WEIGHTS.exists():
        raise FileNotFoundError(f"{WEIGHTS} is missing; run: python -m examples.real.cnn")
    model = DigitCNN()
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu"))
    model.eval()
    return model


if __name__ == "__main__":
    train()
