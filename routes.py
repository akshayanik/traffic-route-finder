import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import requests
import polyline
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def get_routes(origin, destination):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        # Only ask Google for the fields we need (now including the route shape)
        "X-Goog-FieldMask": (
            "routes.description,routes.distanceMeters,routes.duration,"
            "routes.staticDuration,routes.polyline.encodedPolyline"
        ),
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


def congestion_label(percent):
    if percent < 10:
        return "Clear"
    elif percent < 30:
        return "Moderate"
    else:
        return "Heavy"


def analyze_routes(routes):
    results = []
    for route in routes:
        with_traffic = to_minutes(route["duration"])
        without_traffic = to_minutes(route["staticDuration"])
        delay = max(with_traffic - without_traffic, 0)
        congestion = delay / without_traffic * 100 if without_traffic > 0 else 0

        # Decode the route shape into [longitude, latitude] points for the map
        encoded = route.get("polyline", {}).get("encodedPolyline", "")
        path = [[lng, lat] for lat, lng in polyline.decode(encoded)] if encoded else []

        results.append({
            "name": route.get("description", "unnamed road"),
            "km": route["distanceMeters"] / 1000,
            "with_traffic": with_traffic,
            "delay": delay,
            "congestion": congestion,
            "label": congestion_label(congestion),
            "path": path,
        })
    return results


def format_time(minutes):
    # Turns 883 into "14 h 43 min"
    total = round(minutes)
    hours, mins = divmod(total, 60)
    if hours == 0:
        return f"{mins} min"
    return f"{hours} h {mins} min"


def rank_routes(results):
    # Least time stuck in traffic first; if tied, the faster route wins
    return sorted(results, key=lambda r: (round(r["delay"]), r["with_traffic"]))


if __name__ == "__main__":
    origin = "Andheri, Mumbai"
    destination = "Gateway of India, Mumbai"

    results = analyze_routes(get_routes(origin, destination))

    if not results:
        print("No routes found.")
    else:
        ranked = rank_routes(results)

        print("Routes ranked by least traffic:\n")
        for rank, r in enumerate(ranked, start=1):
            print(f"{rank}. via {r['name']} ({r['km']:.1f} km)")
            print(f"   {format_time(r['with_traffic'])} right now, {format_time(r['delay'])} of that is traffic")
            print(f"   Congestion: {r['congestion']:.0f}% ({r['label']})")
            print()