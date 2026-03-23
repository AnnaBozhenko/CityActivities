from flask import Flask, render_template_string

import folium
import osmnx as ox

import numpy as np

import requests
import json
import dotenv
import configparser

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

incident_colors = {
    '0': '#808080', '1': '#FFA500', '2': '#F8F8FF', '3': '#FF00FF',
    '4': '#4169E1', '5': '#00FFFF', '6': '#8B0000', '7': '#FF7F50',
    '8': '#FF0000', '9': '#FFFF00', '10': '#90EE90', '11': '#00008B', 
    '14': '#A52A2A'
}

app = Flask(__name__)

def get_response(request):
    try:
        response = requests.get(request)
        return json.loads(response.content)
    except:
        ...
    return response


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
                 "FFS": traffic_flow['flowSegmentData']['freeFlowSpeed']
            }
        
            return road_segment, flow_data
    except:
        ...

    

@app.route("/flow_speed")
def render_flow_speed():
    kyiv_road_network = ox.graph.graph_from_place("Kyiv, Ukraine", network_type="drive", simplify=True)
    nodes, edges = ox.graph_to_gdfs(kyiv_road_network)
    points = [row['geometry'].centroid for i, row in edges.iterrows()]
    coords = [(point.x, point.y) for point in points]
    indices = np.random.choice(range(len(coords)), size=10)
    flow_speeds = [get_flow_speed(lon_p=coords[i][0], lat_p=coords[i][1]) for i in indices]

    flow_speeds = [flow_speed for flow_speed in flow_speeds if flow_speed is not None]

    m = folium.Map(zoom_start=11) 
    [folium.PolyLine(
            road_segment, 
            tooltip=f"CFS: {flow_data['CFS']}, FFS: {flow_data['FFS']}"
        ).add_to(m)
    for road_segment, flow_data in flow_speeds]

    m.get_root().render()
    header = m.get_root().header.render()
    body_html = m.get_root().html.render()
    script = m.get_root().script.render()

    return render_template_string(
        """
            <!DOCTYPE html>
            <html>
                <head>
                    {{ header|safe }}
                </head>
                <body>
                    <h1>Using components</h1>
                    {{ body_html|safe }}
                    <script>
                        {{ script|safe }}
                    </script>
                </body>
            </html>
        """,
        header=header,
        body_html=body_html,
        script=script,
    )


@app.route("/incidents")
def render_incidents():
    minLon,minLat,maxLon,maxLat = 30.4698481, 50.469297, 30.5213651, 50.489209 # Kyiv bbox
    incidents_data = get_incidents(minLon,minLat,maxLon,maxLat)

    m = folium.Map(zoom_start=11)   
    if incidents_data is not None:
        [
            folium.PolyLine(
                coords, 
                tooltip=incidents_types[incident_id], 
                color=incident_colors[incident_id]).add_to(m)
            for incident_id, coords in incidents_data
        ]
    m.get_root().render()
    header = m.get_root().header.render()
    body_html = m.get_root().html.render()
    script = m.get_root().script.render()

    return render_template_string(
        """
            <!DOCTYPE html>
            <html>
                <head>
                    {{ header|safe }}
                </head>
                <body>
                    <h1>Using components</h1>
                    {{ body_html|safe }}
                    <script>
                        {{ script|safe }}
                    </script>
                </body>
            </html>
        """,
        header=header,
        body_html=body_html,
        script=script,
    )

if __name__ == "__main__":
    app.run(debug=True)
