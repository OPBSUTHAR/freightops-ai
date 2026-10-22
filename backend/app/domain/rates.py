"""Freight pricing domain service: lane distance, carrier rates, quote drafting."""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import settings
from ..store import new_id

CITIES = {
    "chicago": (41.8781, -87.6298),
    "dallas": (32.7767, -96.7970),
    "atlanta": (33.7490, -84.3880),
    "los angeles": (34.0522, -118.2437),
    "newark": (40.7357, -74.1724),
    "memphis": (35.1495, -90.0490),
    "columbus": (39.9612, -82.9988),
    "denver": (39.7392, -104.9903),
    "seattle": (47.6062, -122.3321),
    "miami": (25.7617, -80.1918),
    "houston": (29.7604, -95.3698),
    "phoenix": (33.4484, -112.0740),
    "kansas city": (39.0997, -94.5786),
    "charlotte": (35.2271, -80.8431),
    "indianapolis": (39.7684, -86.1581),
    "laredo": (27.5064, -99.5075),
    "detroit": (42.3314, -83.0458),
    "savannah": (32.0809, -81.0912),
}

CARRIERS = [
    {"code": "PCL", "name": "PaceLane Network", "scac": "PCLN", "reliability": 0.94, "on_time": 0.95, "modes": ["LTL", "FTL"], "multiplier": 0.98, "capacity": 0.90, "speed": 0},
    {"code": "NWF", "name": "Northwind Freight", "scac": "NWFD", "reliability": 0.89, "on_time": 0.91, "modes": ["LTL", "FTL", "Intermodal"], "multiplier": 1.04, "capacity": 0.82, "speed": 0},
    {"code": "BRD", "name": "BlueRoad Logistics", "scac": "BRDL", "reliability": 0.96, "on_time": 0.97, "modes": ["FTL", "LTL"], "multiplier": 1.09, "capacity": 0.95, "speed": -1},
    {"code": "SGL", "name": "Southgate Intermodal", "scac": "SGIL", "reliability": 0.87, "on_time": 0.89, "modes": ["Intermodal", "FTL"], "multiplier": 0.93, "capacity": 0.78, "speed": 1},
    {"code": "HRZ", "name": "Horizon Parcel", "scac": "HRZP", "reliability": 0.92, "on_time": 0.93, "modes": ["Parcel", "LTL"], "multiplier": 1.01, "capacity": 0.88, "speed": 0},
    {"code": "VLT", "name": "Velocity Drayage", "scac": "VLTD", "reliability": 0.78, "on_time": 0.80, "modes": ["FTL", "LTL"], "multiplier": 0.88, "capacity": 0.70, "speed": 1},
]

BASE_RATE_PER_MILE = {"LTL": 1.55, "FTL": 2.35, "Parcel": 0.90, "Intermodal": 1.15}
MIN_CHARGE = {"LTL": 185.0, "FTL": 350.0, "Parcel": 45.0, "Intermodal": 600.0}
FUEL_SURCHARGE = 0.18

ACCESSORIALS = [
    {"code": "LIFTGATE", "label": "Liftgate", "amount": 185.0},
    {"code": "RESIDENTIAL", "label": "Residential delivery", "amount": 145.0},
    {"code": "INSIDE", "label": "Inside delivery", "amount": 210.0},
    {"code": "APPOINTMENT", "label": "Appointment / timed delivery", "amount": 55.0},
    {"code": "DETENTION", "label": "Detention (per hour after 2 free)", "amount": 95.0},
    {"code": "HAZMAT", "label": "Hazmat handling", "amount": 325.0},
    {"code": "REDELIVERY", "label": "Redelivery", "amount": 175.0},
    {"code": "DRIVER_ASSIST", "label": "Driver assist", "amount": 120.0},
]


def city_key(value: str) -> str:
    return value.split(",")[0].strip().lower()


def lane_miles(origin: str, destination: str) -> dict[str, Any]:
    a, b = CITIES.get(city_key(origin)), CITIES.get(city_key(destination))
    if a and b:
        lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        miles = round(2 * 3958.8 * math.asin(math.sqrt(h)) * 1.17)
        return {"miles": max(miles, 45), "known": True}
    seed = sum(ord(c) for c in f"{origin}{destination}".lower())
    return {"miles": 300 + (seed * 7) % 1500, "known": False}


def _weight_factor(mode: str, weight_lb: float) -> float:
    if mode in ("FTL", "Intermodal"):
        return 1.0
    tons = max(weight_lb, 100.0) / 1000
    return max(0.72, tons ** 0.72) if mode == "LTL" else max(0.55, tons ** 0.35)


def rate_lane(req: dict[str, Any]) -> dict[str, Any]:
    origin, destination = req["origin"], req["destination"]
    mode, weight = req.get("mode", "LTL"), float(req.get("weight_lb", 1200))
    lane = lane_miles(origin, destination)
    miles = lane["miles"]

    linehaul = max(miles * BASE_RATE_PER_MILE[mode] * _weight_factor(mode, weight), MIN_CHARGE[mode])
    linehaul = round(linehaul * (1 + FUEL_SURCHARGE), 2)

    options: list[dict[str, Any]] = []
    for carrier in CARRIERS:
        if mode not in carrier["modes"]:
            continue
        buy = round(linehaul * carrier["multiplier"], 2)
        options.append(
            {
                "carrier_code": carrier["code"],
                "carrier": carrier["name"],
                "scac": carrier["scac"],
                "reliability": carrier["reliability"],
                "on_time": carrier["on_time"],
                "capacity": carrier["capacity"],
                "buy_rate": buy,
                "transit_days": max(1, math.ceil(miles / 550) + carrier["speed"]),
                "equipment": req.get("equipment", "Dry Van 53'"),
                "tenderable": carrier["reliability"] >= settings.carrier_reliability_floor,
            }
        )

    benchmark = round(statistics.median(o["buy_rate"] for o in options), 2) if options else 0.0
    best_tenderable = min((o["buy_rate"] for o in options if o["tenderable"]), default=0.0)
    for option in options:
        option["vs_benchmark_pct"] = round((option["buy_rate"] - benchmark) / benchmark * 100, 2) if benchmark else 0.0
        price_score = min(1.0, benchmark / option["buy_rate"]) if option["buy_rate"] else 0.0
        option["score"] = round(0.5 * option["on_time"] + 0.3 * price_score + 0.2 * option["capacity"], 3)
        option["recommended"] = option["tenderable"] and option["buy_rate"] == best_tenderable
    options.sort(key=lambda o: (not o["tenderable"], -o["score"]))

    return {
        "lane": {
            "origin": origin,
            "destination": destination,
            "miles": miles,
            "known_lane": lane["known"],
            "mode": mode,
            "weight_lb": weight,
            "equipment": req.get("equipment", "Dry Van 53'"),
            "commodity": req.get("commodity", "General freight"),
        },
        "benchmark_buy": benchmark,
        "fuel_surcharge_pct": FUEL_SURCHARGE * 100,
        "accessorials": ACCESSORIALS,
        "options": options,
        "priced_at": datetime.now(timezone.utc).isoformat(),
    }


def pick_option(rate: dict[str, Any], carrier_code: str) -> dict[str, Any] | None:
    for option in rate["options"]:
        if option["carrier_code"].upper() == carrier_code.upper() or option["carrier"].lower() == carrier_code.lower():
            return option
    return None


def build_quote(req: dict[str, Any], rate: dict[str, Any], option: dict[str, Any], margin_pct: float | None = None) -> dict[str, Any]:
    margin = float(margin_pct if margin_pct is not None else 18.0)
    buy = round(option["buy_rate"], 2)
    sell = round(buy / (1 - margin / 100), 2) if margin < 100 else buy
    now = datetime.now(timezone.utc)
    quote_id = f"Q-{now:%y%m%d}-{new_id('x').split('_')[1][:4].upper()}"
    return {
        "id": new_id("quo"),
        "quote_id": quote_id,
        "customer": req.get("customer", "Acme Distribution"),
        "origin": rate["lane"]["origin"],
        "destination": rate["lane"]["destination"],
        "mode": rate["lane"]["mode"],
        "equipment": rate["lane"]["equipment"],
        "commodity": rate["lane"]["commodity"],
        "weight_lb": rate["lane"]["weight_lb"],
        "miles": rate["lane"]["miles"],
        "carrier": option["carrier"],
        "carrier_code": option["carrier_code"],
        "scac": option["scac"],
        "carrier_reliability": option["reliability"],
        "transit_days": option["transit_days"],
        "buy": buy,
        "sell": sell,
        "margin_pct": round((sell - buy) / sell * 100, 2) if sell else 0.0,
        "status": "draft",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "accessorials": [],
        "notes": [],
    }
