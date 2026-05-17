import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from runner import PipelineRunner, RawMessage, PipelineResult

INPUT_FILE = ROOT / "data" / "posts.json"
LIMIT = None
USE_BATCH = False

def load_messages(path: Path, limit: int | None = None) -> list[RawMessage]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("Файл має бути JSON масивом")

    if limit: raw = raw[:limit]

    messages = []
    skipped  = 0

    for i, item in enumerate(raw):
        try:
            text = (
                item.get("text")
                or item.get("message")
                or item.get("content")
                or "").strip()

            if not text:
                skipped += 1
                continue

            source_type = (
                item.get("source_type")
                or item.get("source")
                or "unknown")

            source_name = (
                item.get("source_name")
                or item.get("channel")
                or item.get("site")
                or item.get("url", "")[:40]
                or "unknown")

            raw_dt = (
                item.get("published_at")
                or item.get("date")
                or item.get("timestamp")
                or item.get("created_at")
                or item.get("datetime"))
            
            if raw_dt:
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                ]:
                    try:
                        published_at = datetime.strptime(str(raw_dt)[:26], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            messages.append(RawMessage(
                text=text,
                source_type=source_type,
                source_name=source_name,
                published_at=published_at,
                raw_id=str(item.get("id", i)),
            ))

        except Exception as e:
            print(f"Пропущено запис {i}: {e}")
            skipped += 1

    print(f"Завантажено {len(messages)} повідомлень (пропущено: {skipped})")
    return messages

def save_results(results: list[PipelineResult], output_path: Path) -> None:
    events = [
        json.loads(json.dumps(r.event.to_dict(), default=str))
        for r in results
        if r.accepted
    ]
    rejected = [
        {
            "text":             r.rejected.raw_message.text,
            "source_type":      r.rejected.raw_message.source_type,
            "rejection_stage":  r.rejected.rejection_stage,
            "rejection_reason": r.rejected.rejection_reason,
            "event_type":       r.rejected.event_type,
        }
        for r in results
        if not r.accepted
    ]

    events_path   = output_path.parent / "enriched_events.json"
    rejected_path = output_path.parent / "rejected_messages.json"

    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    with open(rejected_path, "w", encoding="utf-8") as f:
        json.dump(rejected, f, ensure_ascii=False, indent=2)

    print(f"Збережено: {events_path}  ({len(events)} подій)")
    print(f"Збережено: {rejected_path}  ({len(rejected)} відхилених)")


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"Файл не знайдено: {INPUT_FILE}")
        sys.exit(1)
    
    messages = load_messages(INPUT_FILE, limit=LIMIT)

    if not messages:
        print("Немає повідомлень для обробки")
        sys.exit(1)

    runner = PipelineRunner()
    t0 = time.perf_counter()

    if USE_BATCH:
        print(f"Батчева обробка {len(messages)} повідомлень...")
        results = runner.process_batch(messages)

    else:
        print(f"Послідовна обробка {len(messages)} повідомлень...")
        results = []
        for i, message in enumerate(messages, 1):
            result = runner.process(message)
            results.append(result)

    save_results(results, INPUT_FILE)
    print(f"Загальний час обробки: {(time.perf_counter() - t0)*1000:.0f}ms")

if __name__ == "__main__":
    main()