import random

import os

from main import broker
import asyncpg

import dotenv
import configparser

from datetime import datetime, date

from mocked_models import MockMLPackage 

from telethon import TelegramClient

import httpx
from bs4 import BeautifulSoup
import json
import urllib.parse

from shapely.geometry import LineString, Point

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

async def get_db_conn():
    return await asyncpg.connect(database_url)


def get_tg_client():
    global tg_client
    if tg_client is None:
        tg_client = TelegramClient('anon', TELEGRAM_API_ID, TELEGRAM_API_HASH)
    return tg_client

@broker.on_event("startup")
async def startup():
    tg_client = get_tg_client()
    await tg_client.connect()

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
                    title, *content = message.text.split("\n")
                    content = " ".join(content)
                    # Standardize data to match your DB schema
                    all_posts.append({
                        "s_id": str(message.peer_id.channel_id),
                        "type": "tg",
                        "url": post_url,
                        "title": title, # Telegram doesn't have titles, so we use a snippet
                        "content": content,
                        "pub_date": message.date # Telethon returns timezone-aware datetime
                    })
            except Exception as e:
                print(f"Error scraping {channel_name}: {e}")
        
        # Now use your existing insertion logic
        for item in all_posts:
            news_id = await conn.fetchval("""
                INSERT INTO raw.news (source_id, source_type, url, title, news_content, published_date)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (url) DO NOTHING RETURNING news_id;
            """, item['s_id'], item['type'], item['url'], item['title'], item['content'], item['pub_date'])
            
            if news_id:
                print(f" [TG] New post ingested: {news_id}")
                await enrich_news_task.kiq(news_id)

    elif source_type == "web":
        # ... (Your Web Scraping Logic here) ...
        pass

    await conn.close()


# @broker.task(
#     schedule=[
#     {"cron": "* * * * *", "args": ["tg"], "labels": {"source": "Telegram"}},
#     {"cron": "* * * * *", "args": ["web"], "labels": {"source": "Web"}}
# ])
# async def fetch_news_task(source_type: str):
#     conn = await get_db_conn()
    
#     # Mock Data
#     mock_data = [
#         {
#             "s_id": "kyiv_alerts_mock",
#             "type": source_type,
#             "url": f"https://mock.com/{random.randint(1,99999)}" if source_type == "web" else "kyivnews",
#             "title": "Ремонт дороги на Олени Теліги",
#             "content": "Сьогодні проводяться планові роботи на дорозі...",
#             "pub_date": "2026-04-23 10:00"
#         }
#     ]

#     for item in mock_data:
#         published_date = datetime.strptime(item["pub_date"], "%Y-%m-%d %H:%M")
#         news_id = await conn.fetchval("""
#             INSERT INTO raw.news (source_id, source_type, url, title, news_content, published_date)
#             VALUES ($1, $2, $3, $4, $5, $6)
#             ON CONFLICT (url) DO NOTHING RETURNING news_id;
#         """, item['s_id'], item['type'], item['url'], item['title'], item['content'], published_date)
#         print(f"news_id: {news_id}")
#         if news_id:
#             await enrich_news_task.kiq(news_id)
#     await conn.close()


@broker.task
async def enrich_news_task(news_id: int):
    print(f" [!] Starting enrichment for News ID: {news_id}")
    conn = await get_db_conn()
    try:
        row = await conn.fetchrow("SELECT title, news_content, published_date FROM raw.news WHERE news_id = $1", news_id)

        if not row:
            print(f" [X] Error: News ID {news_id} not found in DB")
            return

        # Run Mock ML
        tag = MockMLPackage.classify_event(row['title'], row['news_content'])
        start, end = MockMLPackage.extract_times(row['published_date'], row['title'], row['news_content'])
        wkt_hex_data = MockMLPackage.extract_and_geocode(row['title'] + '. ' + row['news_content'])
        binary_geom = bytes.fromhex(wkt_hex_data)

        print(f" [>] ML Results - Tag: {tag}, Geocode: {wkt_hex_data[:10]}...")

        await conn.execute("""
            INSERT INTO enriched.city_event (news_id, event_tag, start_time, end_time, geom)
            VALUES ($1, $2, $3, $4, ST_GeomFromWKB($5, 4326));
        """, news_id, tag, start, end, binary_geom)

        print(f" [OK] Successfully enriched News ID: {news_id}")
    except Exception as e:
        print(f" [ER] Enrichment failed: {e}")
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