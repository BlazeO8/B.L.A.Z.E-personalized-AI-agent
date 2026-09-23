"""
B.L.A.Z.E — Google Maps / Places API Integration
Real directions, distance, ETA, nearby places.
Free tier: $200/month credit, covers normal personal use.
"""

import webbrowser
from blaze.deps import requests, requests_available
from blaze.core.logging_audit import log


class MapsManager:
    def _api_key(self):
        from blaze.config import GOOGLE_API_KEY
        return GOOGLE_API_KEY

    def get_directions(self, origin: str, destination: str, mode: str = "driving") -> str:
        key = self._api_key()
        if not key or not requests_available:
            url = f"https://www.google.com/maps/dir/{origin.replace(' ','+')}/{destination.replace(' ','+')}"
            webbrowser.open(url)
            return f"Opening directions from {origin} to {destination}, sir."

        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={"origin": origin, "destination": destination, "mode": mode, "key": key},
                timeout=10
            )
            data = resp.json()
            if data.get("status") != "OK" or not data.get("routes"):
                url = f"https://www.google.com/maps/dir/{origin.replace(' ','+')}/{destination.replace(' ','+')}"
                webbrowser.open(url)
                return f"Could not fetch route details, opening Maps instead, sir."

            leg      = data["routes"][0]["legs"][0]
            distance = leg["distance"]["text"]
            duration = leg["duration"]["text"]

            url = f"https://www.google.com/maps/dir/{origin.replace(' ','+')}/{destination.replace(' ','+')}"
            webbrowser.open(url)

            return (f"From {origin} to {destination}: {distance}, about {duration} by {mode}, "
                    f"sir. Opening the route in Maps.")

        except Exception as e:
            log.warning(f"Maps directions error: {e}")
            url = f"https://www.google.com/maps/dir/{origin.replace(' ','+')}/{destination.replace(' ','+')}"
            webbrowser.open(url)
            return f"Opened directions in Maps, sir."

    def find_nearby(self, query: str, location: str = "") -> str:
        key = self._api_key()
        search_url = f"https://www.google.com/maps/search/{query.replace(' ','+')}"
        if location:
            search_url += f"+near+{location.replace(' ','+')}"

        if not key or not requests_available:
            webbrowser.open(search_url)
            return f"Searching for {query} nearby, sir."

        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": f"{query} near {location}" if location else query, "key": key},
                timeout=10
            )
            data    = resp.json()
            results = data.get("results", [])[:5]
            if not results:
                webbrowser.open(search_url)
                return f"No results found, opening Maps for '{query}', sir."

            lines = []
            for r in results:
                name    = r.get("name", "Unknown")
                addr    = r.get("formatted_address", "")
                rating  = r.get("rating", "N/A")
                lines.append(f"• {name} ({rating}★) — {addr}")

            webbrowser.open(search_url)
            return f"Found these nearby, sir:\n" + "\n".join(lines)

        except Exception as e:
            log.warning(f"Maps nearby error: {e}")
            webbrowser.open(search_url)
            return f"Opened Maps search for '{query}', sir."


maps_manager = MapsManager()
