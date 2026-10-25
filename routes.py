import sys
sys.stdout.reconfigure(encoding="utf-8")
import math
import os
import requests
import polyline
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"


def get_routes(origin, destination, emission_type="GASOLINE"):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        # Only ask Google for the fields we need (shape, tolls and traffic sections included)
        "X-Goog-FieldMask": (
            "routes.description,routes.distanceMeters,routes.duration,"
            "routes.staticDuration,routes.polyline.encodedPolyline,"
            "routes.travelAdvisory.tollInfo,"
            "routes.travelAdvisory.speedReadingIntervals"
        ),
    }
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "languageCode": "en-US",
        "extraComputations": ["TOLLS", "TRAFFIC_ON_POLYLINE"],
                "routeModifiers": {
            "vehicleInfo": {"emissionType": emission_type},
            "tollPasses": ["IN_FASTAG"],
        },
    }
    try:
        response = requests.post(URL, json=body, headers=headers, timeout=30)
    except requests.exceptions.RequestException:
        print("Network problem while fetching routes.")
        return []

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


def get_toll(route):
    # Returns (toll amount, whether the price is known)
    toll_info = route.get("travelAdvisory", {}).get("tollInfo")
    if toll_info is None:
        return 0.0, True  # no tolls on this route

    prices = toll_info.get("estimatedPrice", [])
    if not prices:
        return 0.0, False  # tolls exist, but Google doesn't know the price

    total = sum(int(p.get("units", 0)) + p.get("nanos", 0) / 1e9 for p in prices)
    return total, True


def distance_km(p1, p2):
    # Distance between two [lng, lat] points on Earth (haversine formula)
    lng1, lat1 = map(math.radians, p1)
    lng2, lat2 = map(math.radians, p2)
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def traffic_split(path, intervals, route_km):
    # Works out how many km of the route are smooth (green), slow (orange) or jammed (red)
    no_data = {"NORMAL": route_km, "SLOW": 0.0, "TRAFFIC_JAM": 0.0}
    if not intervals or len(path) < 2:
        return no_data

    segments = [distance_km(path[i], path[i + 1]) for i in range(len(path) - 1)]
    split = {"NORMAL": 0.0, "SLOW": 0.0, "TRAFFIC_JAM": 0.0}

    for interval in intervals:
        start = interval.get("startPolylinePointIndex", 0)
        end = interval.get("endPolylinePointIndex", len(path) - 1)
        speed = interval.get("speed", "NORMAL")
        if speed not in split:
            speed = "NORMAL"
        split[speed] += sum(segments[start:end])

    covered = sum(split.values())
    if covered == 0:
        return no_data

    # Scale so the three parts add up to Google's official route distance
    return {speed: km / covered * route_km for speed, km in split.items()}


def analyze_routes(routes):
    results = []
    for route in routes:
        with_traffic = to_minutes(route["duration"])
        without_traffic = to_minutes(route["staticDuration"])
        delay = max(with_traffic - without_traffic, 0)
        congestion = delay / without_traffic * 100 if without_traffic > 0 else 0
        route_km = route["distanceMeters"] / 1000

        # Decode the route shape into [longitude, latitude] points for the map
        encoded = route.get("polyline", {}).get("encodedPolyline", "")
        path = [[lng, lat] for lat, lng in polyline.decode(encoded)] if encoded else []

        intervals = route.get("travelAdvisory", {}).get("speedReadingIntervals", [])
        split = traffic_split(path, intervals, route_km)
        toll, toll_known = get_toll(route)

        results.append({
            "name": route.get("description", "unnamed road"),
            "km": route_km,
            "with_traffic": with_traffic,
            "delay": delay,
            "congestion": congestion,
            "label": congestion_label(congestion),
            "path": path,
            "toll": toll,
            "toll_known": toll_known,
            "smooth_km": split["NORMAL"],
            "slow_km": split["SLOW"],
            "jam_km": split["TRAFFIC_JAM"],
        })
    return results


def add_costs(results, smooth_mileage, slow_mileage, fuel_price):
    # Smooth km use the smooth mileage; slow and jammed km use the slow mileage
    for r in results:
        r["fuel_smooth"] = r["smooth_km"] / smooth_mileage * fuel_price
        r["fuel_slow"] = (r["slow_km"] + r["jam_km"]) / slow_mileage * fuel_price
        r["fuel_cost"] = r["fuel_smooth"] + r["fuel_slow"]
        r["total_cost"] = r["fuel_cost"] + r["toll"]
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


def find_badges(results):
    # Work out which route wins each category, and label the routes
    picks = {
        "⚡ Fastest": min(results, key=lambda r: r["with_traffic"]),
        "💰 Cheapest": min(results, key=lambda r: r["total_cost"]),
        "📏 Shortest": min(results, key=lambda r: r["km"]),
        "🌸 Calmest": rank_routes(results)[0],
    }
    for r in results:
        r["badges"] = [badge for badge, winner in picks.items() if winner is r]
    return picks


def suggest_places(text):
    # Called while the user types; returns a list of matching place names
    if not text or len(text) < 3:
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
    }
    body = {
        "input": text,
        "includedRegionCodes": ["in"],  # only suggest places in India
        "languageCode": "en",
    }
    try:
        response = requests.post(AUTOCOMPLETE_URL, json=body, headers=headers, timeout=10)
    except requests.exceptions.RequestException:
        return []

    if response.status_code != 200:
        print("Autocomplete error:", response.text)
        return []

    suggestions = response.json().get("suggestions", [])
    return [
        s["placePrediction"]["text"]["text"]
        for s in suggestions
        if "placePrediction" in s
    ]


if __name__ == "__main__":
    origin = "Andheri, Mumbai"
    destination = "Gateway of India, Mumbai"

    results = analyze_routes(get_routes(origin, destination))

    if not results:
        print("No routes found.")
    else:
        add_costs(results, smooth_mileage=18, slow_mileage=10, fuel_price=100)
        for r in rank_routes(results):
            print(f"via {r['name']}: {format_time(r['with_traffic'])}, {r['km']:.1f} km")
            print(f"  smooth {r['smooth_km']:.1f} km, slow {r['slow_km']:.1f} km, jammed {r['jam_km']:.1f} km")
            print(f"  fuel ₹{r['fuel_cost']:.0f} + tolls ₹{r['toll']:.0f} = ₹{r['total_cost']:.0f}")