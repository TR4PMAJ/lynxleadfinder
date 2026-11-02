#!/usr/bin/env python3
"""Stream Overture Places into small state-aware static search tiles."""

from __future__ import annotations

import argparse
import gzip
import math
import shutil
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import ijson
import orjson

MAX_PAGES_ASSET_BYTES = 20 * 1024 * 1024
TILE_DEGREES = 0.125
MAX_OPEN_HANDLES = 48

REGIONS = {
    "PA": {
        "name": "Pennsylvania",
        "bbox": (-80.52, 39.72, -74.69, 42.27),
    },
    "NJ": {
        "name": "New Jersey",
        "bbox": (-75.56, 38.92, -73.89, 41.36),
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
    postcode_raw = first_value(address_obj.get("postcode"))
    postcode = postcode_raw[:5] if len(postcode_raw) >= 5 and postcode_raw[:5].isdigit() else postcode_raw
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

    websites = as_list(props.get("websites"))
    phones = as_list(props.get("phones"))
    sources = []
    for source in as_list(props.get("sources")):
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
        "phone": first_value(phones),
        "website": first_value(websites),
        "latitude": latitude,
        "longitude": longitude,
        "confidence": confidence,
        "operatingStatus": first_value(props.get("operating_status")),
        "sources": sources,
    }


class TileWriter:
    """Stream records into tile JSON files while keeping few handles open."""

    def __init__(self, region_code: str, output_root: Path, generated_at: str):
        self.region_code = region_code
        self.output_root = output_root
        self.generated_at = generated_at
        self.temp_root = output_root / ".tile-work" / region_code.lower()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.handles: OrderedDict[str, BinaryIO] = OrderedDict()
        self.counts: dict[str, int] = {}
        self.localities: dict[str, set[str]] = {}
        self.postcodes: dict[str, set[str]] = {}

    def _get_handle(self, tile_id: str) -> BinaryIO:
        if tile_id in self.handles:
            self.handles.move_to_end(tile_id)
            return self.handles[tile_id]
        if len(self.handles) >= MAX_OPEN_HANDLES:
            _, oldest = self.handles.popitem(last=False)
            oldest.close()

        path = self.temp_root / f"{tile_id}.json"
        mode = "ab" if self.counts.get(tile_id, 0) else "wb"
        handle = path.open(mode)
        if mode == "wb":
            handle.write(b'{"places":[')
        self.handles[tile_id] = handle
        return handle

    def add(self, record: dict[str, Any]) -> None:
        lat_id = math.floor(record["latitude"] / TILE_DEGREES)
        lon_id = math.floor(record["longitude"] / TILE_DEGREES)
        tile_id = f"tile_{lat_id}_{lon_id}"
        count = self.counts.get(tile_id, 0)
        handle = self._get_handle(tile_id)
        if count:
            handle.write(b",")
        handle.write(orjson.dumps(record))
        self.counts[tile_id] = count + 1
        if record["locality"]:
            self.localities.setdefault(tile_id, set()).add(record["locality"])
        if record["postcode"]:
            self.postcodes.setdefault(tile_id, set()).add(record["postcode"])

    def finish(self) -> tuple[list[dict[str, Any]], int]:
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()

        tiles: list[dict[str, Any]] = []
        total_bytes = 0
        destination_root = self.output_root / "regions" / self.region_code.lower()
        destination_root.mkdir(parents=True, exist_ok=True)

        for tile_id, count in sorted(self.counts.items()):
            temp_file = self.temp_root / f"{tile_id}.json"
            with temp_file.open("ab") as handle:
                handle.write(b"]}")
            relative_path = f"regions/{self.region_code.lower()}/{tile_id}.json.gz"
            output_file = self.output_root / relative_path
            with temp_file.open("rb") as source, output_file.open("wb") as destination:
                with gzip.GzipFile(fileobj=destination, mode="wb", compresslevel=9, mtime=0) as compressed:
                    shutil.copyfileobj(source, compressed, length=1024 * 1024)

            size = output_file.stat().st_size
            if size > MAX_PAGES_ASSET_BYTES:
                raise SystemExit(
                    f"{self.region_code} {tile_id} is {size / 1024 / 1024:.1f} MiB, above the Pages file limit. "
                    "Reduce TILE_DEGREES before publishing."
                )
            total_bytes += size
            lat_id, lon_id = (int(value) for value in tile_id.removeprefix("tile_").split("_"))
            lat_min = lat_id * TILE_DEGREES
            lon_min = lon_id * TILE_DEGREES
            tiles.append({
                "id": tile_id,
                "file": relative_path,
                "count": count,
                "bbox": [lon_min, lat_min, lon_min + TILE_DEGREES, lat_min + TILE_DEGREES],
                "localities": sorted(self.localities.get(tile_id, set())),
                "postcodes": sorted(self.postcodes.get(tile_id, set())),
            })
            temp_file.unlink()
        shutil.rmtree(self.temp_root, ignore_errors=True)
        return tiles, total_bytes


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
    shutil.rmtree(output_root / ".tile-work", ignore_errors=True)

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
        writer = TileWriter(region_code, output_root, generated_at)
        count = 0
        print(f"Streaming {REGIONS[region_code]['name']} records from {input_path}...", flush=True)
        with input_path.open("rb") as handle:
            for feature in ijson.items(handle, "features.item"):
                if not isinstance(feature, dict):
                    continue
                record = normalize_feature(feature, region_code)
                if record:
                    writer.add(record)
                    count += 1
                    if count % 100_000 == 0:
                        print(f"{REGIONS[region_code]['name']}: normalized {count:,} places...", flush=True)

        if count == 0:
            raise SystemExit(f"No named places were found for {REGIONS[region_code]['name']}; refusing an empty index.")

        region_tiles, bytes_written = writer.finish()
        region_tiles.sort(key=lambda item: item["id"])
        manifest_regions.append({
            "code": region_code,
            "name": REGIONS[region_code]["name"],
            "bbox": list(REGIONS[region_code]["bbox"]),
            "count": count,
            "compressedBytes": bytes_written,
            "tiles": region_tiles,
        })
        print(
            f"{REGIONS[region_code]['name']}: {count:,} places, "
            f"{len(region_tiles)} tiles, {bytes_written / 1024 / 1024:.1f} MiB compressed.",
            flush=True,
        )

    manifest = {
        "source": "Overture Maps Places",
        "generatedAt": generated_at,
        "regions": sorted(manifest_regions, key=lambda item: item["code"]),
    }
    manifest_path = output_root / "regions.json"
    manifest_path.write_bytes(orjson.dumps(manifest))
    print(f"Wrote manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
