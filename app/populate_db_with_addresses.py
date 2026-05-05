import json
import asyncio
import asyncpg
from shapely.geometry import shape

import shapely.wkb

import dotenv
import configparser

dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("tg_conn.ini")

DB_CONFIG = {
    "user": config["POSTGRES"]["USER"],
    "password": config["POSTGRES"]["PASSWORD"],
    "database": config["POSTGRES"]["DATABASE"],
    "host": "localhost"
}

GEOJSON_FILE = "data/kyiv_official_addresses.geojson"

async def set_up_postgis_type(conn):
    """Register PostGIS geometry type with asyncpg."""
    def encode_geometry(geometry_wkb):
        # If you're passing raw bytes from Shapely's .wkb, return them directly
        # If you're passing a Shapely object, return its .wkb
        return geometry_wkb

    def decode_geometry(wkb):
        return shapely.wkb.loads(wkb)

    await conn.set_type_codec(
        'geometry',
        encoder=encode_geometry,
        decoder=decode_geometry,
        format='binary',
    )

async def ingest_addresses():
    print(f"Reading {GEOJSON_FILE}...")
    with open(GEOJSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    print(f"Found {len(features)} addresses. Preparing data for PostGIS...")

    # Prepare data for bulk copy
    # Format: (globalid, district, street_type, street_name, building_number, full_address, WKB_geom)
    records = []
    for feat in features:
        props = feat.get('properties', {})
        geom = feat.get('geometry')
        
        if not geom or not props:
            continue

        # Convert GeoJSON geometry to Well-Known Binary (WKB) for PostGIS
        # Shapely is perfect for this conversion
        try:
            wkb_geom = shape(geom).wkb
        except Exception:
            continue

        uuid = props.get('globalid')
        uuid = uuid.strip("{}") if uuid else None
        # We use .get() to avoid KeyErrors if some fields are missing in certain features
        records.append((
            uuid,
            props.get('district1'),
            props.get('type_vul'),
            props.get('ukrnamef'),
            props.get('addrnumb1'),
            props.get('full_addr'),
            wkb_geom  # PostGIS can ingest binary directly
        ))

    # Connect and Execute Bulk Copy
    conn = await asyncpg.connect(**DB_CONFIG)
    await set_up_postgis_type(conn)

    try:
        print("Starting bulk ingestion into electricity.address...")
        
        # Using a transaction to ensure integrity
        async with conn.transaction():
            # 1. Clear existing data if you want a fresh start (Optional)
            # await conn.execute("TRUNCATE electricity.address CASCADE;")

            # 2. Use copy_records_to_table for maximum speed
            # Note: We skip address_id as it is SERIAL and handled by PG
            await conn.copy_records_to_table(
                'address',
                schema_name='electricity',
                columns=[
                    'globalid', 'district', 'street_type', 'street_name', 
                    'building_number', 'full_address', 'geom'
                ],
                records=records
            )

        print(f"Success! Ingested {len(records)} addresses.")
        
        await conn.execute("ANALYZE electricity.address;")

    except Exception as e:
        print(f"Error during ingestion: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(ingest_addresses())