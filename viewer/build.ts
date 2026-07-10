import { cp, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";

const outDir = "dist";

if (existsSync(outDir)) {
  await rm(outDir, { recursive: true });
}
await mkdir(outDir, { recursive: true });

const result = await Bun.build({
  entrypoints: ["./src/main.ts"],
  outdir: outDir,
  target: "browser",
  minify: true,
  sourcemap: "linked",
});

if (!result.success) {
  for (const msg of result.logs) console.error(msg);
  process.exit(1);
}

const html = await Bun.file("index.html").text();
await Bun.write(`${outDir}/index.html`, html);

const cesiumSrc = "node_modules/cesium/Build/Cesium";
const cesiumDst = `${outDir}/cesium`;
if (!existsSync(cesiumSrc)) {
  console.error(
    `Missing ${cesiumSrc}. Run 'bun install' first so the Cesium runtime is available.`,
  );
  process.exit(1);
}
await cp(cesiumSrc, cesiumDst, { recursive: true });

console.log(`Built to ${outDir}/`);
