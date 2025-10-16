from __future__ import annotations

import numpy as np
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def save_confusion_matrix(path: Path, matrix: np.ndarray, class_labels: list[str]) -> Path:
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(class_labels)))
    ax.set_yticks(range(len(class_labels)))
    ax.set_xticklabels(class_labels, rotation=45, ha="right")
    ax.set_yticklabels(class_labels)
    for (i, j), value in np.ndenumerate(matrix):
        ax.text(j, i, int(value), ha="center", va="center", color="black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def save_feature_importances(path: Path, names: list[str], importances: np.ndarray) -> Path:
    if importances.size == 0:
        return path
    order = np.argsort(importances)[::-1][:30]
    top_names = [names[i] for i in order]
    top_importances = importances[order]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.barh(top_names[::-1], top_importances[::-1], color="#7A5195")
    ax.set_xlabel("Importance")
    ax.set_title("Top Feature Importances")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path
