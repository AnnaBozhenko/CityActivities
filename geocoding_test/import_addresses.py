import requests
import json
import time

url = "https://gisserver-stage.kyivcity.gov.ua/mayno/rest/services/KYIV_API/%D0%90%D0%B4%D1%80%D0%B5%D1%81%D0%B8/MapServer/0/query"

all_features = []
offset = 0
limit = 1000

while True:
    params = {
        'where': '1=1',             # Вибрати всі записи
        'outFields': '*',           # Всі атрибути (вулиця, номер тощо)
        'resultOffset': offset,     # Зсув для пагінації
        'resultRecordCount': limit, # Кількість за один запит
        'f': 'geojson',             # Формат виводу
        'returnGeometry': 'true',   # Координати точок
        'outSR': '4326'             # Стандартні координати (WGS84)
    }

    try:
        response = requests.get(url, params=params, timeout=30, verify=True)

        if response.status_code != 200:
            print(f"Помилка доступу: {response.status_code}")
            break

        data = response.json()

        if "error" in data:
            print(f"Помилка API: {data['error'].get('message')}")
            break

        features = data.get('features', [])
        if not features:
            break

        all_features.extend(features)
        print(f"Завантажено {len(all_features)} адрес", end='\r')

        offset += len(features)
        time.sleep(0.2)

    except Exception as e:
        print(f"\nСталася помилка: {e}")
        break

if all_features:
    with open("kyiv_official_addresses.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f, ensure_ascii=False)
    print(f"\nУспішно збережено {len(all_features)} адрес у файл kyiv_official_addresses.geojson")
