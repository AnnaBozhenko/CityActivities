import requests

import dotenv
import configparser

import json

dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("tg_conn.ini")

ukraine_alarm_token=config["UKRAINEALARM"]["api_token"]
ukrainealarm_api_base_url = "https://api.ukrainealarm.com"


def get_region_id(region_name: str, states: list) -> str | None:
    if len(states) > 0:
        if states[0]["regionName"] == region_name:
            return states[0]["regionId"]
        found_child_region_id = get_region_id(region_name, states[0].get("regionChildIds", []))
        if found_child_region_id is not None:
            return found_child_region_id
        else:
            return get_region_id(region_name, states[1:])
    else:
        return None
        

def get_city_alarm_state(city_id: str) -> dict | None:
    try:
        response = requests.request(
            url=f"{ukrainealarm_api_base_url}/api/v3/alerts/{city_id}", 
            method="GET", 
            headers={"Authorization": ukraine_alarm_token}
        )
        alarms_info = json.loads(response.content)
        return alarms_info[0]
    except:
        return None
    

def get_alert(alerts_info: dict, city_id: str) -> dict | None:
    """alerts_info: region alerts"""
    if alerts_info is not None:
        alerts = alerts_info.get('activeAlerts', [])
        if len(alerts) > 0:
            alert = [alert for alert in alerts if alert['regionId'] == city_id]
            return alert[0]
    return None


def get_alert_state(city_id: str) -> bool:
    """Returns True if there is is air raid in the region.
    """
    alerts_info = get_city_alarm_state(city_id)
    alert = get_alert(alerts_info, city_id)
    return alert is not None


if __name__ == "__main__":
    region_name = 'м. Київ'

    try:
        response = requests.request(
            url=f"{ukrainealarm_api_base_url}/api/v3/regions", 
            method="GET", 
            headers={"Authorization": ukraine_alarm_token}
        )
        regions = json.loads(response.content)
        # save
        # with open("data/regions.json", "w") as f:
        #     json.dump(regions, f)
    except:
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
    is_air_raid = get_alert_state(city_id) # True - є тривога
    print(is_air_raid)