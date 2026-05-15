"""
Всі datetime повертаються з timezone Europe/Kyiv (UTC+2/UTC+3).
Спроби:
    1. Діапазон start–end
    2. Одиночний час/дата (start або end)
    3. Відносний вираз ("сьогодні", "вчора", "завтра")
    4. Fallback  (published_at як start, +24h як end)
"""

import re
import time as time_module
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import pytz


DEFAULT_TTL_HOURS = 24
KYIV_TZ = pytz.timezone("Europe/Kiev")

_MONTH_MAP: dict[str, int] = {
    "січня": 1,      "січень": 1,
    "лютого": 2,     "лютий": 2,
    "березня": 3,    "березень": 3,
    "квітня": 4,     "квітень": 4,
    "травня": 5,     "травень": 5,
    "червня": 6,     "червень": 6,
    "липня": 7,      "липень": 7,
    "серпня": 8,     "серпень": 8,
    "вересня": 9,    "вересень": 9,
    "жовтня": 10,    "жовтень": 10,
    "листопада": 11, "листопад": 11,
    "грудня": 12,    "грудень": 12,
}

_UK_MONTHS = "(?:" + "|".join(_MONTH_MAP.keys()) + ")"

_PLANNED_SIGNALS = [
    r"планов", r"планується", r"заплановано",
    r"оголошу", r"повідомля",
    r"буде\s+(?:проведено|відключено|обмежено|закрито)",
    r"на\s+період", r"тимчасово",
    r"(?:захід|подія|ремонт|перекриття)\s+(?:відбудеться|пройде|буде)",
]
_PLANNED_RE = re.compile("|".join(_PLANNED_SIGNALS), re.IGNORECASE)


# Кожен елемент: (regex_pattern, handler_name)
_RANGE_PATTERNS: list[tuple[str, str]] = [
    # "з 18 березня 2025 року, 09:30 до 20 березня 18:00"
    (
        r"з\s+(?P<sd>\d{1,2})\s+(?P<sm>" + _UK_MONTHS + r")(?:\s+(?P<sy>\d{4})(?:\s+року)?)?\s*,?\s*"
        r"(?P<st>\d{1,2}:\d{2})\s+до\s+(?P<ed>\d{1,2})\s+(?P<em>" + _UK_MONTHS + r")"
        r"(?:\s+(?P<ey>\d{4})(?:\s+року)?)?\s*,?\s*(?P<et>\d{1,2}:\d{2})",
        "word_date_time_range",
    ),
    # "з 18 квітня 09:30 до 20-го квітня"  (кінець без часу)
    (
        r"з\s+(?P<sd>\d{1,2})\s+(?P<sm>" + _UK_MONTHS + r")(?:\s+(?P<sy>\d{4}))?\s*,?\s*"
        r"(?P<st>\d{1,2}:\d{2})\s+до\s+(?P<ed>\d{1,2})(?:-го|-ї|-ого)?\s+(?P<em>" + _UK_MONTHS + r")"
        r"(?:\s+(?P<ey>\d{4}))?",
        "word_date_time_range_no_end_time",
    ),
    # "з 9.02 09:00 до 15.02 18:00"
    (
        r"з\s+(?P<sd>\d{1,2}\.\d{1,2}(?:\.\d{4})?)\s+(?P<st>\d{1,2}:\d{2})"
        r"\s+до\s+(?P<ed>\d{1,2}\.\d{1,2}(?:\.\d{4})?)\s+(?P<et>\d{1,2}:\d{2})",
        "dot_date_time_range",
    ),
    # "з 09:00 до 18:00" / "від 10:00 до 22:00"
    (
        r"(?:з|від)\s+(?P<start>\d{1,2}:\d{2})\s+до\s+(?P<end>\d{1,2}:\d{2})",
        "time_range",
    ),
    # "09:00–18:00" / "09:00-18:00"
    (
        r"(?P<start>\d{1,2}:\d{2})\s*[-–—]\s*(?P<end>\d{1,2}:\d{2})",
        "time_range",
    ),
    # "з 4 березня по 12 березня"
    (
        r"з\s+(?P<sd>\d{1,2})\s+(?P<sm>" + _UK_MONTHS + r")(?:\s+(?P<sy>\d{4}))?"
        r"\s*(?:до|по|–|—)\s+(?P<ed>\d{1,2})\s+(?P<em>" + _UK_MONTHS + r")(?:\s+(?P<ey>\d{4}))?",
        "word_date_range",
    ),
    # "з 9.02 до 15.02"
    (
        r"з\s+(?P<sd>\d{1,2}\.\d{1,2}(?:\.\d{4})?)\s*(?:до|по|–|—)\s+(?P<ed>\d{1,2}\.\d{1,2}(?:\.\d{4})?)",
        "dot_date_range",
    ),
    # "з 5 по 12 число"
    (
        r"з\s+(?P<sd>\d{1,2})\s+по\s+(?P<ed>\d{1,2})\s+число",
        "day_range",
    ),
]

_SINGLE_PATTERNS: list[tuple[str, str]] = [
    # "до 20:00"
    (r"до\s+(?P<end_time>\d{1,2}:\d{2})", "end_time"),
    # "о 10:00" / "з 10:00" / "в 10:00"
    (r"(?:о|з|в)\s+(?P<time>\d{1,2}:\d{2})", "start_time"),
    # "18 березня 2025" / "18 березня"
    (r"(?P<d>\d{1,2})\s+(?P<m>" + _UK_MONTHS + r")(?:\s+(?P<y>\d{4}))?", "word_date"),
    # "18.03.2025"
    (r"(?P<dot_date>\d{1,2}\.\d{1,2}\.\d{4})", "dot_date"),
]

_COMPILED_RANGE_PATTERNS  = [(re.compile(p, re.IGNORECASE), h) for p, h in _RANGE_PATTERNS]
_COMPILED_SINGLE_PATTERNS = [(re.compile(p, re.IGNORECASE), h) for p, h in _SINGLE_PATTERNS]


@dataclass(frozen=True)
class TimeResult:
    """
    Результат витягування часу з тексту.

    Attributes:
        start_time:  початок події (завжди заповнений, мінімум = published_at)
        end_time:    кінець події  (завжди заповнений, мінімум = start + 24h)
        status:      статус події відносно теперішнього моменту:
                         "scheduled" - подія в майбутньому
                         "active"    - подія зараз
                         "resolved"  - подія в минулому
        is_planned:  True якщо є сигнали запланованості
        raw_extract: знайдений підрядок, None при fallback
        method:      спосіб визначення часу:
                         "range"      - знайдено діапазон start–end
                         "start_only" - знайдено лише start, end = start + 24h
                         "end_only"   - знайдено лише end, start = published_at
                         "date_only"  - знайдено дату без часу
                         "relative"   - відносний вираз (сьогодні/вчора/завтра)
                         "none"       - нічого не знайдено, fallback на published_at
        elapsed_ms:  час виконання
    """
    start_time:  datetime
    end_time:    datetime
    status:      str     
    is_planned:  bool
    raw_extract: Optional[str]
    method:      str
    elapsed_ms:  float

    def to_dict(self) -> dict:
        return {
            "start_time":  self.start_time.isoformat(),
            "end_time":    self.end_time.isoformat(),
            "status":      self.status,
            "is_planned":  self.is_planned,
            "raw_extract": self.raw_extract,
            "method":      self.method,
        }

    def __str__(self) -> str:
        return (
            f"[{self.method}] "
            f"{self.start_time.strftime('%d.%m %H:%M %Z')} – "
            f"{self.end_time.strftime('%d.%m %H:%M %Z')}"
            + (" (planned)" if self.is_planned else "")
        )

def _to_kyiv(dt: datetime) -> datetime:
    return KYIV_TZ.localize(dt) if dt.tzinfo is None else dt.astimezone(KYIV_TZ)

def _make_dt(
    day:     int,
    month:   int,
    year:    Optional[int],
    hour:    int,
    minute:  int,
    base_dt: datetime,
) -> Optional[datetime]:

    base = _to_kyiv(base_dt)
    y = year if year else base.year

    try:
        dt = KYIV_TZ.localize(datetime(y, month, day, hour, minute))
    except ValueError:
        return None

    if not year and (base - dt).days > 30:
        try:
            dt = KYIV_TZ.localize(datetime(y + 1, month, day, hour, minute))
        except ValueError:
            pass
    return dt

def _parse_hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)

def _parse_dot_date(s: str, base_dt: datetime, hour: int = 0, minute: int = 0) -> Optional[datetime]:
    parts = s.strip().split(".")
    if len(parts) < 2:
        return None
    try:
        day = int(parts[0])
        month = int(parts[1])
        year  = int(parts[2]) if len(parts) >= 3 and parts[2] else None
    except ValueError:
        return None
    return _make_dt(day, month, year, hour, minute, base_dt)

def _parse_word_date(
    day_str:   str,
    month_str: str,
    year_str:  Optional[str],
    base_dt:   datetime,
    hour:      int = 0,
    minute:    int = 0,
) -> Optional[datetime]:
    
    month = _MONTH_MAP.get(month_str.lower())
    if not month:
        return None
    try:
        day = int(day_str)
        year = int(year_str) if year_str else None
    except (ValueError, TypeError):
        return None
    return _make_dt(day, month, year, hour, minute, base_dt)

def _handle_range(m: re.Match, handler: str, base_dt: datetime) -> Optional[tuple[datetime, datetime]]:
    gd = m.groupdict()
    base = _to_kyiv(base_dt)

    if handler == "time_range":
        sh, sm = _parse_hm(gd["start"])
        eh, em = _parse_hm(gd["end"])
        start = KYIV_TZ.localize(datetime(base.year, base.month, base.day, sh, sm))
        end   = KYIV_TZ.localize(datetime(base.year, base.month, base.day, eh, em))
        if end <= start:
            end += timedelta(days=1)
        return start, end

    if handler == "dot_date_range":
        start = _parse_dot_date(gd["sd"], base_dt)
        end = _parse_dot_date(gd["ed"], base_dt)
        return (start, end) if start and end else None

    if handler == "dot_date_time_range":
        sh, sm = _parse_hm(gd["st"])
        eh, em = _parse_hm(gd["et"])
        start = _parse_dot_date(gd["sd"], base_dt, sh, sm)
        end = _parse_dot_date(gd["ed"], base_dt, eh, em)
        return (start, end) if start and end else None

    if handler == "word_date_range":
        start = _parse_word_date(gd["sd"], gd["sm"], gd.get("sy"), base_dt)
        end = _parse_word_date(gd["ed"], gd["em"], gd.get("ey"), base_dt)
        if not (start and end):
            return None
        if not gd.get("ey") and end < start:
            end = _make_dt(
                int(gd["ed"]),
                _MONTH_MAP[gd["em"].lower()],
                start.year + 1,
                0, 0, base_dt,
            )
        return (start, end) if start and end else None

    if handler == "word_date_time_range":
        sh, sm = _parse_hm(gd["st"])
        eh, em = _parse_hm(gd["et"])
        start  = _parse_word_date(gd["sd"], gd["sm"], gd.get("sy"), base_dt, sh, sm)
        end    = _parse_word_date(gd["ed"], gd["em"], gd.get("ey"), base_dt, eh, em)
        return (start, end) if start and end else None

    if handler == "word_date_time_range_no_end_time":
        sh, sm = _parse_hm(gd["st"])
        start  = _parse_word_date(gd["sd"], gd["sm"], gd.get("sy"), base_dt, sh, sm)
        end    = _parse_word_date(gd["ed"], gd["em"], gd.get("ey"), base_dt)
        return (start, end) if start and end else None

    if handler == "day_range":
        try:
            start = KYIV_TZ.localize(datetime(base.year, base.month, int(gd["sd"])))
            end   = KYIV_TZ.localize(datetime(base.year, base.month, int(gd["ed"])))
        except ValueError:
            return None
        if end < start:
            next_month = base.month % 12 + 1
            next_year  = base.year + (1 if next_month == 1 else 0)
            try:
                end = KYIV_TZ.localize(datetime(next_year, next_month, int(gd["ed"])))
            except ValueError:
                pass
        return start, end

    return None

def _try_range(text: str, base_dt: datetime) -> Optional[tuple[datetime, datetime, str]]:
    for pattern, handler in _COMPILED_RANGE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        result = _handle_range(m, handler, base_dt)
        if result:
            return result[0], result[1], m.group(0)
    return None

def _try_single(text: str, base_dt: datetime) -> Optional[tuple[Optional[datetime], Optional[datetime], str]]:
    base = _to_kyiv(base_dt)

    for pattern, handler in _COMPILED_SINGLE_PATTERNS:
        m = pattern.search(text)
        if not m: 
            continue
        gd = m.groupdict()

        if handler == "end_time":
            h, mn = _parse_hm(gd["end_time"])
            dt = KYIV_TZ.localize(datetime(base.year, base.month, base.day, h, mn))
            return None, dt, m.group(0)

        if handler == "start_time":
            h, mn = _parse_hm(gd["time"])
            dt = KYIV_TZ.localize(datetime(base.year, base.month, base.day, h, mn))
            return dt, None, m.group(0)

        if handler == "word_date":
            dt = _parse_word_date(gd["d"], gd["m"], gd.get("y"), base_dt)
            if dt: 
                return dt, None, m.group(0)

        if handler == "dot_date":
            dt = _parse_dot_date(gd["dot_date"], base_dt)
            if dt:
                return dt, None, m.group(0)

    return None

def _try_relative(text: str, base_dt: datetime) -> Optional[datetime]:
    base = _to_kyiv(base_dt)
    t = text.lower()

    if "вчора" in t:
        return KYIV_TZ.localize(datetime(base.year, base.month, base.day)) - timedelta(days=1)

    if "завтра" in t:
        return KYIV_TZ.localize(datetime(base.year, base.month, base.day)) + timedelta(days=1)

    if any(h in t for h in ["сьогодні", "зранку", "ввечері", "до вечора", "до кінця дня"]):
        return KYIV_TZ.localize(datetime(base.year, base.month, base.day))

    return None

class TimeExtractor:
    DEFAULT_TTL_HOURS = 24

    def extract(self, text: str, published_at: datetime) -> TimeResult:

        if not text or not text.strip():
            raise ValueError("Текст не може бути порожнім")

        t0 = time_module.perf_counter()
        base_dt = _to_kyiv(published_at)
        is_planned = bool(_PLANNED_RE.search(text))

        range_res = _try_range(text, base_dt)
        if range_res:
            start, end, raw = range_res
            return self._result(start, end, is_planned, raw, "range", t0)

        single_res = _try_single(text, base_dt)
        if single_res:
            start, end, raw = single_res
            if start and not end:
                end = start + timedelta(hours=self.DEFAULT_TTL_HOURS)
                method = "start_only"
            elif end and not start:
                start = base_dt
                method = "end_only"
            else:
                method = "date_only"
                if not end:
                    end = start + timedelta(hours=self.DEFAULT_TTL_HOURS)
            return self._result(start, end, is_planned, raw, method, t0)

        rel_dt = _try_relative(text, base_dt)
        if rel_dt:
            return self._result(
                rel_dt,
                rel_dt + timedelta(hours=self.DEFAULT_TTL_HOURS),
                is_planned, None, "relative", t0,
            )

        print("TimeExtractor: час не знайдено. fallback на published_at")
        return self._result(
            base_dt,
            base_dt + timedelta(hours=self.DEFAULT_TTL_HOURS),
            is_planned, None, "none", t0,
        )

    def extract_batch(self, texts: list[str], published_ats: list[datetime]) -> list[TimeResult]:
        if len(texts) != len(published_ats):
            raise ValueError(
                f"Довжини texts і published_ats мають збігатись: "
                f"{len(texts)} != {len(published_ats)}"
            )
        return [self.extract(t, p) for t, p in zip(texts, published_ats)]

    @staticmethod
    def _result(
        start: datetime,
        end: datetime,
        is_planned: bool,
        raw: Optional[str],
        method: str,
        t0: float,
    ) -> TimeResult:
        now = datetime.now(KYIV_TZ)
        
        if end < now:
            status = "resolved"
        elif start > now:
            status = "scheduled"
        else:
            status = "active"
        
        elapsed = round((time_module.perf_counter() - t0) * 1000, 2)
        print(
            f"TimeExtractor [{method}]: "
            f"{start.strftime('%d.%m %H:%M %Z')} – {end.strftime('%d.%m %H:%M %Z')}"
            + (f" | «{raw}»" if raw else "")
        )
        return TimeResult(
            start_time=start,
            end_time=end,
            status=status,
            is_planned=is_planned,
            raw_extract=raw,
            method=method,
            elapsed_ms=elapsed,
        )
