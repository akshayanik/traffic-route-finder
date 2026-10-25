import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import requests
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def get_routes(origin, destination):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        # Only ask Google for the fields we need
        "X-Goog-FieldMask": "routes.description,routes.distanceMeters,routes.duration,routes.staticDuration",
    }
    
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "languageCode": "en-US",
    }    
    
    response = requests.post(URL, json=body, headers=headers, timeout=30)

    if response.status_code != 200:
        print("Something went wrong:")
        print(response.text)
        return []

    return response.json().get("routes", [])


def to_minutes(duration):
    # Google sends times like "1534s", so remove the "s" and convert to minutes
    return int(duration.rstrip("s")) / 60


origin = "Andheri, Mumbai"
destination = "Gateway of India, Mumbai"

routes = get_routes(origin, destination)

for i, route in enumerate(routes, start=1):
    with_traffic = to_minutes(route["duration"])
    without_traffic = to_minutes(route["staticDuration"])
    delay = with_traffic - without_traffic
    km = route["distanceMeters"] / 1000

    print(f"Route {i}: via {route.get('description', 'unnamed road')}")
    print(f"  Distance: {km:.1f} km")
    print(f"  With traffic: {with_traffic:.0f} min | Without traffic: {without_traffic:.0f} min")
    print(f"  Traffic delay: {delay:.0f} min")
    print()