import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from classifier import ClassificationResult, EventClassifier
from ner import AddressExtractor, NERResult
from noise_filter import NoiseFilter, NoiseFilterResult
from time_extractor import TimeExtractor, TimeResult

NOISE_CLASS = "шум"

@dataclass
class RawMessage:
    text:         str
    source_type:  str
    source_name:  str
    published_at: datetime
    raw_id:       Optional[str] = None

@dataclass
class EnrichedEvent:
    """Збагачена подія."""
    # Ідентифікатори
    id:           str
    raw_id:       Optional[str]

    # Оригінальні поля
    text:         str
    text_clean:   str
    source_type:  str
    source_name:  str
    published_at: datetime

    # Класифікація
    event_type:       str
    event_confidence: float

    # Фільтр шуму
    noise_stage:      str    # "rule_based" | "ml"
    noise_ml_prob:    Optional[float]

    # Адреса
    addresses:    List[str]
    address_raw:  List[AddressExtractor]   

    # Час
    start_time:   Optional[datetime]
    end_time:     Optional[datetime]
    status:       str   # "scheduled" | "active" | "resolved"
    is_planned:   bool
    time_method:  str

    # Метадані pipeline
    created_at:   datetime
    pipeline_ms:  float 

    def to_dict(self) -> dict:
        """Серіалізація для передачі в бекенд / збереження в БД."""
        return {
            "id":                self.id,
            "raw_id":            self.raw_id,
            "text":              self.text,
            "text_clean":        self.text_clean,
            "source_type":       self.source_type,
            "source_name":       self.source_name,
            "published_at":      self.published_at.isoformat(),
            "event_type":        self.event_type,
            "event_confidence":  self.event_confidence,
            "noise_stage":       self.noise_stage,
            "noise_ml_prob":     self.noise_ml_prob,
            "addresses":         self.addresses,
            "address_raw":       self.address_raw,
            "start_time":        self.start_time.isoformat() if self.start_time else None,
            "end_time":          self.end_time.isoformat()   if self.end_time else None,
            "status":            self.status,
            "is_planned":        self.is_planned,
            "time_method":       self.time_method,
            "created_at":        self.created_at.isoformat(),
            "pipeline_ms":       self.pipeline_ms,
        }

@dataclass
class RejectedMessage:
    """Відхилене повідомлення."""
    raw_message:      RawMessage
    rejection_stage:  str    # "classifier" | "noise_filter" | "no_address"
    rejection_reason: str
    event_type:       Optional[str]
    pipeline_ms:      float

@dataclass
class PipelineResult:
    accepted: bool
    event:    Optional[EnrichedEvent] = None
    rejected: Optional[RejectedMessage] = None

    @classmethod
    def accept(cls, event: EnrichedEvent) -> "PipelineResult":
        return cls(accepted=True, event=event)

    @classmethod
    def reject(cls, rejected: RejectedMessage) -> "PipelineResult":
        return cls(accepted=False, rejected=rejected)


def preprocess(text: str) -> str:
    if not text:
        return ""
    result = unicodedata.normalize("NFC", text)
    result = re.sub(r"[\U0001F000-\U0001FFFF]", " ", result)
    result = result.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    result = re.sub(r" {2,}", " ", result)
    return result.strip()

class PipelineRunner:
    """
    Оркестратор ML pipeline.
    Завантажує всі моделі один раз при ініціалізації.
    
    runner = PipelineRunner()        # при старті застосунку
    result = runner.process(message) # для кожного нового повідомлення
    """

    def __init__(self) -> None:
        print("Ініціалізація PipelineRunner. Завантаження моделей...")
        t0 = time.perf_counter()

        self._classifier = EventClassifier.load()
        self._noise = NoiseFilter.load()
        self._ner = AddressExtractor.load()
        self._time = TimeExtractor()

        elapsed = (time.perf_counter() - t0) * 1000
        print(f"PipelineRunner готовий за {elapsed:.0f}ms")

    def process(self, message: RawMessage) -> PipelineResult:

        t0 = time.perf_counter()
        text_clean = preprocess(message.text)
        if not text_clean:
            return PipelineResult.reject(RejectedMessage(
                raw_message=message,
                rejection_stage="preprocessing",
                rejection_reason="порожній текст після очищення",
                event_type=None,
                pipeline_ms=self._elapsed(t0),
            ))

        print(f"Preprocessing: {len(text_clean)} символів")

        clf_result: ClassificationResult = self._classifier.predict(text_clean)
        print(f"Classifier: {clf_result}")

        if clf_result.event_type == NOISE_CLASS:
            return PipelineResult.reject(RejectedMessage(
                raw_message=message,
                rejection_stage="classifier",
                rejection_reason=f"event_type=шум (conf={clf_result.confidence:.3f})",
                event_type=clf_result.event_type,
                pipeline_ms=self._elapsed(t0),
            ))

        noise_result: NoiseFilterResult = self._noise.predict(text_clean)
        print(f"NoiseFilter: {noise_result}")

        if not noise_result.is_actionable:
            return PipelineResult.reject(RejectedMessage(
                raw_message=message,
                rejection_stage="noise_filter",
                rejection_reason=noise_result.reason,
                event_type=clf_result.event_type,
                pipeline_ms=self._elapsed(t0),
            ))

        ner_result: NERResult = self._ner.predict(text_clean)
        print(f"NER: {ner_result}")

        if not ner_result.address:
            return PipelineResult.reject(RejectedMessage(
                raw_message=message,
                rejection_stage="no_address",
                rejection_reason="адреса не знайдена",
                event_type=clf_result.event_type,
                pipeline_ms=self._elapsed(t0),
            ))

        time_result: TimeResult = self._time.extract(text_clean, published_at=message.published_at)
        print(f"Time: {time_result}")

        event = self._build_event(
            message=message,
            text_clean=text_clean,
            clf=clf_result,
            noise=noise_result,
            ner=ner_result,
            time=time_result,
            pipeline_ms=self._elapsed(t0),
        )

        print(f"Accepted [{event.event_type}] addr={event.address_raw or ' - '} | {event.pipeline_ms:.0f}ms")
        return PipelineResult.accept(event)

    def process_batch(self, messages: list[RawMessage], batch_size: int = 32) -> list[PipelineResult]:

        if not messages:
            return []

        t0 = time.perf_counter()
        n = len(messages)
        print(f"Батчева обробка {n} повідомлень (batch_size={batch_size})")

        results: list[Optional[PipelineResult]] = [None] * n

        clean_texts: list[Optional[str]] = []
        for i, msg in enumerate(messages):
            cleaned = preprocess(msg.text)
            if not cleaned:
                results[i] = PipelineResult.reject(RejectedMessage(
                    raw_message=msg,
                    rejection_stage="preprocessing",
                    rejection_reason="порожній текст після очищення",
                    event_type=None,
                    pipeline_ms=0.0,
                ))
                clean_texts.append(None)
            else:
                clean_texts.append(cleaned)

        active = [i for i in range(n) if clean_texts[i] is not None]
        if not active:
            return results
        
        active_texts = [clean_texts[i] for i in active]
        clf_results = self._classifier.predict_batch(active_texts, batch_size=batch_size)

        post_clf: list[int] = []
        for idx, clf_r in zip(active, clf_results):
            if clf_r.event_type == NOISE_CLASS:
                results[idx] = PipelineResult.reject(RejectedMessage(
                    raw_message=messages[idx],
                    rejection_stage="classifier",
                    rejection_reason=f"event_type=шум (conf={clf_r.confidence:.3f})",
                    event_type=clf_r.event_type,
                    pipeline_ms=0.0,
                ))
            else:
                post_clf.append(idx)

        if not post_clf:
            return self._finalize_timing(results, t0) 

        post_clf_texts = [clean_texts[i] for i in post_clf]
        noise_results = self._noise.predict_batch(post_clf_texts, batch_size=batch_size)

        post_noise: list[int] = []
        for idx, noise_r in zip(post_clf, noise_results):
            if not noise_r.is_actionable:
                clf_r = clf_results[active.index(idx)]
                results[idx] = PipelineResult.reject(RejectedMessage(
                    raw_message=messages[idx],
                    rejection_stage="noise_filter",
                    rejection_reason=noise_r.reason,
                    event_type=clf_r.event_type,
                    pipeline_ms=0.0,
                ))
            else:
                post_noise.append(idx)

        if not post_noise:
            print("Немає дійсних повідомлень для подальшої обробки.")
            return self._finalize_timing(results, t0)  

        post_noise_texts = [clean_texts[i] for i in post_noise]
        ner_results = self._ner.predict_batch(post_noise_texts)

        time_needed = [i for i, ner_r in enumerate(ner_results) if ner_r.address]
        time_map: dict[int, TimeResult] = {}  

        if time_needed:
            time_texts = [clean_texts[post_noise[i]] for i in time_needed]
            time_pubs = [messages[post_noise[i]].published_at for i in time_needed]
            time_batch = self._time.extract_batch(time_texts, time_pubs)
            for pos, tr in zip(time_needed, time_batch):
                time_map[pos] = tr

        for pos, idx in enumerate(post_noise):
            clf_r = clf_results[active.index(idx)]
            noise_r = noise_results[post_clf.index(idx)]
            ner_r = ner_results[pos]
            time_r = time_map.get(pos)

            event = self._build_event(
                message=messages[idx],
                text_clean=clean_texts[idx],
                clf=clf_r,
                noise=noise_r,
                ner=ner_r,
                time=time_r,
                pipeline_ms=0.0,
            )
            results[idx] = PipelineResult.accept(event)

        final = self._finalize_timing(results, t0) 

        accepted = sum(1 for r in final if r.accepted)
        print(f"Батч оброблено: {n} вхідних повідомлень, {accepted} прийнято / {n - accepted} відхилено "
              f"| {(time.perf_counter() - t0)*1000:.0f}ms")
        return final


    @staticmethod
    def _build_event(
        message:    RawMessage,
        text_clean: str,
        clf:        ClassificationResult,
        noise:      NoiseFilterResult,
        ner:        NERResult,
        time:       TimeResult,
        pipeline_ms: float,
    ) -> EnrichedEvent:
        addresses_str = [a.text for a in ner.address]
        
        return EnrichedEvent(
            id=str(uuid.uuid4()),
            raw_id=message.raw_id,

            text=message.text,
            text_clean=text_clean,
            source_type=message.source_type,
            source_name=message.source_name,
            published_at=message.published_at,

            event_type=clf.event_type,
            event_confidence=clf.confidence,

            noise_stage=noise.stage,
            noise_ml_prob=noise.ml_prob,

            addresses=addresses_str, 
            address_raw=ner.address,

            start_time=time.start_time if time else None,
            end_time=time.end_time     if time else None,
            status=time.status         if time else "unknown",
            is_planned=time.is_planned if time else False,
            time_method=time.method    if time else "skipped",

            created_at=datetime.now(),
            pipeline_ms=pipeline_ms,
        )

    @staticmethod
    def _elapsed(t0: float) -> float:
        return round((time.perf_counter() - t0) * 1000, 1)

    @staticmethod
    def _finalize_timing(results: list[Optional[PipelineResult]], t0: float) -> list[PipelineResult]:
        """Проставляє pipeline_ms після батчевої обробки."""
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        per_msg = round(elapsed / max(len(results), 1), 1)

        finalized = []
        for r in results:
            if r is None:
                continue
            if r.accepted and r.event:
                object.__setattr__(r.event, "pipeline_ms", per_msg)
            elif not r.accepted and r.rejected:
                object.__setattr__(r.rejected, "pipeline_ms", per_msg)
            finalized.append(r)

        return finalized

