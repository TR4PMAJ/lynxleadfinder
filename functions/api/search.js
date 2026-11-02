const TAGS = {
  "auto detailing":[["shop","car_repair"]],"car detailing":[["shop","car_repair"]],"mechanic":[["shop","car_repair"]],"auto repair":[["shop","car_repair"]],
  "barber":[["shop","hairdresser"]],"barbershop":[["shop","hairdresser"]],"hair salon":[["shop","hairdresser"]],"salon":[["shop","beauty"],["shop","hairdresser"]],
  "restaurant":[["amenity","restaurant"]],"cafe":[["amenity","cafe"]],"coffee shop":[["amenity","cafe"]],
  "plumber":[["craft","plumber"]],"electrician":[["craft","electrician"]],"dentist":[["amenity","dentist"]],"gym":[["leisure","fitness_centre"]],
  "florist":[["shop","florist"]],"bakery":[["shop","bakery"]],"laundromat":[["shop","laundry"]]
};

export async function onRequestPost({ request }) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Send valid JSON." }, 400); }
  const industry = String(body.industry || "").trim().slice(0, 80);
  const location = String(body.location || "").trim().slice(0, 120);
  const limit = Number(body.maxResultCount || 20);
  if (!industry || !location) return json({ error: "Enter a business type and location." }, 400);
  if (!Number.isInteger(limit) || limit < 1 || limit > 20) return json({ error: "Choose between 1 and 20 results." }, 400);
  try {
    const geoUrl = new URL("https://nominatim.openstreetmap.org/search");
    geoUrl.search = new URLSearchParams({ q: location, format: "jsonv2", limit: "1" }).toString();
    const geoRes = await fetch(geoUrl, { headers: { "User-Agent": "LynxLeadFinder/1.0" } });
    if (!geoRes.ok) return json({ error: "Location search is temporarily unavailable. Try again shortly." }, 502);
    const geo = await geoRes.json();
    if (!geo.length) return json({ error: "Location not found. Try a city and state." }, 404);
    const lat = Number(geo[0].lat), lon = Number(geo[0].lon);
    const normalized = industry.toLowerCase();
    const tags = TAGS[normalized] || Object.entries(TAGS).find(([k]) => normalized.includes(k) || k.includes(normalized))?.[1] || [];
    const selectors = tags.length
      ? tags.map(([k,v]) => `nwr(around:12000,${lat},${lon})["${k}"="${v}"];`).join("\n")
      : `nwr(around:12000,${lat},${lon})["name"~"${industry.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}",i];`;
    const q = `[out:json][timeout:25];(${selectors});out center tags;`;
    const overpass = await fetch("https://overpass-api.de/api/interpreter", {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": "LynxLeadFinder/1.0" },
      body: "data=" + encodeURIComponent(q)
    });
    if (!overpass.ok) return json({ error: "OpenStreetMap search is busy. Wait a moment and retry." }, 502);
    const result = await overpass.json();
    const places = (result.elements || []).map(el => {
      const t = el.tags || {}, pLat = el.lat ?? el.center?.lat, pLon = el.lon ?? el.center?.lon;
      const websiteUri = t.website || t["contact:website"] || "";
      const phone = t.phone || t["contact:phone"] || "";
      const address = [t["addr:housenumber"],t["addr:street"],t["addr:city"],t["addr:state"]].filter(Boolean).join(" ");
      const map = Number.isFinite(pLat) && Number.isFinite(pLon) ? "https://www.openstreetmap.org/?mlat="+pLat+"&mlon="+pLon+"#map=18/"+pLat+"/"+pLon : "";
      return { id: el.type+"/"+el.id, name: t.name || t.brand || "", phone, address: address || geo[0].display_name || location, websiteUri, googleMapsUri: map };
    }).filter(p => p.name).sort((a,b) => Number(!a.websiteUri)-Number(!b.websiteUri)).slice(0,limit);
    return json({ places, source: "OpenStreetMap" });
  } catch { return json({ error: "The free map search could not be completed. Try again shortly." }, 502); }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });
}