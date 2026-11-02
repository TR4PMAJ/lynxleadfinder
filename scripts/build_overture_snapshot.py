#!/usr/bin/env python3
"""Normalize a small Overture Places GeoJSON extract for the Lynx Lead Finder."""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_PAGES_ASSET_BYTES = 25 * 1024 * 1024


def first_value(value: Any) -> str:
    """Return the first useful string from Overture's scalar/list structures."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            result = first_value(item)
            if result:
                return result
    if isinstance(value, dict):
        for key in ("value", "url", "freeform", "primary", "name"):
            result = first_value(value.get(key))
            if result:
                return result
    return ""


def as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value is not None else []


def normalize_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    props = as_object(feature.get("properties"))
    names = as_object(props.get("names"))
    name = first_value(names.get("primary") or props.get("name"))
    if not name:
        return None

    taxonomy = as_object(props.get("taxonomy"))
    category = first_value(taxonomy.get("primary") or props.get("basic_category"))
    alternates = as_list(taxonomy.get("alternates"))
    hierarchy = as_list(taxonomy.get("hierarchy"))
    categories = []
    for item in [category, first_value(props.get("basic_category")), *hierarchy, *alternates]:
        text = first_value(item)
        if text and text not in categories:
            categories.append(text)

    addresses = as_list(props.get("addresses"))
    address_obj = as_object(addresses[0]) if addresses else {}
    locality = first_value(address_obj.get("locality"))
    region = first_value(address_obj.get("region"))
    postcode = first_value(address_obj.get("postcode"))
    country = first_value(address_obj.get("country"))
    address = first_value(address_obj.get("freeform"))
    if not address:
        address = " ".join(
            part for part in (
                first_value(address_obj.get("house_number")),
                first_value(address_obj.get("street")),
                locality,
                region,
                postcode,
            ) if part
        )

    if country and country.upper() not in {"US", "USA", "UNITED STATES"}:
        return None

    websites = as_list(props.get("websites"))
    phones = as_list(props.get("phones"))
    website = first_value(websites)
    phone = first_value(phones)

    geometry = as_object(feature.get("geometry"))
    coordinates = as_list(geometry.get("coordinates"))
    if len(coordinates) < 2:
        return None
    try:
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None

    raw_sources = as_list(props.get("sources"))
    sources = []
    for source in raw_sources:
        source_obj = as_object(source)
        dataset = first_value(source_obj.get("dataset"))
        license_name = first_value(source_obj.get("license"))
        if dataset:
            item = {"dataset": dataset}
            if license_name:
                item["license"] = license_name
            if item not in sources:
                sources.append(item)

    confidence = props.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    return {
        "id": first_value(props.get("id") or feature.get("id")),
        "name": name,
        "category": category,
        "categories": categories,
        "address": address,
        "locality": locality,
        "region": region,
        "postcode": postcode,
        "phone": phone,
        "website": website,
        "latitude": latitude,
        "longitude": longitude,
        "confidence": confidence,
        "operatingStatus": first_value(props.get("operating_status")),
        "sources": sources,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as handle:
        source_doc = json.load(handle)

    features = source_doc.get("features", [])
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for feature in features:
        if not isinstance(feature, dict):
            continue
        record = normalize_feature(feature)
        if not record:
            continue
        location_key = (record["address"] or record["postcode"] or
                        f'{record["latitude"]:.5f},{record["longitude"]:.5f}')
        dedupe_key = (
            record["name"].casefold().strip(),
            location_key.casefold().strip(),
            record["category"].casefold().strip(),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append(record)

    # Put records with missing website fields first, then the stronger confidence
    # signals. Confidence is only a relative quality signal, not a probability.
    records.sort(
        key=lambda row: (
            bool(row["website"]),
            -(row["confidence"] if row["confidence"] is not None else -1),
            row["name"].casefold(),
        )
    )

    document = {
        "source": "Overture Maps Places",
        "area": "Philadelphia metro snapshot",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "places": records,
    }

    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with output_path.open("wb") as raw_handle:
        with gzip.GzipFile(fileobj=raw_handle, mode="wb", compresslevel=9, mtime=0) as gz:
            gz.write(raw)

    output_size = output_path.stat().st_size
    print(f"Normalized {len(records):,} named places.")
    print(f"Compressed snapshot: {output_size:,} bytes ({output_size / 1024 / 1024:.2f} MiB).")

    if not records:
        raise SystemExit("No named place records were found; refusing to publish an empty snapshot.")
    if output_size > MAX_PAGES_ASSET_BYTES:
        raise SystemExit(
            "The snapshot is larger than Cloudflare Pages' 25 MiB per-file limit. "
            "We need to narrow the area or store the index in a database/object store."
        )


if __name__ == "__main__":
    main()
