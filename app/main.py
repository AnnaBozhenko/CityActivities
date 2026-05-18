from taskiq_redis import ListQueueBroker
import json
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncpg
import configparser

broker = ListQueueBroker("redis://localhost:6379")

config = configparser.ConfigParser()
config.read("tg_conn.ini")
database_url = config["POSTGRES"]["DATABASE_URL"]
app = FastAPI(title="Kyiv City Activities API")

async def get_db_pool():
    return await asyncpg.create_pool(database_url)

@app.on_event("startup")
async def startup():
    app.state.db_pool = await get_db_pool()

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

@app.get("/api/events")
async def get_all_events():
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                event_id, event_type, confidence, 
                start_time, end_time, status, is_planned,
                extracted_addresses,
                ST_AsGeoJSON(geom) as geojson
            FROM enriched.city_event
            WHERE geom IS NOT NULL;
        """)
        
        markers = []
        
        category_map = {
            "ДТП": "accident",
            "відключення світла": "blackout",
            "ремонти": "repair",
            "ярмарок": "fair",
            "культурні події": "exhibition",
            "виставка": "exhibition",
            "перекриття": "closed"
        }

        for row in rows:
            geo = json.loads(row['geojson']) if row['geojson'] else None
            if not geo:
                continue
                
            event_type_raw = row['event_type']
            category = category_map.get(event_type_raw, "default")
            
            title = f"{event_type_raw.capitalize()}"
            addresses_list = row['extracted_addresses']
            address_str = ", ".join(addresses_list) if addresses_list else "Київ"
            description = f"<b>Адреса:</b> {address_str}<br><b>ML Вірогідність:</b> {(row['confidence']*100):.1f}%"
            
            start_date = row['start_time'].date().isoformat() if row['start_time'] else None
            end_date = row['end_time'].date().isoformat() if row['end_time'] else None

            # 📍 ОБРОБКА MULTIPOINT ТА POINT
            # Формуємо список координат у форматі Leaflet: [[lat, lng], [lat, lng]]
            if geo['type'] == 'MultiPoint':
                coords = [[pt[1], pt[0]] for pt in geo['coordinates']]
            elif geo['type'] == 'Point':
                coords = [[geo['coordinates'][1], geo['coordinates'][0]]]
            else:
                continue # Ігноруємо інші типи геометрії

            msg_type = "event" if category in ["fair", "exhibition"] else "incident"

            markers.append({
                "id": str(row['event_id']),
                "coords": coords, # 👈 Тепер тут завжди МАСИВ точок
                "type": msg_type,
                "category": category,
                "title": title,
                "description": description,
                "image": None,
                "date": None,
                "startDate": start_date,
                "endDate": end_date
            })
                    
        return {"markers": markers}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")