"""Model Management (design component C8, REQ-01/04/19).

The rest of the app only talks to the `ChurnModel` interface. A new model
version is trained and swapped in here without touching dashboards or routes
(design pattern: Strategy).
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import ml


class ChurnModel(ABC):
    name: str
    trained_at: str
    input_columns: list[str]
    meta: dict

    @abstractmethod
    def predict_proba(self, raw: pd.DataFrame) -> np.ndarray:
        """Churn probability (0-1) for each customer row."""

    @abstractmethod
    def explain(self, raw: pd.DataFrame, top_n: int = 3) -> list[list[dict]]:
        """Top factors behind each score."""

    @abstractmethod
    def importance(self) -> list[dict]:
        """Global feature importance."""


class SklearnChurnModel(ChurnModel):
    def __init__(self, artifacts: dict):
        self._m = artifacts["model"]
        self._scaler = artifacts["scaler"]
        self._features = artifacts["feature_names"]
        self.name = artifacts["model_name"]
        self.input_columns = artifacts.get("input_columns", ml.INPUT_COLUMNS)
        self.meta = artifacts.get("meta", {})
        self.trained_at = self.meta.get("trained_at", "")

    def predict_proba(self, raw):
        return self._m.predict_proba(self._scaler.transform(ml.build_matrix(raw, self._features)))[:, 1]

    def explain(self, raw, top_n=3):
        return ml.explain_frame(self._m, self._scaler, self._features, raw, top_n)

    def importance(self):
        return ml.feature_importance(self._m, self._features)


class ModelManager:
    """Holds the active model, the prepared training split and the training job state."""

    def __init__(self, models_dir: Path):
        self.dir = Path(models_dir)
        self.model: ChurnModel | None = None
        self.prepared: dict | None = None
        self.job = {"status": "idle", "message": "", "error": None}
        self.lock = threading.Lock()
        self.load()

    def load(self) -> None:
        saved = ml.load_artifacts(self.dir)
        self.model = SklearnChurnModel(saved) if saved else None

    def prepare(self, df: pd.DataFrame) -> dict:
        prepared = ml.prepare_training_data(df)
        with self.lock:
            self.prepared = prepared
        return prepared

    def start_training(self, keys: list[str], use_smote: bool, on_done=None) -> None:
        """Train in a background thread; poll `job` for progress."""
        self.job = {"status": "running", "message": "Starting…", "error": None}
        threading.Thread(target=self._train, args=(keys, use_smote, on_done), daemon=True).start()

    def _train(self, keys, use_smote, on_done) -> None:
        try:
            prep = self.prepared
            results = {}
            for i, key in enumerate(keys):
                self.job["message"] = f"Training {ml.MODEL_LABELS[key]} ({i + 1}/{len(keys)})…"
                model, params = ml.TRAINERS[key](prep["X_train"], prep["y_train"], use_smote)
                results[key] = (model, params, ml.evaluate_model(model, prep["X_test"], prep["y_test"]))
            best_key = max(results, key=lambda k: results[k][2]["auc"])
            model = results[best_key][0]
            meta = {
                "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "labels": ml.MODEL_LABELS,
                "metrics": {k: v[2] for k, v in results.items()},
                "params": {k: v[1] for k, v in results.items()},
                "smote": use_smote,
                "train_rows": len(prep["y_train"]),
                "test_rows": len(prep["y_test"]),
            }
            ml.save_artifacts(self.dir, model, prep["scaler"], prep["feature_names"],
                              ml.MODEL_LABELS[best_key], prep["input_columns"], meta)
            self.load()
            if on_done:  # score customers with the new model before reporting "done"
                self.job = {"status": "running", "message": "Scoring customers with the new model…", "error": None}
                on_done()
            self.job = {"status": "done", "message": f"Best model: {ml.MODEL_LABELS[best_key]}", "error": None}
        except Exception as exc:  # surfaced to the admin on the Data page  # noqa: BLE001 - report any failure to the user
            self.job = {"status": "error", "message": "", "error": str(exc)}
