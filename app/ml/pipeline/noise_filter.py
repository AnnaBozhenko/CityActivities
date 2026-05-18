import joblib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np

ML_ACTIONABLE_THRESHOLD = 0.45
MODELS_DIR = Path(__file__).parent.parent / "models"
MODEL_PATH  = MODELS_DIR / "is_actionable_classifier.pkl"

from .embeddings import get_encoder

@dataclass(frozen=True)
class NoiseFilterResult:
    """Результат перевірки одного повідомлення."""

    is_actionable: bool
    stage:         str
    reason:        str
    ml_prob:       Optional[float]
    elapsed_ms:    float

    def __str__(self) -> str:
        icon = "is actionable" if self.is_actionable else "noise"
        return f"{icon} [{self.stage}] {self.reason}"


class NoiseFilter:
    """
    Дворівневий фільтр шуму.
        - rule-based: миттєво відсіює очевидний шум.
        - ML: бінарний класифікатор для граничних випадків.
    """

    _instance: Optional["NoiseFilter"] = None

    def __init__(
        self,
        model,
        encoder,
        threshold: float = ML_ACTIONABLE_THRESHOLD,
    ) -> None:
        self._model = model
        self._encoder = get_encoder()
        self._threshold = threshold
        self._noise_re = self._compile_rules()


    _RULES = {
        "redirect": [
            r"читайте\s+тут", r"дізнайтесь?\s+(?:тут|за\s+посиланням|більше)",
            r"детальніше\s*(?:→|тут|за\s+посиланням|:)", r"підписуйтесь",
            r"більше\s+інформації", r"повний\s+(?:список|графік)",
        ],
        "bare_link": [r"(?<!\S)https?://\S+\s*$"],
        "statistics": [
            r"за\s+(?:цей|минулий|перший|другий|третій|четвертий)\s+(?:рік|квартал|місяць)",
            r"з\s+початку\s+року", r"відремонтовано\s+\d+", r"\d{3,}\s*км",
            r"підсумки?", r"за результатами", r"порівняно з", 
            r"відремонтовано", r"замінено", r"виконано", 
            r"статистика", r"за підсумками",
        ],
        "promo": [
            r"топ[\s\-]\d+", r"рейтинг", r"опитування", r"голосування",
            r"зменшил(?:ася|ося|ись)", r"збільшил(?:ася|ося|ись)",
            r"(?:км|кілометр)\s+доріг", r"тендер",
            r"план\s+розвитку", r"до\s+20\d\d\s+року", 
            r"акція", r"знижка", r"донат", r"збір", r"волонтери",

        ],
        "alarm": [
            r"відбій\s+повітряної?\s+тривоги?", r"відбій повітряної",
            r"тривога\s+відбій",
        ],
    }

    @staticmethod    
    def _compile_rules() -> re.Pattern:
        all_patterns = []
        for patterns in NoiseFilter._RULES.values():
            all_patterns.extend(patterns)
        return re.compile("|".join(all_patterns), flags=re.IGNORECASE | re.UNICODE)
    
    @classmethod
    def load(
        cls,
        model_path: Path = MODEL_PATH,
        force_reload: bool = False,
    ) -> "NoiseFilter":

        if cls._instance is not None and not force_reload:
            return cls._instance

        if not model_path.exists():
            raise FileNotFoundError(f"Модель не знайдена: {model_path}\n")

        print(f"Завантаження noise filter: {model_path}")
        t0 = time.perf_counter()

        artifact = joblib.load(model_path)
        model = artifact.get("model")
        encoder = get_encoder()

        elapsed = (time.perf_counter() - t0) * 1000
        print(f"Noise filter завантажено за {elapsed:.0f}ms")

        cls._instance = cls(model=model, encoder=encoder)
        return cls._instance


    def predict(self, text: str) -> NoiseFilterResult:
        if not text or not text.strip():
            raise ValueError("Текст не може бути порожнім")
        return self._filter_single(text)

    def predict_batch(self, texts: list[str], batch_size: int = 32) -> list[NoiseFilterResult]:

        if not texts:
            return []

        t0 = time.perf_counter()
        results: list[Optional[NoiseFilterResult]] = [None] * len(texts)

        ml_needed_indices = []
        for i, text in enumerate(texts):
            rule_reason = self._apply_rules(text)
            if rule_reason is not None:
                results[i] = NoiseFilterResult(
                    is_actionable=False,
                    stage="rule_based",
                    reason=rule_reason,
                    ml_prob=None,
                    elapsed_ms=0.0,)
            else:
                ml_needed_indices.append(i)

        if ml_needed_indices:
            ml_texts = [texts[i] for i in ml_needed_indices]
            ml_probs = self._ml_predict_proba(ml_texts, batch_size=batch_size)

            for idx, prob in zip(ml_needed_indices, ml_probs):
                results[idx] = self._make_ml_result(prob)

        elapsed = (time.perf_counter() - t0) * 1000
        print(
            f"NoiseFilter: {len(texts)} текст(ів), "
            f"rule_based={len(texts) - len(ml_needed_indices)}, "
            f"ml={len(ml_needed_indices)}, "
            f"elapsed={elapsed:.1f}ms"
        )

        return results  # type: ignore[return-value]


    def _filter_single(self, text: str) -> NoiseFilterResult:
        """Повна перевірка одного тексту."""
        t0 = time.perf_counter()

        rule_reason = self._apply_rules(text)
        if rule_reason is not None:
            return NoiseFilterResult(
                is_actionable=False,
                stage="rule_based",
                reason=rule_reason,
                ml_prob=None,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        prob = self._ml_predict_proba([text])[0]
        result = self._make_ml_result(prob)

        return NoiseFilterResult(
            is_actionable=result.is_actionable,
            stage=result.stage,
            reason=result.reason,
            ml_prob=result.ml_prob,
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    def _apply_rules(self, text: str) -> Optional[str]:
        match = self._noise_re.search(text)
        if match:
            return f"rule: {match.group(0)[:50]}"
        return None


    def _ml_predict_proba(self, texts: list[str], batch_size: int = 32) -> list[float]:

        embeddings = self._encoder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            )
        proba_matrix = self._model.predict_proba(embeddings)
        true_class_idx = list(self._model.classes_).index(True if True in self._model.classes_ else 1)
    
        return [float(row[true_class_idx]) for row in proba_matrix]

    def _make_ml_result(self, prob: float) -> NoiseFilterResult:
        is_actionable = prob >= self._threshold
        return NoiseFilterResult(
            is_actionable=is_actionable,
            stage="ml",
            reason=(
                f"ml_prob={prob:.3f} >= {self._threshold}"
                if is_actionable
                else f"ml_prob={prob:.3f} < {self._threshold}"
            ),
            ml_prob=round(prob, 4),
            elapsed_ms=0.0,
        )

    @property
    def threshold(self) -> float:
        return self._threshold
