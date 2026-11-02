# Lynx & Co. Lead Finder

A small-business prospecting dashboard using OpenStreetMap community data and Cloudflare Pages Functions. No Google Places API key or billing account is required.

## Features

- Search local businesses by type and location
- Show business name, available phone/address, website tag and map link
- Filter listings where no website is recorded in OpenStreetMap
- Export current in-memory results to CSV
- Keep external service requests in a server-side Pages Function

## Deploy to Cloudflare Pages

1. In Cloudflare, create or open a **Pages** project connected to this GitHub repository (not a Workers project).
2. Select the `main` branch.
3. Set the framework preset to **None**.
4. Leave the build command blank and set the build output directory to `public`.
5. Save and deploy. No API key, secret, or billing configuration is needed.

The static website is in `public/`. The Pages Function stays in the repository-root `functions/` folder, where Cloudflare expects it.

**Important:** For this Git-connected Pages project, do not enter a Wrangler deploy command. Cloudflare automatically builds and deploys each push to `main`. The `npx wrangler pages deploy public --project-name <your-pages-project-name>` command is only for a separate manual CLI deployment workflow.

The `functions/api/search.js` file handles requests to `/api/search`.

## Run locally

Install Node.js and Wrangler, then run:

```bash
npm install -D wrangler
npx wrangler pages dev public
```

No `.dev.vars` file is required.

## Data sources and limitations

- Location lookup: OpenStreetMap Nominatim.
- Business/map data: OpenStreetMap Overpass API.
- Search coverage depends on what OpenStreetMap contributors have mapped. It is not a complete business directory.
- “No website listed” means no website tag was present in the returned map record. It does not prove the business has no website.
- Common categories include barbers, salons, restaurants, cafes, auto repair, plumbers, electricians, dentists and gyms. Other terms use a name match and may return fewer relevant results.
- Public community endpoints are shared resources and may rate-limit or temporarily reject requests. Avoid rapid repeated searches or bulk automated querying.
- Results are held in browser memory and cleared when the page is refreshed. CSV export is only for the current session.

## Attribution and licensing

Map data © OpenStreetMap contributors, available under the Open Database License (ODbL). Review the OpenStreetMap Foundation's Nominatim and Overpass usage policies before scaling or commercializing this service. Public community endpoints are not an unlimited production API.
