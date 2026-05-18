import joblib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np

CONFIDENCE_THRESHOLD = 0.70
MODELS_DIR = Path(__file__).parent.parent / "models"
MODEL_PATH = MODELS_DIR / "event_type_classifier.pkl"

from .embeddings import get_encoder

@dataclass(frozen=True)
class ClassificationResult:
    """Результат класифікації одного тексту."""

    event_type:  str
    confidence:  float
    is_reliable: bool      # confidence >= CONFIDENCE_THRESHOLD
    all_probs:   dict[str, float]
    elapsed_ms:  float

    def __str__(self) -> str:
        reliable = "reliable: " if self.is_reliable else "unreliable: "
        return (
            f"{reliable} {self.event_type} "
            f"(confidence={self.confidence:.3f})"
        )

class EventClassifier:
    """
    Класифікатор типу події.
    Завантажує збережений SVM + використовує SentenceTransformer для embeddings.
    Підтримує одиночне і батчеве передбачення.
    Перший виклик завантажує модель. Повторний виклик повертає кешований
    """

    _instance: Optional["EventClassifier"] = None

    def __init__(
        self,
        model,
        label_encoder,
        encoder,
        embedding_model_name: str,
    ):
        self._model = model
        self._label_encoder = label_encoder
        self._encoder = get_encoder()
        self._embedding_model_name = embedding_model_name

    @classmethod
    def load(
        cls,
        model_path: Path = MODEL_PATH,
        force_reload: bool = False,
    ) -> "EventClassifier":
        """
        Завантажує модель (або повертає кешований singleton).

        Args:
            model_path: шлях до event_type_classifier.pkl
            force_reload: примусово перезавантажити
        """
        if cls._instance is not None and not force_reload:
            return cls._instance

        if not model_path.exists():
            raise FileNotFoundError(f"Модель не знайдена: {model_path}\n")

        print(f"Завантаження класифікатора: {model_path}")
        t0 = time.perf_counter()

        artifact = joblib.load(model_path)
        model = artifact["model"]
        label_encoder = artifact["label_encoder"]
        encoder_name = artifact["encoder_name"]

        encoder = get_encoder()
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"Класифікатор завантажено за {elapsed:.0f}ms")

        cls._instance = cls(
            model=model,
            label_encoder=label_encoder,
            encoder=encoder,
            embedding_model_name=encoder_name,
        )
        return cls._instance


    def predict(self, text: str) -> ClassificationResult:
        if not text or not text.strip():
            raise ValueError("Текст не може бути порожнім")

        results = self._predict_batch_internal([text])
        return results[0]

    def predict_batch(self, texts: list[str], batch_size: int = 32) -> list[ClassificationResult]:
        if not texts:
            return []
        return self._predict_batch_internal(texts, batch_size=batch_size)

    def _predict_batch_internal(self, texts: list[str], batch_size: int = 32) -> list[ClassificationResult]:
        """Внутрішній метод батчевого inference."""
        t0 = time.perf_counter()

        embeddings = self._encoder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,)

        proba_matrix = self._model.predict_proba(embeddings)
        predicted_indices = np.argmax(proba_matrix, axis=1)

        elapsed_total = (time.perf_counter() - t0) * 1000
        elapsed_per = elapsed_total / len(texts)

        results = []
        for text, probs, pred_idx in zip(texts, proba_matrix, predicted_indices):
            event_type = self._label_encoder.classes_[pred_idx]
            confidence = float(probs[pred_idx])

            # Словник всіх ймовірностей
            all_probs = {cls: round(float(p), 4)
                         for cls, p in zip(self._label_encoder.classes_, probs)}

            results.append(ClassificationResult(
                event_type=event_type,
                confidence=round(confidence, 4),
                is_reliable=confidence >= CONFIDENCE_THRESHOLD,
                all_probs=all_probs,
                elapsed_ms=round(elapsed_per, 2),
            ))

        print(
            f"Класифіковано {len(texts)} текст(ів) "
            f"за {elapsed_total:.1f}ms "
            f"({elapsed_per:.1f}ms/текст)")

        return results

    @property
    def classes(self) -> list[str]:
        """Список можливих класів у тому самому порядку що і під час навчання."""
        return list(self._label_encoder.classes_)

    @property
    def embedding_model(self) -> str:
        return self._embedding_model_name
