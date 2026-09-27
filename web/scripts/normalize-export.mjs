// Post-build fix-up for the static export (runs automatically after `npm run build`).
//
// Next.js names each route-segment prefetch file `__next.<segment path with "/"
// replaced by ".">.txt`, and the client router requests exactly that name (for
// example `/compare/__next.compare.__PAGE__.txt`). On Windows the segment path
// uses "\" separators, so the replacement misses and the file is written as a
// nested directory instead (`compare/__next.compare/__PAGE__.txt`), which makes
// every prefetch 404. This script flattens those directories into the expected
// file names. On Linux and macOS the export is already flat and nothing changes.
import { readdir, rename, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const outDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "out");

async function filesUnder(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...(await filesUnder(p)));
    else found.push(p);
  }
  return found;
}

async function flatten(segmentDir, parent, prefix) {
  let moved = 0;
  for (const file of await filesUnder(segmentDir)) {
    const rel = path.relative(segmentDir, file).split(path.sep).join(".");
    await rename(file, path.join(parent, `${prefix}.${rel}`));
    moved++;
  }
  await rm(segmentDir, { recursive: true, force: true });
  return moved;
}

async function walk(dir) {
  let moved = 0;
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name === "_next") continue;
    const p = path.join(dir, entry.name);
    moved += entry.name.startsWith("__next.") ? await flatten(p, dir, entry.name) : await walk(p);
  }
  return moved;
}

if (!existsSync(outDir)) {
  console.error(`normalize-export: ${outDir} not found; did next build run with output: "export"?`);
  process.exit(1);
}
const moved = await walk(outDir);
console.log(moved ? `normalize-export: flattened ${moved} segment prefetch file(s) in out/` : "normalize-export: out/ already flat");
