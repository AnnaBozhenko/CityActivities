import os
from pathlib import Path

import osmnx as ox

import numpy as np

import requests

import json

import dotenv
import configparser
import argparse

from datetime import datetime

dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("app/tg_conn.ini")

tomtom_key=config["TOMTOM"]["api_key"]
incidents_types = {'0': 'Unknown',
 '1': 'Accident',
 '2': 'Fog',
 '3': 'Dangerous Conditions',
 '4': 'Rain',
 '5': 'Ice',
 '6': 'Jam',
 '7': 'Lane Closed',
 '8': 'Road Closed',
 '9': 'Road Works',
 '10': 'Wind',
 '11': 'Flooding',
 '14': 'Broken Down Vehicle'}

def check_file_exists(fp_save_to):
    "creates recursively parent directory of endpoint file, if not existing"
    if not os.path.exists(fp_save_to):
        parent_path = Path(fp_save_to).parent
        if parent_path != ".":
            os.makedirs(parent_path, exist_ok=True)


def get_response(request):
    try:
        response = requests.get(request)
        return json.loads(response.content)
    except:
        ...


def get_incidents(minLon,minLat,maxLon,maxLat):
    try:
        incidents_request = f"https://api.tomtom.com/traffic/services/5/incidentDetails?key={tomtom_key}&bbox={minLon},{minLat},{maxLon},{maxLat}" + "&fields={incidents{type,geometry{type,coordinates},properties{iconCategory}}}&language=en-GB&t=1111&timeValidityFilter=present"
        incidents_data = get_response(incidents_request)
        if incidents_data is not None:    
            incidents_data = [
                (
                    str(inc['properties']['iconCategory']), 
                    [(lat, lon) for lon, lat in inc['geometry']['coordinates']]
                ) 
                for inc in incidents_data['incidents']
            ]

            
        return incidents_data
    except:
        ...


def get_flow_speed(lat_p,lon_p):
    try:
        request = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?key={tomtom_key}&point={lat_p},{lon_p}&unit=kmph"
        traffic_flow = get_response(request)
        if traffic_flow is not None:
            print("response is non-zero")
            road_segment = [(coords['latitude'], coords['longitude']) for coords in traffic_flow['flowSegmentData']['coordinates']['coordinate']]
            
            flow_data = {
                "CFS": traffic_flow['flowSegmentData']['currentSpeed'],
                "FFS": traffic_flow['flowSegmentData']['freeFlowSpeed'],
                "road_segment": road_segment,
            }
        
            return flow_data
    except:
        ...

    

def load_flow_speed(filepath: str) -> list[dict]:
    """returns [
        {
            "CFS": int # currentSpeed (km/hour)
            "FFS": int # freeFlowSpeed (km/hour)
            "road_segment": [(float, float)] # (latitude, longitude)
        }
    ]"""
    kyiv_road_network = ox.graph.graph_from_place("Kyiv, Ukraine", network_type="drive", simplify=True)
    nodes, edges = ox.graph_to_gdfs(kyiv_road_network)
    points = [row['geometry'].centroid for i, row in edges.iterrows()]
    coords = [(point.y, point.x) for point in points]
    indices = np.random.choice(range(len(coords)), size=10)
    flow_speeds = [get_flow_speed(lat_p=coords[i][0], lon_p=coords[i][1]) for i in indices]

    flow_speeds = [flow_speed for flow_speed in flow_speeds if flow_speed is not None]
    check_file_exists(filepath)
    with open(filepath, mode="w") as f:
        json.dump(flow_speeds, f)
    return flow_speeds


def load_incidents(filepath: str) -> list[dict]:
    """returns [
        {
            'incident_type': str # from set `incidents_types` (see definition above)
            'coordinates': [(float, float)] # (latitude, longitude)
        }
    ] from bounding box of Kyiv (lower-left, upper-right)"""
    minLon,minLat,maxLon,maxLat = 30.4698481, 50.469297, 30.5213651, 50.489209 
    incidents_data = get_incidents(minLon,minLat,maxLon,maxLat)
    incidents_data = [] if incidents_data is None else incidents_data
    if len(incidents_data) > 0:
        incidents_data = [
            {"incident_type": incidents_types[incident_id], "coordinates": coords}
            for incident_id, coords in incidents_data
        ]

    check_file_exists(filepath)
    with open(filepath, mode="w") as f:
        json.dump(incidents_data, f)
    return incidents_data

    

if __name__ == "__main__":
    argparser = argparse.ArgumentParser("get_traffic")
    argparser.add_argument("-f", dest="flow_speed", action='store_true')
    argparser.add_argument("-i", dest="incidents", action='store_true') 
    current_timestamp = datetime.now().strftime(format="%Y-%m-%d_%H-%M")
    if argparser.parse_args().flow_speed:
        load_flow_speed(f"flowspeed_{current_timestamp}.json")
    if argparser.parse_args().incidents:
        load_incidents(f"incidents_{current_timestamp}.json")

