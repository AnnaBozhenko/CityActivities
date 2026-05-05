CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA raw; -- For initial scraper output
CREATE SCHEMA enriched; -- For ML-processed news with geolocations
CREATE SCHEMA alerts;   -- For Air Raid and Traffic status
CREATE SCHEMA electricity; -- For electricity state across Kyiv addresses

CREATE TABLE raw.news (
    news_id SERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,         -- <tg_channel_username> or <base_url>
    source_type TEXT NOT NULL,       -- 'tg' or 'web'
    url TEXT UNIQUE,                 -- url to post, following <base_url>
    title TEXT,
    news_content TEXT NOT NULL,
    published_date TIMESTAMP WITH TIME ZONE,         
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE enriched.city_event (
    event_id SERIAL PRIMARY KEY,
    news_id INTEGER REFERENCES raw.news(news_id) ON DELETE CASCADE,
    event_tag TEXT,                  -- ML predicted (e.g., 'concert', 'repair')
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    -- PostGIS Geometry column (supports Point, Line, or Polygon)
    geom GEOMETRY(Geometry, 4326), 
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for map performance
CREATE INDEX idx_events_geom ON enriched.city_event USING GIST (geom);

CREATE TABLE alerts.traffic_incident (
    traffic_incident_id SERIAL PRIMARY KEY,
    external_id TEXT UNIQUE,         -- TomTom's unique ID
    incident_type INTEGER,           -- 1: Accident, 6: Jam, etc.
    geom GEOMETRY(Geometry, 4326),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_traffic_geom ON alerts.traffic_incident USING GIST (geom);

CREATE TABLE alerts.air_raid (
    air_raid_id SERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL,
    region TEXT DEFAULT 'Kyiv',
    activated_at TIMESTAMP WITH TIME ZONE,
    deactivated_at TIMESTAMP WITH TIME ZONE
);

-- Table for Official City Addresses
CREATE TABLE electricity.address (
    address_id SERIAL PRIMARY KEY,
    globalid UUID UNIQUE,           -- From the official GeoJSON 'globalid'
    district TEXT,                  -- 'district1'
    street_type TEXT,               -- 'type_vul'
    street_name TEXT,               -- 'ukrnamef'
    building_number TEXT,           -- 'addrnumb1'
    full_address TEXT,              -- 'full_addr'
    geom GEOMETRY(Point, 4326),     -- Coordinates from GeoJSON
    last_scraped_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_addresses_geom ON electricity.address USING GIST (geom);
CREATE INDEX idx_addresses_lookup ON electricity.address (street_name, building_number);

-- Table for Electricity Schedules (The "Status Log")
CREATE TABLE electricity.electricity_schedule (
    schedule_id SERIAL PRIMARY KEY,
    address_id INTEGER REFERENCES electricity.address(address_id) ON DELETE CASCADE,
    schedule_date DATE NOT NULL,
    -- Using an 'interval' approach or a 'bitmask' is possible, 
    -- but for half-hour granularity, a JSONB array or 48 binary slots is safest.
    time_slots BOOLEAN[] NOT NULL,       -- Array of 48 booleans (every 30 mins)
    raw_html_meta JSONB,            -- To store version of the page layout for debugging
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	UNIQUE(address_id, schedule_date)
);
