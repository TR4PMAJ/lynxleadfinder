# Lynx & Co. Lead Finder

A static prospecting dashboard using a Philadelphia-area snapshot of Overture Maps Places. It does not call Google Places, Nominatim, or Overpass when a user searches.

## How search works

- The browser downloads one compressed Philadelphia-area business snapshot and searches it locally.
- Search filters business category and locality/ZIP, prioritizing records with no website recorded.
- The snapshot includes a business name, category, available address, phone, website, coordinates, confidence score, and source identifiers.
- Results and CSV export stay in browser memory for the current session.

## First-time setup

1. Open the repository's **Actions** tab on GitHub.
2. Select **Refresh Philadelphia Overture business index**.
3. Click **Run workflow** on the `main` branch.
4. Wait for the workflow to finish. It downloads a regional Overture Places extract, normalizes it, compresses it, and commits `public/data/philadelphia-places.json.gz`.
5. The new commit should trigger a Cloudflare Pages deployment. Once that deployment succeeds, refresh the website and search.

The workflow also runs monthly. No API key, Google billing account, public map-search API, or paid business-data API is required.

## Cloudflare Pages settings

- Project type: **Pages**, connected to this GitHub repository
- Production branch: `main`
- Framework preset: `None`
- Build command: `exit 0`
- Build output directory: `public`
- Root directory: repository root (default)

Do not use `npx wrangler deploy`; that is a Workers deployment command. This project is a Git-connected Cloudflare Pages site.

## Refresh and coverage

The current snapshot covers a Philadelphia metro bounding box (west -75.35, south 39.80, east -74.85, north 40.25). Searches outside this area will not return results. The upstream Overture Places theme is released monthly, and this repository's workflow refreshes the local snapshot monthly.

The build script checks that the compressed snapshot is below Cloudflare Pages' 25 MiB per-file asset limit. If the area extract grows beyond that, the workflow stops instead of committing a broken Pages asset; the index would need to move to a database or object store.

## Data quality and limitations

- This is a monthly snapshot, not a live business directory.
- A missing website or phone means the source snapshot has no value recorded for that field. It does not prove the business lacks a website or phone.
- Overture documents known data-quality issues including duplicates, junk records, and incomplete attributes. The build script removes exact duplicates by name/address/category, but it cannot independently verify a business.
- The confidence score is a relative source-quality signal, not a calibrated probability.
- Verify each prospect's identity, location, website, and contact details independently before outreach.

## Attribution and licensing

The Overture Places theme does not contain OpenStreetMap data. Overture lists source-specific licenses including CDLA-Permissive-2.0, Apache-2.0 (Foursquare), and CC0. This project includes the CDLA-Permissive-2.0 and Apache-2.0 license texts, the Foursquare NOTICE, and a summary of source/modification details:

- `public/OVERTURE-NOTICE.txt`
- `public/data/CDLA-Permissive-2.0.txt`
- `public/data/Apache-2.0.txt`
- `public/data/NOTICE.txt`

Review those notices and Overture's current attribution/licensing documentation before redistributing the snapshot or building a commercial product on it.
