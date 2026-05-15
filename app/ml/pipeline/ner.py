import joblib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List


MIN_SPAN_CONFIDENCE = 0.60
MODELS_DIR = Path(__file__).parent.parent / "models"
MODEL_PATH  = MODELS_DIR / "address_ner_crf.pkl"

@dataclass(frozen=True)
class AddressSpan:
    text: str
    confidence: float
    start: int      # індекс першого токена
    end: int        # індекс останнього токена + 1


@dataclass(frozen=True)
class NERResult:
    """Результат витягування адреси з одного тексту."""

    address:    List[AddressSpan]
    tokens:     list[str]
    tags:       list[str]
    elapsed_ms: float

    def __str__(self) -> str:
        if not self.address:
            return "адреса не знайдена"
        return f"знайдено {len(self.address)} адрес(и): " + \
               ", ".join(f"'{a.text}'({a.confidence:.3f})" for a in self.address)

_STREET_ABBR = {
    "вул", "вул.", "вулиця", "просп", "просп.", "проспект",
    "пров", "пров.", "провулок", "бул", "бул.", "бульвар",
    "пл", "пл.", "площа", "пр-т", "шосе", "траса"
}

_ADDR_TRIGGERS = {
    "парк", "парку", "міст", "мосту", "метро", "район", "районі",
    "зупинка", "зупинці", "вокзал", "вокзалу"
}

_ADDR_CONTEXT = _STREET_ABBR | _ADDR_TRIGGERS 

def _word_features(seq: list[str], i: int) -> dict:
    token = seq[i]
    w = token.lower().rstrip(".,")

    features = {
        "bias": 1.0,
        "w.lower": w,
        "w.suffix2": w[-2:] if len(w) >= 2 else w,
        "w.suffix3": w[-3:] if len(w) >= 3 else w,
        "w.prefix3": w[:3] if len(w) >= 3 else w,

        "w.isupper": token.isupper(),
        "w.istitle": token.istitle(),
        "w.isdigit": token.isdigit(),
        "w.isalpha": token.isalpha(),
        "w.has_dash": "–" in token or "-" in token,
        "w.is_street_abbr": w in _STREET_ABBR,
        "w.is_addr_trigger": w in _ADDR_TRIGGERS,
        "w.is_house_num": bool(re.match(r"^\d+[а-яa-z]?(/\d+)?$", token)),
        "w.is_house_range": bool(re.match(r"^\d+[–\-]\d+", token)),
        "w.is_punct": not token[0].isalnum() if token else False,
        "w.ukr_street_end": any(w.endswith(suf) for suf in ["ська", "ький", "ька", "ьке", "ього", "ого", "а", "я"]),
    }

    if i > 0:
        pt = seq[i - 1]
        pw = pt.lower().rstrip(".,")
        features.update({
            "-1:w.lower": pw,
            "-1:w.istitle": pt.istitle(),
            "-1:w.is_abbr": pw in _STREET_ABBR,
            "-1:w.is_trigger": pw in _ADDR_TRIGGERS,
            "-1:w.is_addr_ctx": pw in _ADDR_CONTEXT,
        })
    else:
        features["BOS"] = True

    if i < len(seq) - 1:
        nt = seq[i + 1]
        nw = nt.lower().rstrip(".,")
        features.update({
            "+1:w.lower": nw,
            "+1:w.istitle": nt.istitle(),
            "+1:w.is_house_num": bool(re.match(r"^\d+[а-яa-z]?(/\d+)?$", nt)),
            "+1:w.is_addr_ctx": nw in _ADDR_CONTEXT,
        })
    else:
        features["EOS"] = True

    if i > 0:
        features["-1:w+ w"] = pw + "+" + w
    if i < len(seq) - 1:
        features["+1:w+ w"] = w + "+" + nw

    return features

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+|[.,!?;:\-]", text)
def _build_features(tokens: list[str]) -> list[dict]:
    return [_word_features(tokens, i) for i in range(len(tokens))]


class AddressExtractor:
    _instance: Optional["AddressExtractor"] = None

    def __init__(self, crf, min_confidence: float = MIN_SPAN_CONFIDENCE) -> None:
        self._crf = crf
        self._min_confidence = min_confidence

    @classmethod
    def load(cls, model_path: Path = MODEL_PATH, force_reload: bool = False) -> "AddressExtractor":
        """Завантажує CRF модель (або повертає кешований singleton)."""
        if cls._instance is not None and not force_reload:
            return cls._instance

        if not model_path.exists():
            raise FileNotFoundError(f"Модель не знайдена: {model_path}\n")

        print(f"Завантаження NER моделі: {model_path}")
        t0 = time.perf_counter()

        artifact = joblib.load(model_path)
        crf = artifact.get("model") or artifact
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"NER модель завантажено за {elapsed:.0f}ms")

        cls._instance = cls(crf=crf)
        return cls._instance


    def predict(self, text: str) -> NERResult:

        if not text or not text.strip():
            raise ValueError("Текст не може бути порожнім")

        t0 = time.perf_counter()

        tokens   = _tokenize(text)
        features = _build_features(tokens)

        tags = self._crf.predict_single(features)
        marginals = self._crf.predict_marginals([features])[0]
        spans = self._extract_spans(tokens, tags, marginals)
        elapsed = round((time.perf_counter() - t0) * 1000, 2)

        return NERResult(
            address=spans,
            tokens=tokens,
            tags=tags,
            elapsed_ms=elapsed,
        )

    def predict_batch(self, texts: list[str], batch_size: int = 64) -> list[NERResult]:
        if not texts:
            return []

        t0 = time.perf_counter()
        results = []

        for text in texts:
            results.append(self.predict(text))
        
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"NER: оброблено {len(texts)} текстів за {elapsed:.1f}ms")
        return results

    def _extract_spans(
        self,   
        tokens: list[str],
        tags: list[str],
        marginals: list[dict]
    ) -> list[AddressSpan]:
        """
        Витягує адресні спани з BIO-розмітки.

        Args:
            tokens: список токенів
            tags: BIO теги
            marginals: список {тег: ймовірність} для кожного токена
            (з crf.predict_marginals) для обчислення confidence
        """
        spans = []
        buf_tokens = []
        buf_probs= []
        start_idx = -1

        for i, (token, tag) in enumerate(zip(tokens, tags)):
            if tag.startswith("B-ADDR"):
                if buf_tokens:
                    self._flush_span(buf_tokens, buf_probs, start_idx, spans)
                buf_tokens = [token]
                buf_probs = [marginals[i].get("B-ADDR", 0.0)]
                start_idx = i

            elif tag.startswith("I-ADDR") and buf_tokens:
                buf_tokens.append(token)
                buf_probs.append(marginals[i].get("I-ADDR", 0.0))

            else:
                if buf_tokens:
                    self._flush_span(buf_tokens, buf_probs, start_idx, spans)
                    buf_tokens = []
                    buf_probs = []

        if buf_tokens:
            self._flush_span(buf_tokens, buf_probs, start_idx, spans)

        return spans

    def _flush_span(
        self,
        tokens: list[str],
        probs: list[float],
        start: int,
        spans: list[AddressSpan]
    ):
        if not tokens:
            return
        text = " ".join(tokens)
        confidence = sum(probs) / len(probs)
        spans.append(AddressSpan(
            text=text,
            confidence=confidence,
            start=start,
            end=start + len(tokens)
        ))

    