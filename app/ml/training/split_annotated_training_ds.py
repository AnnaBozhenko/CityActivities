import json
import re
from pathlib import Path

def split_digest_post(text: str) -> list[str]:
    """
    Splits a single compilation post into individual event strings.
    """
    # Розширена регулярка для пошуку 1️⃣, ① та 1.
    split_pattern = re.compile(
        r"(?="
        r"[1-9]️⃣|"               # Keycaps
        r"[①-⑨❶-❾]|"            # Circled numbers
        r"\b[1-9][\.\)\-]\s"      # Standard numbers with punctuation and a space
        r")"
    )
    
    chunks = split_pattern.split(text)
    individual_events = []
    
    for chunk in chunks:
        chunk = chunk.strip()
        
        # 1. Skip intro text
        if len(chunk) < 40 and "Де:" not in chunk and "Коли:" not in chunk:
            continue
            
        # 2. Clean up the outro
        outro_markers = ["До того ж читайте", "Більше івентів", "Підписуйтесь"]
        for marker in outro_markers:
            if marker in chunk:
                chunk = chunk.split(marker)[0].strip()
                
        # 3. Keep chunks that look like real sub-events
        if len(chunk) > 30:
            individual_events.append(chunk)
            
    return individual_events

def main():
    # Шляхи до файлів
    input_path = Path("../data/annotated_scraped_data.json")
    output_path = Path("../data/flattened_annotated_scraped_data.json")

    if not input_path.exists():
        print(f"❌ Файл не знайдено: {input_path}")
        return

    print(f"Відкриваємо {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    flattened_data = [] 
    
    for i, item in enumerate(dataset):
        text = item.get("text", "").strip()
        if not text: 
            continue
        
        base_raw_id = str(item.get("post_id", i))
        
        # ❗️ ЗБЕРІГАЄМО РОЗМІТКУ: Беремо 'event_type' з файлу anno.json
        base_metadata = {
            "source_type": item.get("source_type", "tg"),
            "published_at": item.get("published_at", item.get("pub_date", "")),
            "url": item.get("post_address", item.get("url", "")),
            "address": item.get("address", ""),      
            "event_type": item.get("event_type", ""), # <--- Зберігаємо анотацію!
            "is_actionable": item.get("is_actionable"),
            "is_planned": item.get("is_planned", False)
        }

        # --- THE DIGEST CHECK ---
        sub_events = split_digest_post(text)
        
        if len(sub_events) > 1:
            for sub_index, sub_text in enumerate(sub_events):
                event = {
                    "post_id": f"{base_raw_id}_sub_{sub_index + 1}",
                    "text": sub_text,
                    **base_metadata
                }
                flattened_data.append(event)
        else:
            event = {
                "post_id": base_raw_id,
                "text": text,
                **base_metadata
            }
            flattened_data.append(event)
    
    # Збереження результату
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(flattened_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Успішно! Оброблено {len(dataset)} оригінальних постів.")
    print(f"✅ Отримано {len(flattened_data)} окремих івентів (дайджести розбиті).")
    print(f"💾 Збережено у: {output_path}")

if __name__ == "__main__":
    main()