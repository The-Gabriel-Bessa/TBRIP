"""Parse and compare visible lines from Tibia's Loot channel."""

from __future__ import annotations

import re
from collections import Counter


TIME_PREFIX = re.compile(r"^\s*(?P<time>\d{1,2}:\d{2})\s+(?P<message>.+?)\s*$")
LOOT_OF = re.compile(r"loot of (?:an?|the)\s+(?P<creature>[^:]+):\s*(?P<items>.+)", re.IGNORECASE)
WANTED_CREATURES = {"amazon", "witch", "valkyrie"}
WANTED_ITEMS = {
    "gold coin": re.compile(r"(?:(?P<quantity>\d+)|an?)?\s*gold coins?", re.IGNORECASE),
    "broom": re.compile(r"(?:(?P<quantity>\d+)|an?)?\s*brooms?", re.IGNORECASE),
    "protective charm": re.compile(
        r"(?:(?P<quantity>\d+)|an?)?\s*protective charms?", re.IGNORECASE
    ),
    "girlish hair decoration": re.compile(
        r"(?:(?P<quantity>\d+)|an?)?\s*girlish hair decorations?", re.IGNORECASE
    ),
}


def clean_line(line: str) -> str:
    return " ".join(line.replace("�", "").strip(" |\t").split())


def visible_lines(text: str) -> list[str]:
    return [cleaned for line in text.splitlines() if (cleaned := clean_line(line))]


def comparison_key(line: str) -> str:
    cleaned = clean_line(line)
    cleaned = re.sub(r"\s+(?:[lI][a-z]{0,2}|[\[\];$<>¢¥]+)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.rstrip(" .|[];$<>¢¥").casefold()


def new_visible_lines(before: str, after: str) -> list[str]:
    remaining = Counter(comparison_key(line) for line in visible_lines(before))
    added = []
    for line in visible_lines(after):
        key = comparison_key(line)
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            added.append(line)
    return added


def extract_wanted_items(items: str) -> list[dict]:
    found = []
    for name, pattern in WANTED_ITEMS.items():
        for match in pattern.finditer(items):
            quantity = int(match.group("quantity")) if match.group("quantity") else 1
            found.append({"name": name, "quantity": quantity, "ocr_text": match.group(0).strip()})
    return found


def parse_line(line: str) -> dict:
    cleaned = clean_line(line)
    match = TIME_PREFIX.match(cleaned)
    timestamp = match.group("time") if match else None
    message = match.group("message") if match else cleaned
    lowered = message.casefold()

    loot_match = LOOT_OF.search(message)
    if loot_match:
        items = clean_line(loot_match.group("items"))
        items = re.sub(r"\.\s*[lI]*$", "", items).strip(". |")
        creature = clean_line(loot_match.group("creature")).casefold()
        return {
            "type": "loot_of",
            "time": timestamp,
            "creature": creature,
            "wanted_creature": creature in WANTED_CREATURES,
            "items": items,
            "wanted_items": extract_wanted_items(items),
            "raw": cleaned,
        }
    if "you looted none" in lowered:
        return {"type": "none_collected", "time": timestamp, "raw": cleaned}
    if "you looted nothing" in lowered:
        return {"type": "nothing_found", "time": timestamp, "raw": cleaned}
    if "you looted" in lowered:
        return {"type": "loot_summary", "time": timestamp, "raw": cleaned}
    if "container for unassigned loot is full" in lowered:
        return {"type": "server_log_noise", "time": timestamp, "raw": cleaned}
    return {"type": "other", "time": timestamp, "raw": cleaned}


def parse_new_entries(before: str, after: str) -> list[dict]:
    return [parse_line(line) for line in new_visible_lines(before, after)]


def terminal_entries(entries: list[dict]) -> list[dict]:
    terminal_types = {
        "loot_of",
        "none_collected",
        "nothing_found",
        "loot_summary",
    }
    return [entry for entry in entries if entry["type"] in terminal_types]
