import random

from main import broker
import asyncpg

import dotenv
import configparser

from datetime import datetime

from mocked_models import MockMLPackage 

dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("tg_conn.ini")

database_url = config["POSTGRES"]["DATABASE_URL"]

async def get_db_conn():
    return await asyncpg.connect(database_url)

@broker.task(
    schedule=[
    {"cron": "* * * * *", "args": ["tg"], "labels": {"source": "Telegram"}},
    {"cron": "* * * * *", "args": ["web"], "labels": {"source": "Web"}}
])
async def fetch_news_task(source_type: str):
    conn = await get_db_conn()
    
    # Mock Data
    mock_data = [
        {
            "s_id": "kyiv_alerts_mock",
            "type": source_type,
            "url": f"https://mock.com/{random.randint(1,99999)}" if source_type == "web" else "kyivnews",
            "title": "Ремонт дороги на Олени Теліги",
            "content": "Сьогодні проводяться планові роботи на дорозі...",
            "pub_date": "2026-04-23 10:00"
        }
    ]

    for item in mock_data:
        published_date = datetime.strptime(item["pub_date"], "%Y-%m-%d %H:%M")
        news_id = await conn.fetchval("""
            INSERT INTO raw.news (source_id, source_type, url, title, news_content, published_date)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (url) DO NOTHING RETURNING news_id;
        """, item['s_id'], item['type'], item['url'], item['title'], item['content'], published_date)
        print(f"news_id: {news_id}")
        if news_id:
            await enrich_news_task.kiq(news_id)
    await conn.close()


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
async def update_infrastructure_task():
    conn = await get_db_conn() 
    
    # Mock Traffic
    await conn.execute("""
        INSERT INTO alerts.traffic_incident (external_id, incident_type, geom, updated_at)
        VALUES ($1, $2, ST_GeomFromTEXT($3, 4326), NOW())
        ON CONFLICT (external_id) DO UPDATE SET updated_at = NOW();
    """, str(random.random()), 6, "LINESTRING(30.50 50.44, 30.51 50.45)")

    # Mock Air Raid
    await conn.execute("""
        INSERT INTO alerts.air_raid (is_active, activated_at) 
        VALUES ($1, NOW());
    """, random.choice([True, False]))
    
    await conn.close()


@broker.task(
        schedule=[
            {"cron": "* * * * *"}# {"cron":"1 0 * * *"}
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
