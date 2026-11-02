# Lynx & Co. Lead Finder

A static small-business prospecting dashboard using a monthly Philadelphia-area / Pennsylvania / New Jersey snapshot of Overture Maps Places. Search clicks do not call Google Places, Nominatim, or Overpass.

## How search works

- GitHub Actions downloads Pennsylvania and New Jersey Overture Places records monthly.
- A build script normalizes the records and splits them into compressed geographic tiles.
- Cloudflare Pages serves those tiles as static assets. The browser loads only the tiles needed for the selected state and city/ZIP, then searches locally.
- Listings without a recorded website are prioritized. Results and CSV export stay in browser memory for the current session.

## First regional index build

A refresh starts automatically when the workflow or snapshot builder changes. You can also run it manually:

1. Open the repository's **Actions** tab.
2. Select **Refresh Pennsylvania and New Jersey Overture index**.
3. Click **Run workflow** on the `main` branch.
4. Wait for the download, normalization, and commit steps to complete.
5. The new commit triggers a Cloudflare Pages deployment. Once successful, refresh the website.

The workflow also runs monthly. No Google API key, paid API, or public map-search endpoint is required.

## Cloudflare Pages settings

- Project type: **Pages**, connected to this GitHub repository
- Production branch: `main`
- Framework preset: `None`
- Build command: `exit 0`
- Build output directory: `public`
- Root directory: repository root (default)

Do not use `npx wrangler deploy`; that is a Workers deployment command. This is a Git-connected Cloudflare Pages project.

## Coverage

Currently indexed states:
- Pennsylvania
- New Jersey

The regional bounding boxes are approximate and used to select source records. The builder streams the GeoJSON rather than loading all of each state into memory. If an Overture address explicitly identifies the other indexed state, that record is excluded from the current state input. A small number of records without state-level address metadata may still fall near state borders; verify each prospect before outreach.

The code stores records in state-specific, 0.125-degree geographic tiles. Any tile above 20 MiB compressed is subdivided before publishing, keeping each Pages asset below the 25 MiB file-size limit. This layout is designed to extend to additional states without building one huge download.

To add another state, add its bounding box and aliases in `scripts/build_overture_snapshot.py`, add a corresponding `overturemaps download --bbox=...` step in `.github/workflows/refresh-overture.yml`, and add its two-letter code/name in the browser's state resolver in `public/index.html`.

## Data quality and limitations

- This is a monthly snapshot, not a live business directory.
- A missing website or phone means the source snapshot has no value recorded for that field. It does not prove the business lacks a website or phone.
- Overture documents known data-quality issues including duplicates, junk records, and incomplete attributes. The builder removes exact duplicates by name/address/category, but cannot independently verify a business.
- The confidence score is a relative source-quality signal, not a calibrated probability.
- Verify every prospect's identity, location, website, and contact details before outreach.

## Attribution and licensing

The Overture Places theme does not contain OpenStreetMap data. Overture lists source-specific licenses including CDLA-Permissive-2.0, Apache-2.0 (Foursquare), and CC0. This project includes the CDLA-Permissive-2.0 and Apache-2.0 license texts, the Foursquare NOTICE, and a summary of source/modification details:

- `public/OVERTURE-NOTICE.txt`
- `public/data/CDLA-Permissive-2.0.txt`
- `public/data/Apache-2.0.txt`
- `public/data/NOTICE.txt`

Review those notices and Overture's current attribution/licensing documentation before redistributing the snapshot or building a commercial product on it.
