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

        results.append({
            "name": route.get("description", "unnamed road"),
            "km": route["distanceMeters"] / 1000,
            "with_traffic": with_traffic,
            "delay": delay,
            "congestion": congestion,
            "label": congestion_label(congestion),
        })
    return results


origin = "Andheri, Mumbai"
destination = "Gateway of India, Mumbai"

results = analyze_routes(get_routes(origin, destination))

if not results:
    print("No routes found.")
else:
    ranked = sorted(results, key=lambda r: r["congestion"])

    print("Routes ranked by least traffic:\n")
    for rank, r in enumerate(ranked, start=1):
        print(f"{rank}. via {r['name']} ({r['km']:.1f} km)")
        print(f"   {r['with_traffic']:.0f} min right now, {r['delay']:.0f} min of that is traffic")
        print(f"   Congestion: {r['congestion']:.0f}% ({r['label']})")
        print()

    fastest = min(results, key=lambda r: r["with_traffic"])
    calmest = ranked[0]

    print(f"Fastest route: via {fastest['name']} ({fastest['with_traffic']:.0f} min)")
    print(f"Calmest route: via {calmest['name']} ({calmest['congestion']:.0f}% congestion)")

    if calmest is not fastest:
        extra = calmest["with_traffic"] - fastest["with_traffic"]
        print(f"Taking the calmest route costs you about {extra:.0f} extra minutes.")