import random
from datetime import datetime, timedelta
from shapely.geometry import Point, LineString, Polygon, mapping
import json

class MockMLPackage:
    @staticmethod
    def classify_event(title: str, content: str) -> str:
        types = [
            'Транспортні інциденти', 
            'Планові/аварійні ремонти', 
            'Відключення інфраструктури', 
            'Погодні негаразди', 
            'Культурні події', 
            'Шум'
        ]
        return random.choice(types)

    @staticmethod
    def extract_times(published_date_str: str, title: str, content: str):
        start = datetime.now()
        end = start + timedelta(hours=1)
        return start, end

    @staticmethod
    def extract_and_geocode(text: str):
        # Mocking address extraction and 3rd party geocoding
        # In reality, this would hit Google Maps/Photon/Nominatim
        mock_points = [
            Point([30.5234, 50.4501]), # Kyiv Center
            LineString([[30.45, 50.45], [30.46, 50.46]]), # Mock road event
            Polygon([[30.4, 50.4], [30.5, 50.4], [30.5, 50.5], [30.4, 50.5], [30.4, 50.4]])
        ]
        return random.choice(mock_points).wkb_hex
    
    