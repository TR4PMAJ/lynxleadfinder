# Lynx & Co. Lead Finder

A small-business prospecting dashboard built with static HTML and a Cloudflare Pages Function.

## Features

- Search Google Places by business type and location
- Show returned business name, phone, address, website and Maps link
- Filter listings where Google did not return a website
- Export the current search results to CSV
- Keep the Google API key on the server, never in browser JavaScript

## Run locally

This project uses Cloudflare Pages Functions. Install Node.js and Wrangler:

```bash
npm install -D wrangler
npx wrangler pages dev .
```

Set a local secret for the Pages Function. Create a `.dev.vars` file in the project root:

```env
GOOGLE_PLACES_API_KEY=your_google_places_api_key
```

Do not commit `.dev.vars` or share your API key. Add it to `.gitignore`.

Then open the local URL Wrangler prints.

## Google Places setup

1. Create or select a project in Google Cloud Console.
2. Enable Places API (New).
3. Configure billing and review current Places API pricing.
4. Create an API key and restrict it to Places API (New).
5. Set the key as a Cloudflare Pages environment variable named `GOOGLE_PLACES_API_KEY`.

The app requests business name, address, phone number, website URI and Google Maps URI. These fields can have different billing implications. Review Google's current Places API pricing, policies, attribution and storage requirements before using the results commercially or storing them in a CRM.

A missing `websiteUri` means Google did not return a website for that place. It does not prove the business has no website. Verify each prospect independently before outreach.

## Deploy to Cloudflare Pages

1. In Cloudflare, open Workers & Pages and create a Pages project connected to this GitHub repository.
2. Select the `main` branch.
3. For this static HTML + Pages Functions project, set the build command to blank and the output directory to `/`.
4. In project Settings → Variables and Secrets, add `GOOGLE_PLACES_API_KEY` as a secret.
5. Deploy and test a search.

Never put the Google API key in `index.html`, a public GitHub file, or frontend JavaScript.

## Current limitations

- Search results are limited to one Google Places Text Search response (up to 20).
- The browser holds results in memory; refreshing the page clears the list.
- CSV export is for the current in-memory search session. Confirm Google's terms permit your intended use before retaining or exporting Places content.
- No automatic website crawling or independent website verification is implemented yet.
