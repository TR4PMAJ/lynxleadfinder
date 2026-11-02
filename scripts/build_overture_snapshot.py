#!/usr/bin/env python3
"""Build small, state-aware, compressed Overture Places shards for Cloudflare Pages."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_PAGES_ASSET_BYTES = 20 * 1024 * 1024
INITIAL_TILE_DEGREES = 0.5
MIN_TILE_DEGREES = 0.125

REGIONS = {
    "PA": {
        "name": "Pennsylvania",
        "bbox": (-80.52, 39.72, -74.69, 42.27),
        "aliases": {"pa", "pennsylvania", "us-pa"},
    },
    "NJ": {
        "name": "New Jersey",
        "bbox": (-75.56, 38.92, -73.89, 41.36),
        "aliases": {"nj", "new jersey", "us-nj"},
    },
}


def first_value(value: Any) -> str:
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
    return value if isinstance(value, list) else ([value] if value is not None else [])


def normalize_region(value: str) -> str:
    text = " ".join(value.casefold().replace("-", " ").split())
    if text in {"pa", "pennsylvania", "us pa", "united states pa"}:
        return "PA"
    if text in {"nj", "new jersey", "us nj", "united states nj"}:
        return "NJ"
    return ""


def within_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def normalize_feature(feature: dict[str, Any], region_code: str) -> dict[str, Any] | None:
    props = as_object(feature.get("properties"))
    names = as_object(props.get("names"))
    name = first_value(names.get("primary") or props.get("name"))
    if not name:
        return None

    taxonomy = as_object(props.get("taxonomy"))
    category = first_value(taxonomy.get("primary") or props.get("basic_category"))
    hierarchy = as_list(taxonomy.get("hierarchy"))
    alternates = as_list(taxonomy.get("alternates"))
    categories: list[str] = []
    for item in [category, first_value(props.get("basic_category")), *hierarchy, *alternates]:
        label = first_value(item)
        if label and label not in categories:
            categories.append(label)

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

    explicit_region = normalize_region(region)
    if explicit_region and explicit_region != region_code:
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

    if not within_bbox(longitude, latitude, REGIONS[region_code]["bbox"]):
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
        "regionCode": region_code,
        "postcode": postcode,
        "phone": phone,
        "website": website,
        "latitude": latitude,
        "longitude": longitude,
        "confidence": confidence,
        "operatingStatus": first_value(props.get("operating_status")),
        "sources": sources,
    }


def compress_document(document: dict[str, Any]) -> bytes:
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=9, mtime=0)


def tile_bounds(records: list[dict[str, Any]], size: float) -> tuple[int, int, int, int]:
    lat_ids = [math.floor(row["latitude"] / size) for row in records]
    lon_ids = [math.floor(row["longitude"] / size) for row in records]
    return min(lat_ids), min(lon_ids), max(lat_ids), max(lon_ids)


def write_tile(
    region_code: str,
    records: list[dict[str, Any]],
    size: float,
    output_root: Path,
    manifest_tiles: list[dict[str, Any]],
) -> None:
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            math.floor(record["latitude"] / size),
            math.floor(record["longitude"] / size),
        )
        buckets.setdefault(key, []).append(record)

    for (lat_id, lon_id), tile_records in sorted(buckets.items()):
        tile_id = f"tile_{lat_id}_{lon_id}"
        document = {
            "source": "Overture Maps Places",
            "region": region_code,
            "tile": tile_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "count": len(tile_records),
            "places": tile_records,
        }
        compressed = compress_document(document)
        if len(compressed) > MAX_PAGES_ASSET_BYTES:
            if size / 2 < MIN_TILE_DEGREES:
                raise SystemExit(
                    f"{region_code} {tile_id} is still larger than 20 MiB after subdivision. "
                    "Reduce the tile size or move the data to a database/object store."
                )
            write_tile(region_code, tile_records, size / 2, output_root, manifest_tiles)
            continue

        relative_path = f"regions/{region_code.lower()}/{tile_id}.json.gz"
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(compressed)

        lat_min = lat_id * size
        lon_min = lon_id * size
        manifest_tiles.append({
            "id": tile_id,
            "file": relative_path,
            "count": len(tile_records),
            "bbox": [lon_min, lat_min, lon_min + size, lat_min + size],
            "localities": sorted({row["locality"] for row in tile_records if row["locality"]}),
            "postcodes": sorted({row["postcode"] for row in tile_records if row["postcode"]}),
        })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="STATE=PATH",
        help="Input Overture GeoJSON, for example PA=/tmp/pa.geojson. Repeat for each state.",
    )
    parser.add_argument("--output", required=True, help="Output directory, e.g. public/data")
    args = parser.parse_args()

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    regions_root = output_root / "regions"
    if regions_root.exists():
        shutil.rmtree(regions_root)
    regions_root.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest_regions = []

    for input_spec in args.input:
        if "=" not in input_spec:
            raise SystemExit(f"Invalid --input value {input_spec!r}; expected STATE=PATH.")
        region_code, path_text = input_spec.split("=", 1)
        region_code = region_code.upper()
        if region_code not in REGIONS:
            raise SystemExit(f"Unsupported region {region_code!r}. Supported: {', '.join(REGIONS)}.")

        input_path = Path(path_text)
        with input_path.open("r", encoding="utf-8") as handle:
            source_doc = json.load(handle)

        features = source_doc.get("features", [])
        records: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for feature in features:
            if not isinstance(feature, dict):
                continue
            record = normalize_feature(feature, region_code)
            if not record:
                continue
            location_key = (
                record["address"] or record["postcode"] or
                f'{record["latitude"]:.5f},{record["longitude"]:.5f}'
            )
            dedupe_key = (
                record["name"].casefold().strip(),
                location_key.casefold().strip(),
                record["category"].casefold().strip(),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            records.append(record)

        records.sort(
            key=lambda row: (
                bool(row["website"]),
                -(row["confidence"] if row["confidence"] is not None else -1),
                row["name"].casefold(),
            )
        )

        region_tiles: list[dict[str, Any]] = []
        write_tile(region_code, records, INITIAL_TILE_DEGREES, output_root, region_tiles)
        region_tiles.sort(key=lambda item: item["id"])
        manifest_regions.append({
            "code": region_code,
            "name": REGIONS[region_code]["name"],
            "bbox": list(REGIONS[region_code]["bbox"]),
            "count": len(records),
            "tiles": region_tiles,
        })
        print(f"{REGIONS[region_code]['name']}: {len(records):,} places in {len(region_tiles)} tiles.")

    manifest = {
        "source": "Overture Maps Places",
        "generatedAt": generated_at,
        "regions": sorted(manifest_regions, key=lambda item: item["code"]),
    }
    manifest_path = output_root / "regions.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
