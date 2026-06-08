"""
B.L.A.Z.E — Service Integrations (Feature 2)
External API / web integrations: GitHub, Spotify, Google Drive,
Trello, Slack, Notion, currency, dictionary, Wikipedia, IP info.
"""

import webbrowser

from blaze.deps import requests, requests_available
from blaze.core.logging_audit import log


class ServiceIntegrations:
    """Each method tries the API and gracefully falls back if the key isn't set."""

    # ── GitHub ────────────────────────────────────────────────────────────────
    def github_repos(self, username: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                f"https://api.github.com/users/{username}/repos?sort=updated&per_page=5",
                timeout=5
            )
            if r.ok:
                repos = r.json()
                lines = [f"GitHub repos for {username}:"]
                for repo in repos:
                    lines.append(f"  • {repo['name']} — ⭐{repo['stargazers_count']}")
                return "\n".join(lines)
            return f"GitHub: {r.status_code}"
        except Exception as e:
            return f"GitHub error: {e}"

    def github_trending(self) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                "https://api.github.com/search/repositories"
                "?q=stars:>1000&sort=stars&order=desc&per_page=5",
                timeout=5
            )
            if r.ok:
                items = r.json().get("items", [])
                lines = ["Trending GitHub repos:"]
                for item in items:
                    lines.append(f"  • {item['full_name']} ⭐{item['stargazers_count']}")
                return "\n".join(lines)
            return f"Could not fetch trending repos (HTTP {r.status_code})."
        except Exception as e:
            return f"GitHub trending error: {e}"

    # ── Spotify ───────────────────────────────────────────────────────────────
    def open_spotify_search(self, query: str) -> str:
        url = f"https://open.spotify.com/search/{query.replace(' ', '%20')}"
        webbrowser.open(url)
        return f"Opening Spotify search for '{query}', sir."

    # ── Google Drive ──────────────────────────────────────────────────────────
    def open_drive(self) -> str:
        webbrowser.open("https://drive.google.com")
        return "Opening Google Drive in browser, sir."

    def search_drive(self, query: str) -> str:
        url = f"https://drive.google.com/drive/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        return f"Searching Google Drive for '{query}', sir."

    # ── Trello ────────────────────────────────────────────────────────────────
    def open_trello(self) -> str:
        webbrowser.open("https://trello.com")
        return "Opening Trello, sir."

    # ── Slack ─────────────────────────────────────────────────────────────────
    def open_slack(self) -> str:
        webbrowser.open("https://app.slack.com")
        return "Opening Slack in browser, sir."

    # ── Notion ────────────────────────────────────────────────────────────────
    def open_notion(self) -> str:
        webbrowser.open("https://notion.so")
        return "Opening Notion, sir."

    # ── Currency conversion ───────────────────────────────────────────────────
    def convert_currency(self, amount: float, from_cur: str, to_cur: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_cur.upper()}",
                timeout=5
            )
            if r.ok:
                rate = r.json()["rates"].get(to_cur.upper())
                if rate:
                    result = amount * rate
                    return f"{amount} {from_cur.upper()} = {result:.2f} {to_cur.upper()}"
            return "Currency conversion failed."
        except Exception as e:
            return f"Currency error: {e}"

    # ── Dictionary ────────────────────────────────────────────────────────────
    def define_word(self, word: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=5
            )
            if r.ok:
                data = r.json()
                if isinstance(data, list) and data:
                    meanings = data[0].get("meanings", [])
                    if meanings:
                        defs = meanings[0].get("definitions", [])
                        if defs:
                            return f"{word}: {defs[0]['definition']}"
            return f"Definition not found for '{word}'."
        except Exception as e:
            return f"Dictionary error: {e}"

    # ── Wikipedia ─────────────────────────────────────────────────────────────
    def wiki_summary(self, query: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + query.replace(" ", "_"),
                timeout=5
            )
            if r.ok:
                data    = r.json()
                extract = data.get("extract", "")
                return extract[:400] + "..." if len(extract) > 400 else extract
            return f"No Wikipedia article found for '{query}'."
        except Exception as e:
            return f"Wikipedia error: {e}"

    # ── IP info ───────────────────────────────────────────────────────────────
    def ip_info(self) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get("https://ipinfo.io/json", timeout=5)
            if r.ok:
                d = r.json()
                return (
                    f"IP: {d.get('ip')} | "
                    f"Location: {d.get('city')}, {d.get('region')}, {d.get('country')} | "
                    f"ISP: {d.get('org')}"
                )
        except Exception as e:
            return f"IP info error: {e}"
        return "Could not fetch IP info."


# ── Singleton ─────────────────────────────────────────────────────────────────
services = ServiceIntegrations()
