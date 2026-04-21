## Overview:

[editable doc](https://docs.google.com/document/d/1r3bIRMeBPs8Jm1lrlEx-ZI1e_5dGhoxPRLpVEB6xL6s/edit?tab=t.0#heading=h.srysdeav6dt7)


# To load Telegram channel's posts:
* navigate to `app` dir
* add `tg_conn.ini` with filled:
```\
[TELEGRAM]
app_id=...
app_hash=...
``` 
*Sign in to Telegram developer account. [Mannual's](https://docs.telethon.dev/en/stable/basic/signing-in.html)
`Sign in` section may be helpful 
* flags to run `python telegram_scraper.py`:
    * `-u` - channel's username(s), e.g: `-u kyivmas dtek_ua`, str, required
    * `-y` - year of requested date, *int* **required**
    * `-m` - month of requested date, *int* **required**
    * `-d` - day's number of requested date, *int* **required**
    * `-l` - limit number of messages per eveery requested channel, *int*

Example to run request for `bbcukrainian` channel, 2026 yer, 2 month, 20 day, 2: 

```
python telegram_scraper.py -u -y 2026 -m 2 -d 20
```

# Traffic data

Prerequisites
* navigate to `app` dir
* add TomTom's API-key to `tg_conn.ini`:
```
[TOMTOM]
api_key=
```

## 1. Traffic Incidents
Fetches real-time traffic incidents within the Kyiv bounding box.

### Data Structure:
The results are saved to `incidents_YYYY-MM-DD_HH-mm.json` in the following format:
```
[
    {
        'incident_type': str # from set `incidents_types` (see definition above)
        'coordinates': [(float, float)] # (latitude, longitude)
    }
]
```

### Incident Type Reference: 
* '0': 'Unknown',
* '1': 'Accident',
* '2': 'Fog',
* '3': 'Dangerous Conditions',
* '4': 'Rain',
* '5': 'Ice',
* '6': 'Jam',
* '7': 'Lane Closed',
* '8': 'Road Closed',
* '9': 'Road Works',
* '10': 'Wind',
* '11': 'Flooding',
* '14': 'Broken Down Vehicle'

### Run command:
```
python get_traffic.py -i
```

## 2. Traffic Flow Speed

### Data Structure:
The results are saved to flowspeed_YYYY-MM-DD_HH-mm.json in the following format: 
```
[
    {
        "CFS": int # currentSpeed (km/hour)
        "FFS": int # freeFlowSpeed (km/hour)
        "road_segment": [(float, float)] # (latitude, longitude)
    }
]
```

* This process utilizes osmnx to generate a directed driving graph of Kyiv

### Run command:
```
python get_traffic.py -f
```

### To get the current air raid state
Use the `get_alert_state()` function from `app/get_air_raid_state.py`

* add `tg_conn.ini` with filled:
```
[UKRAINEALARM]
api_token=
```

**Returns:**
* `True`: If there is an active air raid alert in Kyiv.
* `False`: If the airspace is currently clear.

**Example usage:**
```
region_name = 'м. Київ'
regions = {
            'states': [
                {
                    'regionId': '31',
                    'regionName': 'м. Київ',
                    'regionType': 'State',
                    'regionChildIds': []}
             ]
        }

city_id = get_region_id(region_name, regions["states"])
is_air_raid = get_alert_state(city_id)
```









