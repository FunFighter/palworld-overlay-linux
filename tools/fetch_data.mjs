#!/usr/bin/env node
/**
 * Pull Palworld map data from TH.GL's public data-forge CDN and write it into
 * ../data as plain JSON the overlay can load directly.
 *
 * Their node blobs are CBOR (cbor-x, useRecords + pack), and version.json
 * carries the authoritative per-map Leaflet transformation and bounds - which
 * is what lets the player marker land exactly right with no calibration.
 */
import { Encoder } from "cbor-x";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const CDN = "https://cdn.th.gl/palworld";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "data");
// Which maps to pull. Palpagos + World Tree are the two overworlds.
const MAPS = (process.argv[2] || "default,tree").split(",");
const enc = new Encoder({ useRecords: true, pack: true });

const getJson = async (p) => {
  const r = await fetch(CDN + p);
  if (!r.ok) throw new Error(`${p} -> HTTP ${r.status}`);
  return r.json();
};
const getBuf = async (p) => {
  const r = await fetch(CDN + p);
  if (!r.ok) throw new Error(`${p} -> HTTP ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
};

mkdirSync(OUT, { recursive: true });

console.log("version.json ...");
const version = await getJson("/version.json");
const { tiles, filters } = version.data;
const nodePaths = version.more.nodes;

console.log("dicts/en.json ...");
const dict = await getJson("/dicts/en.json");
// Some entries are "@ref" aliases; fall back to a readable id.
const label = (id) => {
  const v = dict[id];
  if (typeof v === "string" && v && !v.startsWith("@")) return v;
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

// ---- per-map tile config + node spawns -----------------------------------
const maps = {};
for (const m of MAPS) {
  if (!tiles[m]) { console.warn(`  ! no tile config for "${m}", skipping`); continue; }
  const t = tiles[m];
  console.log(`nodes/${m} ...`);
  const groups = enc.decode(await getBuf(nodePaths[m]));

  const types = {};
  for (const g of groups) {
    if (!g.spawns?.length) continue;
    // p is [x, y, z] in raw game coordinates - the same frame the dedicated
    // server's REST API reports location_x / location_y in.
    types[g.type] = g.spawns
      .filter((s) => Array.isArray(s.p) && s.p.length >= 2)
      .map((s) => [
        Math.round(s.p[0] * 10) / 10,
        Math.round(s.p[1] * 10) / 10,
        Math.round((s.p[2] ?? 0) * 10) / 10,
      ]);
  }
  const count = Object.values(types).reduce((a, v) => a + v.length, 0);

  maps[m] = {
    id: m,
    label: label(m),
    tileUrl: CDN + t.url + "?v=1",
    tileSize: t.options.tileSize,
    minNativeZoom: t.options.minNativeZoom,
    maxNativeZoom: t.options.maxNativeZoom,
    minZoom: t.minZoom,
    maxZoom: t.maxZoom,
    bounds: t.options.bounds,          // [[latMin,lngMin],[latMax,lngMax]] raw coords
    transformation: t.transformation,  // [a, b, c, d] -> Leaflet L.Transformation
  };
  writeFileSync(join(OUT, `nodes.${m}.json`), JSON.stringify({ map: m, types }));
  console.log(`  ${m}: ${Object.keys(types).length} types, ${count} spawns`);
}
writeFileSync(join(OUT, "maps.json"), JSON.stringify(maps, null, 1));

// ---- filter groups, labelled, restricted to types we actually have -------
const present = new Set();
for (const m of Object.keys(maps)) {
  const n = JSON.parse(
    (await import("node:fs")).readFileSync(join(OUT, `nodes.${m}.json`), "utf8"));
  Object.keys(n.types).forEach((t) => present.add(t));
}
const outFilters = [];
for (const f of filters) {
  const values = (f.values || [])
    .filter((v) => present.has(v.id))
    .map((v) => ({ id: v.id, label: label(v.id), icon: v.icon, size: v.size ?? 1 }));
  if (values.length) outFilters.push({ group: f.group, label: label(f.group), values });
}
// anything present but not in a filter group still deserves a home
const claimed = new Set(outFilters.flatMap((g) => g.values.map((v) => v.id)));
const rest = [...present].filter((t) => !claimed.has(t)).sort();
if (rest.length) {
  outFilters.push({
    group: "other", label: "Other",
    values: rest.map((id) => ({ id, label: label(id), size: 1 })),
  });
}
writeFileSync(join(OUT, "filters.json"), JSON.stringify(outFilters));
console.log(`filters: ${outFilters.length} groups, ${claimed.size + rest.length} types`);

console.log("icons sprite ...");
writeFileSync(join(OUT, "icons.webp"), await getBuf(version.more.icons));

writeFileSync(join(OUT, "meta.json"), JSON.stringify({
  forgeId: version.id, createdAt: version.createdAt,
  fetchedMaps: Object.keys(maps),
}, null, 1));
console.log("done ->", OUT);
