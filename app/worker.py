from main import broker
import asyncpg

import dotenv
import configparser
from datetime import datetime, date
import re
import uuid
from telethon import TelegramClient
import random
import os

import httpx
from bs4 import BeautifulSoup
import json
import urllib.parse

from shapely.geometry import LineString, Point

from ml.pipeline.runner import PipelineRunner, RawMessage

dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("tg_conn.ini")

database_url = config["POSTGRES"]["DATABASE_URL"]
TELEGRAM_API_ID = config["TELEGRAM"].getint("app_id")
TELEGRAM_API_HASH = config["TELEGRAM"]["app_hash"]
# Important: Define target channels here
TELEGRAM_CHANNELS = ["KyivCityOfficial", "dtek_ua", "kyivmaps", "kievreal1", "kyivteploenergo", "autokiev", "kyivpatrol"]
KYIV_REGION_ID = "31"
tg_client = None
ml_runner = None

async def get_db_conn():
    return await asyncpg.connect(database_url)


def get_tg_client():
    global tg_client
    if tg_client is None:
        tg_client = TelegramClient('anon', TELEGRAM_API_ID, TELEGRAM_API_HASH)
    return tg_client


def get_ml_runner():
    global ml_runner
    if ml_runner is None:
        print("Initializing ML Pipeline in Worker Memory...")
        ml_runner = PipelineRunner()
        print("ML Pipeline Ready.")
    return ml_runner

@broker.on_event("startup")
async def startup_event():
    global tg_client
    tg_client = get_tg_client()
    await tg_client.connect()


def generate_post_id(channel_id: int, message_id: int) -> str:
    # Create a unique, fixed namespace for your project
    NAMESPACE_TELEGRAM = uuid.UUID('12345678-1234-5678-1234-567812345678')
    
    # Combine the immutable IDs
    unique_string = f"{channel_id}_{message_id}"
    
    # Generate a deterministic UUID
    post_id = uuid.uuid5(NAMESPACE_TELEGRAM, unique_string)
    
    return str(post_id)



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


@broker.task(schedule=[
    {"cron": "* * * * *", "args": ["tg"], "labels": {"source": "Telegram"}}
])
async def fetch_news_task(source_type: str):
    conn = await get_db_conn()
    
    if source_type == "tg":
        tg_client = get_tg_client()
        # Ensure client is connected
        if not tg_client.is_connected():
            await tg_client.connect()

        all_posts = []
        for channel_name in TELEGRAM_CHANNELS:
            try:
                # Fetch only the latest 5 messages to avoid redundant processing
                async for message in tg_client.iter_messages(channel_name, limit=5):
                    if not message.text:
                        continue
                    
                    # Create a unique URL for the Telegram post to satisfy DB unique constraints
                    post_url = f"https://t.me/{channel_name}/{message.id}"
                    text = message.text.replace("\n", " ")
                    text_marked = re.sub(r'\s{2,}', ' __SPACE__ ', text)
                    text_fixed = re.sub(r'(?<=\S)\s(?=\S)', '', text_marked)
                    text_fixed = text_fixed.replace('__SPACE__', ' ')
                    
                    text = " ".join(text)
                    # Standardize data to match your DB schema
                    all_posts.append({
                        "post_id": generate_post_id(message.chat_id, message.id),
                        "source_type": "tg",
                        "source_name": channel_name,
                        "url": post_url,
                        "news_text": text,
                        "published_at": message.date # Telethon returns timezone-aware datetime
                    })
            except Exception as e:
                print(f"Error scraping {channel_name}: {e}")
        
        new_posts_count = 0
        # Now use your existing insertion logic
        for item in all_posts:
            news_id = await conn.fetchval("""
                INSERT INTO raw.news (post_id, source_type, source_name, url, news_text, published_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (url) DO NOTHING RETURNING post_id;
            """, item['post_id'], item['source_type'], item["source_name"], item['url'], item['news_text'], item['published_at'])
            
            if news_id:
                print(f" [TG] New post ingested: {news_id}")
                new_posts_count += 1
        if new_posts_count > 0:
            await enrich_news_batch_task.kiq()

    elif source_type == "web":
        # ... (Your Web Scraping Logic here) ...
        pass

    await conn.close()


@broker.task(schedule=[{"cron": "*/5 * * * *"}]) # Запуск кожні 5 хв
async def enrich_news_batch_task():
    ml_runner = get_ml_runner()
    conn = await get_db_conn() # Ваша функція підключення до Postgres
    
    try:
        # 1. Беремо пости, для яких ЩЕ НЕМАЄ записів в enriched.city_event або rejected_noise
        rows = await conn.fetch("""
            SELECT n.post_id, n.news_text, n.source_type, 
                   n.source_name, n.published_at, n.url
            FROM raw.news n
            WHERE NOT EXISTS (SELECT 1 FROM enriched.city_event e WHERE e.post_id = n.post_id)
              AND NOT EXISTS (SELECT 1 FROM enriched.rejected_noise r WHERE r.post_id = n.post_id)
            LIMIT 50;
        """)

        if not rows:
            return

        # 2. Формуємо повідомлення для ML, розбиваючи дайджести
        raw_messages = []
        for row in rows:
            base_id = row['post_id']
            text = row['news_text']

            sub_events = split_digest_post(text)

            if len(sub_events) > 1:
                for i, sub_text in enumerate(sub_events):
                    raw_messages.append(RawMessage(
                        text=sub_text,
                        source_type=row['source_type'],
                        source_name=row['source_name'],
                        url=row['url'], 
                        published_at=row['published_at'],
                        raw_id=f"{base_id}_sub_{i}" # Унікальний ID для спліта
                    ))
            else:
                raw_messages.append(RawMessage(
                    text=text,
                    source_type=row['source_type'],
                    source_name=row['source_name'],
                    url=row['url'],
                    published_at=row['published_at'],
                    raw_id=str(base_id)
                ))

        # 3. Запускаємо БАТЧЕВУ ML Обробку
        print(f" [ML] Starting inference for {len(raw_messages)} prepared events...")
        results = ml_runner.process_batch(raw_messages, batch_size=32)

        # 4. Розбираємо результати та записуємо в базу
        for result in results:
            if result is None:
                continue
            # Витягуємо оригінальний news_id (наприклад, з "45_sub_1" робимо int(45))
            raw_id_str = result.event.raw_id if result.accepted else result.rejected.raw_message.raw_id
            base_news_id = str(raw_id_str).split("_sub_")[0]

            if result.accepted:
                ev = result.event
                await conn.execute("""
                    INSERT INTO enriched.city_event 
                    (event_id, post_id, source_type, event_type, confidence, start_time, end_time, status, is_planned, extracted_addresses, pipeline_ms)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """, 
                ev.id, base_news_id, ev.source_type, ev.event_type, ev.event_confidence, 
                ev.start_time, ev.end_time, ev.status, ev.is_planned, 
                ev.addresses, ev.pipeline_ms)
                
            else:
                rej = result.rejected
                await conn.execute("""
                    INSERT INTO enriched.rejected_noise 
                    (post_id, rejection_stage, rejection_reason, event_type)
                    VALUES ($1, $2, $3, $4)
                """, base_news_id, rej.rejection_stage, rej.rejection_reason, rej.event_type)

        print(f" [ML] Successfully processed batch of {len(rows)} raw posts into {len(raw_messages)} sub-events.")

    finally:
        await conn.close()


@broker.task(
        schedule=[{
            "cron":"*/2 * * * *", 
            "labels": {"source": "Traffic Collector"}
        }]
)
async def get_kyiv_air_raid_status():
    token = config["UKRAINEALARM"]["api_token"]
    url = f"https://api.ukrainealarm.com/api/v3/alerts/{KYIV_REGION_ID}"
    
    headers = {"Authorization": token}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                print(f" [!] Alarm API Error: {response.status_code}")
                return False
            
            data = response.json()
            
            # The API returns a list of regions with active alerts.
            # If the list is empty or our region isn't in 'activeAlerts', there's no raid.
            if not data:
                return False
            
            # The data format for /alerts/{id} returns an object for that specific region
            # We check if 'activeAlerts' contains any entries for this region
            active_alerts = data[0].get('activeAlerts', [])
            return len(active_alerts) > 0
            
    except Exception as e:
        print(f" [ER] Air Raid check failed: {e}")
        return False
    

@broker.task(schedule=[{"cron": "*/2 * * * *"}]) # Run every 2 minutes
async def update_infrastructure_task():
    conn = await get_db_conn()
    tomtom_key = config["TOMTOM"]["api_key"]
    
    # Kyiv Bounding Box
    minLon, minLat, maxLon, maxLat = 30.20, 50.35, 30.75, 50.55
    
    url = (
        f"https://api.tomtom.com/traffic/services/5/incidentDetails?key={tomtom_key}"
        f"&bbox={minLon},{minLat},{maxLon},{maxLat}"
        f"&fields={{incidents{{type,geometry{{type,coordinates}},properties{{iconCategory}}}}}}"
        f"&language=en-GB&t=1111&timeValidityFilter=present"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            data = response.json()

        if "incidents" not in data:
            print(" [i] No traffic incidents found in the current area.")
            return

        for inc in data["incidents"]:
            # 1. Map Icon Category to your ID system
            icon_cat = str(inc['properties']['iconCategory'])
            
            # 2. Extract Geometry and convert to WKT
            # TomTom coords are [lon, lat]. WKT expects "lon lat"
            coords = inc['geometry']['coordinates']
            geom_type = inc['geometry']['type']
            
            if geom_type == "LineString":
                # Create 'LON LAT, LON LAT' string
                wkt_coords = ", ".join([f"{c[0]} {c[1]}" for c in coords])
                wkt_geom = f"LINESTRING({wkt_coords})"
            else:
                # Fallback for Point data
                wkt_geom = f"POINT({coords[0]} {coords[1]})"

            # 3. Create a unique ID for ON CONFLICT
            # We can use a hash of the coordinates or TomTom's ID if available. 
            # Here we use a hash of WKT for stability.
            external_id = f"tt_{hash(wkt_geom)}"

            await conn.execute("""
                INSERT INTO alerts.traffic_incident (external_id, incident_type, geom, updated_at)
                VALUES ($1, $2, ST_GeomFromText($3, 4326), NOW())
                ON CONFLICT (external_id) 
                DO UPDATE SET updated_at = NOW();
            """, external_id, int(icon_cat), wkt_geom)

        print(f" [OK] Traffic update complete: Processed {len(data['incidents'])} incidents.")

        # Mock Air Raid
        is_active = await get_kyiv_air_raid_status()
        await conn.execute("""
        INSERT INTO alerts.air_raid (is_active, activated_at) 
        VALUES ($1, NOW())
        ON CONFLICT (air_raid_id) DO UPDATE SET 
            is_active = EXCLUDED.is_active,
            activated_at = CASE 
                WHEN alerts.air_raid.is_active != EXCLUDED.is_active THEN NOW() 
                ELSE alerts.air_raid.activated_at 
            END;
        """, is_active)
    
        status_text = "ALARM" if is_active else "CLEAR"
        print(f" [i] Kyiv Air Raid Status: {status_text}")

    except Exception as e:
        print(f" [ER] TomTom Fetch Failed: {e}")
    finally:
        await conn.close()
    

@broker.task(
        schedule=[
            {"cron": "0 0,12 * * *"} # every midnight, midday
        ]
)
async def daily_electricity_sync():
    conn = await get_db_conn()
    addresses = await conn.fetch("SELECT address_id FROM electricity.address LIMIT 10") # Test small batch
    
    for addr in addresses:
        mock_slots = [random.choice([True, False]) for _ in range(48)]
        await conn.execute("""
            INSERT INTO electricity.electricity_schedule (address_id, schedule_date, time_slots)
            VALUES ($1, CURRENT_DATE, $2)
            ON CONFLICT (address_id, schedule_date) DO UPDATE SET time_slots = $2;
        """, addr['address_id'], mock_slots)
    await conn.close()


def generate_electricity_url(row: dict) -> str | None:
    """
    Parses a database row and generates the energy-ua.info URL.
    Returns None if the building number contains complex formats like '/'.
    """
    base_url = "https://kyiv.energy-ua.info/grafik/%D0%9A%D0%B8%D1%97%D0%B2" # Київ
    
    # 1. Validation for complex building numbers (e.g., 1/11)
    # The site often fails to resolve building numbers with slashes
    building = str(row['building_number']).strip()
    if "/" in building:
        return None

    # 2. Map full street types to abbreviations
    type_map = {
        "вулиця": "вул.",
        "проспект": "просп.",
        "бульвар": "бул.",
        "провулок": "пров.",
        "площа": "пл.",
        "шосе": "шосе"
    }
    
    street_type = row['street_type'].lower().strip()
    short_type = type_map.get(street_type, street_type) # Fallback to original if not in map
    
    # 3. Construct the path segments
    # Format: "type. name" (e.g., "просп. Корольова Академіка")
    street_full_name = f"{short_type} {row['street_name']}"
    
    # 4. URL Encode segments
    # safe='' ensures spaces are converted to %20 or + depending on implementation
    # We'll use quote to match the % encoded style of your example
    encoded_street = urllib.parse.quote(street_full_name)
    encoded_building = urllib.parse.quote(building)
    
    return f"{base_url}/{encoded_street}/{encoded_building}"


def parse_electricity_html(html_content: str, address_id: int):
    soup = BeautifulSoup(html_content, 'html.parser')
    scale = soup.find("div", class_="scale_hours new_scale")
    
    if not scale:
        return None

    # Find all hour elements
    hour_elements = scale.find_all("div", class_=lambda x: x and "scale_hours_el" in x)
    
    # We expect 24 elements for 24 hours
    time_slots_48 = []
    
    for el in hour_elements:
        status_span = el.find("span", class_="hour_status")
        # Logic: If 'off' or 'blackout' is in the class, electricity is False.
        # In your snippet, the class is just "hour_status ", implying True.
        is_on = "off" not in status_span.get("class", [])
        
        # Convert 1 hour slot to two 30-min slots
        time_slots_48.extend([is_on, is_on])

    return {
        "address_id": address_id,
        "schedule_date": date.today(),
        "time_slots": time_slots_48,
        "raw_meta": json.dumps({"container_count": len(hour_elements)})
    }


@broker.task
@broker.task(
    schedule=[{
        "cron": "0 0 * * *", 
        "args": [], 
        "labels": {"source": "EnergyUA", "priority": "high"}
    }]
)
async def scrape_and_ingest_schedule():
    conn = await get_db_conn()
    
    # 1. Get Address details from DB
    rows = await conn.fetch("""
        SELECT address_id, street_type, street_name, building_number 
        FROM electricity.address LIMIT 10
    """)
    
    if not rows:
        await conn.close()
        return

    # Use a single client for the whole batch (performance boost)
    async with httpx.AsyncClient(timeout=10.0) as client:
        for row in rows:
            addr_id = row['address_id']
            
            # Generate URL for this specific row
            url = generate_electricity_url(dict(row))
            
            if not url:
                print(f" [!] Skipping invalid URL for ID: {addr_id}")
                continue

            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f" [!] HTTP {resp.status_code} for ID: {addr_id}")
                    continue

                # 3. Parse HTML
                parsed_data = parse_electricity_html(resp.text, addr_id)

                if parsed_data:
                    # 4. Upsert into Postgres
                    await conn.execute("""
                        INSERT INTO electricity.electricity_schedule 
                        (address_id, schedule_date, time_slots, raw_html_meta)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (address_id, schedule_date) 
                        DO UPDATE SET 
                            time_slots = EXCLUDED.time_slots,
                            raw_html_meta = EXCLUDED.raw_html_meta,
                            updated_at = CURRENT_TIMESTAMP;
                    """, 
                    parsed_data['address_id'], 
                    parsed_data['schedule_date'], 
                    parsed_data['time_slots'], 
                    parsed_data['raw_meta'])

                    print(f" [OK] Updated schedule for Address ID: {addr_id}")

            except Exception as e:
                print(f" [ER] Failed task for ID {addr_id}: {e}")
                # Don't return here; let the loop continue to the next address
    
    await conn.close()