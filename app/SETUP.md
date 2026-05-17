# CityActivities Data Pipeline Setup 🌆🏛️

This repository contains an automated urban monitoring system for Kyiv, integrating traffic data (TomTom), air raid alerts (UkraineAlarm), electricity schedules (Energy-UA), and city news (Telegram).

## 1. Environment & Database Setup

### Step A: Initialize the Database
The database schema is defined in `database_schema.sql`. You can set this up via pgAdmin 4 or the command line.

1. Create a new PostgreSQL database (e.g., `city_activities`).
2. Run the schema script:
   ```bash
   # Using psql
   psql -h localhost -U your_username -d city_activities -f database_schema.sql
   
# 🚀 Deployment & Task Execution Guide

This guide covers the initialization of data, authentication, and the execution of the asynchronous monitoring pipeline. Ensure your database schema is created via `database_schema.sql` before proceeding.

---

## 1. Data Initialization

Navigate to the `app` folder. We must populate the base addresses before starting the automated scrapers.

### Step A: Collect Official Addresses
This script fetches raw data from API resources and generates a local GeoJSON file.
```bash
python import_addresses.py
```

Step B: Populate the Database
Load the collected addresses into the PostgreSQL electricity.address table.

Bash
python populate_db_with_addresses.py

