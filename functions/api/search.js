const FIELD_MASK = [
  "places.id",
  "places.displayName",
  "places.formattedAddress",
  "places.nationalPhoneNumber",
  "places.websiteUri",
  "places.googleMapsUri"
].join(",");

export async function onRequestPost({ request, env }) {
  if (!env.GOOGLE_PLACES_API_KEY) {
    return json({ error: "The Google Places API key is not configured on the server yet." }, 500);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Send a valid JSON request." }, 400);
  }

  const industry = String(body.industry || "").trim().slice(0, 100);
  const location = String(body.location || "").trim().slice(0, 120);
  const maxResultCount = Number(body.maxResultCount || 20);

  if (!industry || !location) {
    return json({ error: "Enter both a business type and a location." }, 400);
  }
  if (!Number.isInteger(maxResultCount) || maxResultCount < 1 || maxResultCount > 20) {
    return json({ error: "Results per search must be between 1 and 20." }, 400);
  }

  try {
    const upstream = await fetch("https://places.googleapis.com/v1/places:searchText", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": env.GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": FIELD_MASK
      },
      body: JSON.stringify({
        textQuery: industry + " in " + location,
        maxResultCount
      })
    });

    const data = await upstream.json();
    if (!upstream.ok) {
      return json({
        error: data.error?.message || "Google Places search failed. Check API configuration and billing."
      }, upstream.status >= 400 && upstream.status < 600 ? upstream.status : 502);
    }

    return json({ places: data.places || [] });
  } catch {
    return json({ error: "Could not reach Google Places. Please try again." }, 502);
  }
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