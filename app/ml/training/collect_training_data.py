import json

import asyncio
from telethon import TelegramClient
import configparser

import re
from uuid import uuid4
from pathlib import Path
import sys
from dataclasses import asdict
import datetime

ROOT = Path(__file__).parent.parent
PIPELINE_DIR = ROOT / "pipeline"

# Add both the ml folder AND the pipeline folder to the path
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PIPELINE_DIR))

from pipeline.runner import RawMessage

class DatetimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Read your existing config
config = configparser.ConfigParser()
config.read("../../tg_conn.ini")

API_ID = config["TELEGRAM"].getint("app_id")
API_HASH = config["TELEGRAM"]["app_hash"]
input_path = Path("../data/raw_scraped_data.json")
output_path = Path("../data/scraped_events.json")
# Target channels (e.g., Kyiv Traffic, DTEK, Kyiv City)
CHANNELS = ["kyivmaps", "news44ua",  "KyivCityOfficial", "kyivpatrol", "kyivteploenergo"] 
MESSAGE_LIMIT = 500


def split_digest_post(text: str) -> list[str]:
    """
    Splits a single compilation post into individual event strings.
    """
    # Regex to split on numbered emojis (1️⃣, 2️⃣) or standard numbers (1., 2.)
    # The (?=...) is a lookahead assertion so we don't delete the numbers when splitting.
    split_pattern = re.compile(
        r"(?="
        r"[1-9]️⃣|"               # Keycaps (1️⃣)
        r"[①-⑨❶-❾]|"            # Circled numbers (①, ❶)
        r"\b[1-9][\.\)\-]\s"      # Standard numbers with punctuation and a space (1., 2), 3-)
        r")"
    )
    
    # Split the text
    chunks = split_pattern.split(text)
    
    individual_events = []
    
    for chunk in chunks:
        chunk = chunk.strip()
        
        # 1. Skip intro text (usually doesn't have time/location)
        if len(chunk) < 40 and "Де:" not in chunk and "Коли:" not in chunk:
            continue
            
        # 2. Clean up the outro (usually attached to the last event)
        # Using a common call-to-action keyword to slice off the bottom noise
        outro_markers = ["До того ж читайте", "Більше івентів", "Підписуйтесь"]
        for marker in outro_markers:
            if marker in chunk:
                chunk = chunk.split(marker)[0].strip()
                
        # 3. Keep chunks that look like real sub-events
        if len(chunk) > 30:
            individual_events.append(chunk)
            
    return individual_events


def flatten_messages(path: Path, limit: int | None = None) -> list[RawMessage]:
    with open("../data/raw_scraped_data.json", encoding="utf-8") as f:
        raw = json.load(f)

    flattened_data = [] # [post[event]] -> [event   ]
    
    for i, item in enumerate(raw):
        text = item.get("text", "").strip()
        if not text: continue
        
        # Determine base metadata

        base_raw_id = str(item.get("post_id", i))
        base_metadata = {
            "source_type": item.get("source_type", "tg"),
            "published_at": item.get("published_at", datetime.date.today().strftime('%Y-%m-%d %H:%M:%S')),
            "url": item.get("url", ""),
            "address": "",       # <--- MUST BE EMPTY FOR NER ANNOTATION
            "event_type": "",    # <--- MUST BE EMPTY FOR CLASSIFIER ANNOTATION
            "is_actionable": None,
            "is_planned": False
        }
        # --- THE DIGEST CHECK ---
        # If the text has multiple list markers, treat it as a digest

        
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

    return flattened_data


import uuid

def generate_post_id(channel_id: int, message_id: int) -> str:
    # Create a unique, fixed namespace for your project
    NAMESPACE_TELEGRAM = uuid.UUID('12345678-1234-5678-1234-567812345678')
    
    # Combine the immutable IDs
    unique_string = f"{channel_id}_{message_id}"
    
    # Generate a deterministic UUID
    post_id = uuid.uuid5(NAMESPACE_TELEGRAM, unique_string)
    
    return str(post_id)

# Example Output: 'e4ea20c8-6927-5d51-87ab-5a3d0f1b2181'


async def main():
    # Use your existing session
    client = TelegramClient('anon', API_ID, API_HASH)
    await client.connect()
    
    # 3. Check authorization state cleanly
    if not await client.is_user_authorized():
        # Gather inputs cleanly before feeding them into Telethon
        phone_number = input('👉 Please enter your phone number (with country code, e.g., +380...): ').strip()
        
        try:
            # Request authentication code explicitly
            await client.send_code_request(phone_number)
            code = input('💬 Enter the verification code you received on Telegram: ').strip()
            
            # Sign in
            await client.sign_in(phone=phone_number, code=code)
        except Exception as e:
            print(f"\n❌ Login failed during input validation: {e}")
            return
            
    print("\n✅ Success! 'anon.session' file generated and authenticated.")

    dataset = []
    
    for channel in CHANNELS:
        print(f"Scraping {channel}...")
        try:
            async for msg in client.iter_messages(channel, limit=MESSAGE_LIMIT):
                if msg.text and len(msg.text) > 10:
                    dataset.append({
                        "post_id": generate_post_id(msg.chat_id, msg.id),
                        "text": msg.text.replace("\n", " "),
                        "source_type": "tg",
                        "event_type": "", # To be filled manually
                        "published_at": msg.date.isoformat(),
                        "url": "",
                        "address": "",    # To be filled manually
                        "is_actionable": None,
                        "is_planned": False
                    })
        except Exception as e:
            print(f"Failed to scrape {channel}: {e}")

    flattened_data = [] # [post[event]] -> [event   ]
    
    for i, item in enumerate(dataset):
        text = item.get("text", "").strip()
        if not text: continue
        
        # Determine base metadata

        base_raw_id = str(item.get("post_id", i))
        base_metadata = {
            "source_type": item.get("source_type", "tg"),
            "published_at": item.get("published_at", datetime.date.today().strftime('%Y-%m-%d %H:%M:%S')),
            "url": item.get("url", ""),
            "address": "",       # <--- MUST BE EMPTY FOR NER ANNOTATION
            "event_type": "",    # <--- MUST BE EMPTY FOR CLASSIFIER ANNOTATION
            "is_actionable": None,
            "is_planned": False
        }
        # --- THE DIGEST CHECK ---
        # If the text has multiple list markers, treat it as a digest

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
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(flattened_data, f, ensure_ascii=False, indent=2)
    
    [print(message) for message in flattened_data[:3]]
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())