const TAGS = {
  "auto detailing":[["shop","car_repair"]],"car detailing":[["shop","car_repair"]],"mechanic":[["shop","car_repair"]],"auto repair":[["shop","car_repair"]],
  "barber":[["shop","hairdresser"]],"barbershop":[["shop","hairdresser"]],"hair salon":[["shop","hairdresser"]],"salon":[["shop","beauty"],["shop","hairdresser"]],
  "restaurant":[["amenity","restaurant"]],"cafe":[["amenity","cafe"]],"coffee shop":[["amenity","cafe"]],
  "plumber":[["craft","plumber"]],"electrician":[["craft","electrician"]],"dentist":[["amenity","dentist"]],"gym":[["leisure","fitness_centre"]],
  "florist":[["shop","florist"]],"bakery":[["shop","bakery"]],"laundromat":[["shop","laundry"]]
};

const OVERPASS_ENDPOINTS = [
  "https://overpass.private.coffee/api/interpreter",
  "https://overpass-api.de/api/interpreter"
];
const APP_URL = "https://lynxleadfinder.pages.dev/";

export async function onRequestPost({ request }) {
  let body;
  try { body = await request.json(); }
  catch { return json({ error: "Send valid JSON." }, 400); }

  const industry = String(body.industry || "").trim().slice(0, 80);
  const location = String(body.location || "").trim().slice(0, 120);
  const limit = Number(body.maxResultCount || 20);
  if (!industry || !location) return json({ error: "Enter a business type and location." }, 400);
  if (!Number.isInteger(limit) || limit < 1 || limit > 20) {
    return json({ error: "Choose between 1 and 20 results." }, 400);
  }

  try {
    const geoUrl = new URL("https://nominatim.openstreetmap.org/search");
    geoUrl.search = new URLSearchParams({ q: location, format: "jsonv2", limit: "1" }).toString();
    const geoRes = await fetch(geoUrl, {
      headers: {
        "User-Agent": "LynxLeadFinder/1.0 (https://lynxleadfinder.pages.dev/)",
        "Referer": APP_URL
      }
    });
    if (!geoRes.ok) {
      return json({ error: "The location lookup service is temporarily unavailable. Try again shortly." }, 502);
    }
    const geo = await geoRes.json();
    if (!geo.length) return json({ error: "Location not found. Try a city and state." }, 404);

    const lat = Number(geo[0].lat);
    const lon = Number(geo[0].lon);
    const normalized = industry.toLowerCase();
    const tags = TAGS[normalized] ||
      Object.entries(TAGS).find(([key]) => normalized.includes(key) || key.includes(normalized))?.[1] || [];

    // Limit the search radius and exclude unnamed map objects to reduce server load.
    const selectors = tags.length
      ? tags.map(([key, value]) =>
          `nwr(around:7000,${lat},${lon})["${key}"="${value}"]["name"];`
        ).join("\n")
      : `nwr(around:7000,${lat},${lon})["name"~"${escapeRegex(industry)}",i];`;
    const query = `[out:json][timeout:15][maxsize:134217728];(${selectors});out center tags;`;

    let result = null;
    let lastStatus = 0;
    let lastIssue = "The map data service could not be reached.";

    for (let index = 0; index < OVERPASS_ENDPOINTS.length; index++) {
      try {
        const response = await fetch(OVERPASS_ENDPOINTS[index], {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": "LynxLeadFinder/1.0 (https://lynxleadfinder.pages.dev/)",
            "Referer": APP_URL
          },
          body: "data=" + encodeURIComponent(query)
        });

        if (response.status === 429 || response.status === 406) {
          return json({
            error: "The OpenStreetMap search service has rate-limited this request. Please wait at least 30 seconds before searching again."
          }, 429);
        }

        if (!response.ok) {
          lastStatus = response.status;
          lastIssue = `The map data service returned HTTP ${response.status}.`;
          // Do not immediately repeat rate-limited requests. For server/network errors,
          // try the next independent public instance once.
          if (response.status >= 500 && index + 1 < OVERPASS_ENDPOINTS.length) continue;
          return json({ error: lastIssue + " Please try again later." }, 502);
        }

        const data = await response.json();
        if (data.remark && !Array.isArray(data.elements)) {
          lastIssue = "The map data service rejected or could not finish the search.";
          if (index + 1 < OVERPASS_ENDPOINTS.length) continue;
          return json({ error: lastIssue + " Try a smaller area or a different business type." }, 502);
        }

        result = data;
        break;
      } catch {
        lastIssue = "A connection to the map data service failed.";
        if (index + 1 >= OVERPASS_ENDPOINTS.length) {
          return json({ error: lastIssue + " Please try again later." }, 502);
        }
      }
    }

    if (!result) {
      return json({ error: lastIssue + (lastStatus ? ` (HTTP ${lastStatus})` : "") }, 502);
    }

    const places = (result.elements || []).map(element => {
      const tags = element.tags || {};
      const placeLat = element.lat ?? element.center?.lat;
      const placeLon = element.lon ?? element.center?.lon;
      const websiteUri = tags.website || tags["contact:website"] || "";
      const phone = tags.phone || tags["contact:phone"] || "";
      const address = [
        tags["addr:housenumber"], tags["addr:street"], tags["addr:city"], tags["addr:state"]
      ].filter(Boolean).join(" ");
      const mapUrl = Number.isFinite(placeLat) && Number.isFinite(placeLon)
        ? "https://www.openstreetmap.org/?mlat=" + placeLat + "&mlon=" + placeLon + "#map=18/" + placeLat + "/" + placeLon
        : "";

      return {
        id: element.type + "/" + element.id,
        name: tags.name || tags.brand || "",
        phone,
        address: address || geo[0].display_name || location,
        websiteUri,
        googleMapsUri: mapUrl
      };
    })
      .filter(place => place.name)
      .sort((a, b) => Number(!a.websiteUri) - Number(!b.websiteUri))
      .slice(0, limit);

    return json({ places, source: "OpenStreetMap" });
  } catch {
    return json({ error: "The free map search could not be completed. Please try again shortly." }, 502);
  }
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}