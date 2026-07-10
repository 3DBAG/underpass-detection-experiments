// Cesium is loaded as a global via /cesium/Cesium.js in index.html.
// We only use its types here — it is not bundled.
declare const Cesium: typeof import("cesium");
type Color = import("cesium").Color;
type Cesium3DTileset = import("cesium").Cesium3DTileset;
type Cesium3DTileFeature = import("cesium").Cesium3DTileFeature;
type Cesium3DTileContent = {
  featuresLength: number;
  getFeature(index: number): Cesium3DTileFeature;
};
type Cesium3DTile = {
  content: Cesium3DTileContent;
};
type SelectedFeatureState = {
  featureId: number;
  feature?: Cesium3DTileFeature;
  originalColor: Color;
};
type LoadedTileset = {
  url: string;
  label: string;
  tileset: Cesium3DTileset;
};
type AvailableTileset = {
  url: string;
  label: string;
};
type TilesetManifestEntry = string | {
  url?: unknown;
  href?: unknown;
  path?: unknown;
  label?: unknown;
  name?: unknown;
};

const urlInput = document.getElementById("url-input") as HTMLInputElement;
const tokenInput = document.getElementById("token-input") as HTMLInputElement;
const terrainSelect = document.getElementById("terrain-select") as HTMLSelectElement;
const underpassColorToggle = document.getElementById("underpass-color-toggle") as HTMLInputElement;
const underpassLegend = document.getElementById("underpass-legend") as HTMLDivElement;
const tilesetLayerList = document.getElementById("tileset-layer-list") as HTMLDivElement;
const loadBtn = document.getElementById("load-btn") as HTMLButtonElement;
const zoomBtn = document.getElementById("zoom-btn") as HTMLButtonElement;
const inspectContent = document.getElementById("inspect-content") as HTMLDivElement;
const searchParams = new URLSearchParams(window.location.search);
const AMSTERDAM_CENTER = {
  longitude: 4.91406,
  latitude: 52.377995,
  height: 1200,
};

const viewer = new Cesium.Viewer("cesiumContainer", {
  animation: false,
  timeline: false,
  geocoder: false,
  baseLayerPicker: false,
  homeButton: false,
  sceneModePicker: false,
  navigationHelpButton: false,
  fullscreenButton: false,
  infoBox: false,
  selectionIndicator: false,
  baseLayer: new Cesium.ImageryLayer(
    new Cesium.OpenStreetMapImageryProvider({
      url: "https://tile.openstreetmap.org/",
    })
  ),
  shouldAnimate: false,
  requestRenderMode: true,
  maximumRenderTimeChange: Infinity,
});

const TILESET_MANIFEST_URL = "data/tilesets.json";
const DEFAULT_TOKEN = "";
const DEFAULT_UNDERPASS_COLORS_ENABLED = true;
const PDOK_TERRAIN_URL = "https://roofer-online.nl/pdok-qm-ahn6/";
const TERRAIN_NONE = "none";
const TERRAIN_CESIUM = "cesium";
const TERRAIN_PDOK = "pdok";
type TerrainMode = typeof TERRAIN_NONE | typeof TERRAIN_CESIUM | typeof TERRAIN_PDOK;
const DEFAULT_TERRAIN_MODE: TerrainMode = TERRAIN_PDOK;
const SELECTION_HIGHLIGHT_COLOR = new Cesium.Color(0.25, 0.78, 1.0, 0.9);
const DEFAULT_FEATURE_COLOR = Cesium.Color.WHITE;
const UNDERPASS_STREETLIDAR_SUCCESS_COLOR = Cesium.Color.fromCssColorString("#1f7a3a");
const UNDERPASS_ASSUMED_SUCCESS_COLOR = Cesium.Color.fromCssColorString("#8fd694");
const UNDERPASS_FAILED_COLOR = Cesium.Color.fromCssColorString("#f08f8f");

let currentTilesets: LoadedTileset[] = [];
let availableTilesets: AvailableTileset[] = [];
let terrainRequestId = 0;
let selectedFeatureState: SelectedFeatureState | undefined;

function normalizeTilesetUrl(rawUrl: string) {
  const trimmed = rawUrl.trim();
  if (!trimmed) return trimmed;

  try {
    const parsed = new URL(trimmed);
    const isLoopbackHost = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
    const looksLikeFilesystemPath =
      parsed.pathname.startsWith("/home/") ||
      parsed.pathname.startsWith("/Users/") ||
      parsed.pathname.startsWith("/private/");

    if (isLoopbackHost && looksLikeFilesystemPath) {
      const parts = parsed.pathname.split("/").filter(Boolean);
      const tail = parts[parts.length - 1];
      if (tail) {
        parsed.pathname = `/${tail}`;
        return parsed.toString();
      }
    }

    return parsed.toString();
  } catch {
    return trimmed;
  }
}

function parseTilesetUrls(rawUrls: string) {
  return rawUrls
    .split(/[\n,]+/)
    .map(normalizeTilesetUrl)
    .filter(Boolean);
}

function formatTilesetUrls(urls: string[]) {
  return urls.join(", ");
}

function normalizeManifestTilesetUrl(rawUrl: string) {
  const normalized = normalizeTilesetUrl(rawUrl);
  if (
    !normalized ||
    normalized.startsWith("http://") ||
    normalized.startsWith("https://") ||
    normalized.startsWith("/") ||
    normalized.startsWith("data/") ||
    normalized.startsWith("./data/")
  ) {
    return normalized;
  }

  return `data/${normalized.replace(/^\.\//, "")}`;
}

function getCurrentLabels() {
  return currentTilesets.map(({ label }) => label);
}

function deriveTilesetLabel(url: string, index: number) {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    const fileName = parts.at(-1);
    const parentName = parts.at(-2);
    const label = fileName === "tileset.json" ? parentName : fileName;
    return label ?? `Tileset ${index + 1}`;
  } catch {
    const parts = url.split("/").filter(Boolean);
    const fileName = parts.at(-1);
    const parentName = parts.at(-2);
    const label = fileName === "tileset.json" ? parentName : fileName;
    return label ?? `Tileset ${index + 1}`;
  }
}

function parseManifestTilesets(rawManifest: unknown): AvailableTileset[] {
  const rawEntries = Array.isArray(rawManifest)
    ? rawManifest
    : rawManifest && typeof rawManifest === "object" && Array.isArray((rawManifest as { tilesets?: unknown }).tilesets)
      ? (rawManifest as { tilesets: TilesetManifestEntry[] }).tilesets
      : [];

  const entries: AvailableTileset[] = [];
  for (const [index, rawEntry] of rawEntries.entries()) {
    const rawUrl = typeof rawEntry === "string"
      ? rawEntry
      : rawEntry && typeof rawEntry === "object"
        ? (rawEntry.url ?? rawEntry.href ?? rawEntry.path)
        : undefined;
    if (typeof rawUrl !== "string" || !rawUrl.trim()) {
      continue;
    }

    const url = normalizeManifestTilesetUrl(rawUrl);
    if (!url) {
      continue;
    }

    const rawLabel = typeof rawEntry === "object" && rawEntry
      ? rawEntry.label ?? rawEntry.name
      : undefined;
    const label = typeof rawLabel === "string" && rawLabel.trim()
      ? rawLabel.trim()
      : deriveTilesetLabel(url, index);

    entries.push({ url, label });
  }

  return entries;
}

async function fetchManifestTilesets() {
  try {
    const response = await fetch(TILESET_MANIFEST_URL, { cache: "no-store" });
    if (!response.ok) {
      if (response.status !== 404) {
        console.warn(`Tileset manifest request failed: ${response.status} ${response.statusText}`);
      }
      return [];
    }

    return parseManifestTilesets(await response.json());
  } catch (err: unknown) {
    console.warn("Tileset manifest could not be loaded.", err);
    return [];
  }
}

function dedupeAvailableTilesets(entries: AvailableTileset[]) {
  const seen = new Set<string>();
  const deduped: AvailableTileset[] = [];

  for (const entry of entries) {
    if (seen.has(entry.url)) {
      continue;
    }

    seen.add(entry.url);
    deduped.push(entry);
  }

  return deduped;
}

function setAvailableTilesets(entries: AvailableTileset[]) {
  availableTilesets = dedupeAvailableTilesets(entries);
  renderTilesetSwitcher();
}

function findAvailableTileset(url: string) {
  return availableTilesets.find((entry) => entry.url === url);
}

function loadAvailableTileset(entry: AvailableTileset, options: { zoomToTileset?: boolean } = {}) {
  urlInput.value = entry.url;
  return loadTilesets([entry.url], {
    ...options,
    labels: [entry.label],
  });
}

function formatAngle(value: number) {
  return `${value.toFixed(6)} deg`;
}

function formatHeight(value: number) {
  return `${value.toFixed(2)} m`;
}

function appendLine(container: HTMLElement, label: string, value: string) {
  const row = document.createElement("div");
  const labelEl = document.createElement("span");
  labelEl.className = "label";
  labelEl.textContent = label;
  const valueEl = document.createElement("span");
  valueEl.textContent = value;
  row.append(labelEl, valueEl);
  container.appendChild(row);
}

function cloneColor(color: Color, result?: Color) {
  return Cesium.Color.clone(color, result ?? new Cesium.Color())!;
}

function formatFeaturePropertyValue(value: unknown) {
  if (value === null) return "null";
  if (value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function getFeaturePropertyIds(feature: Cesium3DTileFeature) {
  const withPropertyIds = feature as Cesium3DTileFeature & {
    getPropertyIds?: (results?: string[]) => string[];
  };
  if (typeof withPropertyIds.getPropertyIds !== "function") {
    return [];
  }

  return withPropertyIds.getPropertyIds([]);
}

function renderFeatureProperties(container: HTMLElement, feature: Cesium3DTileFeature) {
  const propertyIds = getFeaturePropertyIds(feature).sort((a, b) => a.localeCompare(b));
  if (propertyIds.length === 0) {
    container.textContent = "Picked feature has no properties.";
    return;
  }

  const heading = document.createElement("div");
  heading.className = "label";
  heading.textContent = "Attributes";

  const table = document.createElement("table");
  const body = document.createElement("tbody");
  for (const propertyId of propertyIds) {
    const row = document.createElement("tr");
    const key = document.createElement("th");
    const value = document.createElement("td");
    key.scope = "row";
    key.textContent = propertyId;
    value.textContent = formatFeaturePropertyValue(feature.getProperty(propertyId));
    row.append(key, value);
    body.appendChild(row);
  }

  table.appendChild(body);
  container.append(heading, table);
}

function getTileFeatureById(tile: Cesium3DTile, featureId: number) {
  const { content } = tile;
  for (let index = 0; index < content.featuresLength; index += 1) {
    const feature = content.getFeature(index);
    if (feature.featureId === featureId) {
      return feature;
    }
  }

  return undefined;
}

function getUnderpassColor(feature: Cesium3DTileFeature) {
  if (!isUnderpassColorsEnabled()) {
    return DEFAULT_FEATURE_COLOR;
  }

  const success = feature.getProperty("add_underpass_success");
  if (success === null || success === undefined) {
    return DEFAULT_FEATURE_COLOR;
  }

  if (success === 1 || success === "1" || success === true) {
    const source = feature.getProperty("h_underpass_source");
    return source === "streetlidar" ? UNDERPASS_STREETLIDAR_SUCCESS_COLOR : UNDERPASS_ASSUMED_SUCCESS_COLOR;
  }

  return UNDERPASS_FAILED_COLOR;
}

function applyUnderpassStyleToTile(tile: Cesium3DTile) {
  const { content } = tile;
  const selectedFeature = selectedFeatureState?.feature;
  for (let index = 0; index < content.featuresLength; index += 1) {
    const feature = content.getFeature(index);
    if (feature === selectedFeature) {
      continue;
    }

    feature.color = cloneColor(getUnderpassColor(feature));
  }
}

function clearSelection() {
  if (!selectedFeatureState) {
    return;
  }

  const { feature, originalColor } = selectedFeatureState;
  if (feature) {
    feature.color = cloneColor(originalColor);
  }

  selectedFeatureState = undefined;
  viewer.scene.requestRender();
}

function selectFeature(feature: Cesium3DTileFeature) {
  if (selectedFeatureState?.feature === feature) {
    return;
  }

  clearSelection();
  selectedFeatureState = {
    featureId: feature.featureId,
    feature,
    originalColor: cloneColor(feature.color),
  };
  feature.color = cloneColor(SELECTION_HIGHLIGHT_COLOR);
  viewer.scene.requestRender();
}

function restoreSelectionOnTileUnload(tile: Cesium3DTile) {
  const state = selectedFeatureState;
  if (!state || !state.feature) {
    return;
  }

  const feature = getTileFeatureById(tile, state.featureId);
  if (!feature || feature !== state.feature) {
    return;
  }

  feature.color = cloneColor(state.originalColor);
  state.feature = undefined;
  viewer.scene.requestRender();
}

function reapplySelectionOnTileVisible(tile: Cesium3DTile) {
  const state = selectedFeatureState;
  if (!state || state.feature) {
    return;
  }

  const feature = getTileFeatureById(tile, state.featureId);
  if (!feature) {
    return;
  }

  state.feature = feature;
  feature.color = cloneColor(SELECTION_HIGHLIGHT_COLOR);
  viewer.scene.requestRender();
}

function handleTileVisible(tile: Cesium3DTile) {
  applyUnderpassStyleToTile(tile);
  reapplySelectionOnTileVisible(tile);
}

function renderInspection(
  cartesian: import("cesium").Cartesian3 | undefined,
  pickedFeature: Cesium3DTileFeature | undefined
) {
  inspectContent.replaceChildren();

  if (!cartesian) {
    inspectContent.textContent = "No world position was resolved for that click.";
    inspectContent.className = "hint";
    return;
  }

  inspectContent.className = "";

  const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
  appendLine(inspectContent, "Longitude", formatAngle(Cesium.Math.toDegrees(cartographic.longitude)));
  appendLine(inspectContent, "Latitude", formatAngle(Cesium.Math.toDegrees(cartographic.latitude)));
  appendLine(inspectContent, "Height", formatHeight(cartographic.height));

  const featureSection = document.createElement("div");
  featureSection.className = "section";
  inspectContent.appendChild(featureSection);

  if (!pickedFeature) {
    featureSection.textContent = "No 3D Tiles feature picked.";
    return;
  }

  renderFeatureProperties(featureSection, pickedFeature);
}

function getPickedPosition(windowPosition: import("cesium").Cartesian2) {
  if (viewer.scene.pickPositionSupported) {
    const pickedPosition = viewer.scene.pickPosition(windowPosition);
    if (Cesium.defined(pickedPosition)) return pickedPosition;
  }

  return viewer.camera.pickEllipsoid(windowPosition, viewer.scene.globe.ellipsoid);
}

function setupInspector() {
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((event: { position: import("cesium").Cartesian2 }) => {
    const picked = viewer.scene.pick(event.position);
    const pickedFeature = picked instanceof Cesium.Cesium3DTileFeature ? picked : undefined;
    if (pickedFeature) {
      selectFeature(pickedFeature);
    } else {
      clearSelection();
    }
    const cartesian = getPickedPosition(event.position);
    renderInspection(cartesian, pickedFeature);
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

function attachTilesetSelectionLifecycle(tileset: Cesium3DTileset) {
  tileset.tileUnload.addEventListener(restoreSelectionOnTileUnload);
  tileset.tileVisible.addEventListener(handleTileVisible);
}

function detachTilesetSelectionLifecycle(tileset: Cesium3DTileset) {
  tileset.tileUnload.removeEventListener(restoreSelectionOnTileUnload);
  tileset.tileVisible.removeEventListener(handleTileVisible);
}

function applyToken() {
  const t = tokenInput.value.trim();
  Cesium.Ion.defaultAccessToken = t;
}

function createEllipsoidTerrain() {
  return new Cesium.Terrain(Promise.resolve(new Cesium.EllipsoidTerrainProvider()));
}

function createPdokTerrain() {
  return new Cesium.Terrain(Cesium.CesiumTerrainProvider.fromUrl(PDOK_TERRAIN_URL, {
    requestVertexNormals: true,
  }));
}

function getTerrainMode(): TerrainMode {
  const value = terrainSelect.value;
  if (value === TERRAIN_CESIUM || value === TERRAIN_PDOK) return value;
  return TERRAIN_NONE;
}

function syncUnderpassLegend() {
  underpassLegend.hidden = !isUnderpassColorsEnabled();
}

function isUnderpassColorsEnabled() {
  return true;
}

function syncUnderpassStyle() {
  syncUnderpassLegend();
  if (currentTilesets.length === 0) return;

  clearSelection();
  for (const { tileset } of currentTilesets) {
    tileset.style = undefined;
  }
  viewer.scene.requestRender();
}

function syncTerrain() {
  const requestId = ++terrainRequestId;
  const token = tokenInput.value.trim();
  const mode = getTerrainMode();
  const useCesiumWorldTerrain = mode === TERRAIN_CESIUM && Boolean(token);
  const usePdokTerrain = mode === TERRAIN_PDOK;
  const terrain = useCesiumWorldTerrain
    ? Cesium.Terrain.fromWorldTerrain({
        requestVertexNormals: true,
        requestWaterMask: true,
      })
    : usePdokTerrain
      ? createPdokTerrain()
      : createEllipsoidTerrain();

  terrain.readyEvent.addEventListener(() => {
    if (requestId !== terrainRequestId) return;

    viewer.scene.globe.depthTestAgainstTerrain = mode !== TERRAIN_NONE;
    viewer.scene.requestRender();
  });

  terrain.errorEvent.addEventListener((error) => {
    if (requestId !== terrainRequestId) return;

    console.error(error);
    alert(`Failed to configure terrain: ${error}`);
  });

  viewer.scene.setTerrain(terrain);
}

function updateQuery(
  urls: string[],
  token: string,
  terrainMode: TerrainMode,
  underpassColorsEnabled: boolean,
  labels = getCurrentLabels(),
) {
  const next = new URL(window.location.href);
  next.searchParams.delete("tileset");
  next.searchParams.delete("tilesetVisible");
  next.searchParams.delete("tilesetLabel");
  for (const url of urls) {
    next.searchParams.append("tileset", url);
  }
  for (const label of labels) {
    next.searchParams.append("tilesetLabel", label);
  }
  if (token) {
    next.searchParams.set("token", token);
  } else {
    next.searchParams.delete("token");
  }
  if (terrainMode !== TERRAIN_NONE) {
    next.searchParams.set("terrain", terrainMode);
  } else {
    next.searchParams.delete("terrain");
  }
  if (underpassColorsEnabled) {
    next.searchParams.set("underpassColors", "1");
  } else {
    next.searchParams.delete("underpassColors");
  }
  window.history.replaceState({}, "", next);
}

function setInitialMinimalView() {
  viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(
      AMSTERDAM_CENTER.longitude,
      AMSTERDAM_CENTER.latitude,
      AMSTERDAM_CENTER.height,
    ),
  });
}

function removeCurrentTilesets() {
  clearSelection();
  for (const { tileset } of currentTilesets) {
    detachTilesetSelectionLifecycle(tileset);
    viewer.scene.primitives.remove(tileset);
  }
  currentTilesets = [];
  renderTilesetSwitcher();
}

async function zoomToCurrentTilesets() {
  const visibleTilesets = currentTilesets
    .filter(({ tileset }) => tileset.show !== false)
    .map(({ tileset }) => tileset);
  if (visibleTilesets.length === 0) return;

  try {
    if (visibleTilesets.length === 1) {
      await viewer.zoomTo(visibleTilesets[0]);
      return;
    }

    const boundingSphere = Cesium.BoundingSphere.fromBoundingSpheres(
      visibleTilesets.map((tileset) => tileset.boundingSphere),
    );
    viewer.camera.flyToBoundingSphere(boundingSphere, { duration: 0 });
    viewer.scene.requestRender();
  } catch (err: unknown) {
    console.error(err);
    const msg = err instanceof Error ? err.message : String(err);
    alert(`Failed to zoom to tileset: ${msg}`);
  }
}

function renderTilesetSwitcher() {
  tilesetLayerList.replaceChildren();

  if (availableTilesets.length === 0) {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "No tilesets available.";
    tilesetLayerList.appendChild(hint);
    return;
  }

  const select = document.createElement("select");
  select.ariaLabel = "Tileset";
  const currentUrl = currentTilesets[0]?.url ?? availableTilesets[0]?.url ?? "";

  for (const entry of availableTilesets) {
    const option = document.createElement("option");
    option.value = entry.url;
    option.textContent = entry.label;
    option.title = entry.url;
    select.appendChild(option);
  }

  select.value = currentUrl;
  select.addEventListener("change", () => {
    const entry = findAvailableTileset(select.value);
    if (!entry) return;

    loadAvailableTileset(entry, { zoomToTileset: false });
  });

  tilesetLayerList.appendChild(select);
}

async function loadTilesets(
  urls: string[],
  options: { zoomToTileset?: boolean; labels?: string[] } = {},
) {
  const zoomToTileset = options.zoomToTileset ?? true;
  applyToken();
  syncTerrain();

  try {
    const tilesets = await Promise.all(
      urls.map((url) =>
        Cesium.Cesium3DTileset.fromUrl(url, {
          showCreditsOnScreen: true,
          debugShowBoundingVolume: false,
        }),
      ),
    );

    removeCurrentTilesets();
    for (const tileset of tilesets) {
      tileset.show = true;
      viewer.scene.primitives.add(tileset);
      attachTilesetSelectionLifecycle(tileset);
    }
    currentTilesets = tilesets.map((tileset, index) => ({
      url: urls[index],
      label: options.labels?.[index] ?? deriveTilesetLabel(urls[index], index),
      tileset,
    }));
    renderTilesetSwitcher();
    syncUnderpassStyle();
    updateQuery(urls, tokenInput.value.trim(), getTerrainMode(), isUnderpassColorsEnabled());
    if (zoomToTileset) {
      await zoomToCurrentTilesets();
    }
  } catch (err: unknown) {
    console.error(err);
    const msg = err instanceof Error ? err.message : String(err);
    alert(`Failed to load tileset: ${msg}`);
  }
}

async function zoomToCurrentTileset() {
  await zoomToCurrentTilesets();
}

function triggerLoad() {
  const urls = parseTilesetUrls(urlInput.value);
  if (urls.length > 0) {
    const entry = findAvailableTileset(urls[0]);
    if (!entry) {
      const currentUrl = currentTilesets[0]?.url ?? "";
      urlInput.value = currentUrl;
      alert(`Tileset is not listed in ${TILESET_MANIFEST_URL}.`);
      return;
    }

    loadAvailableTileset(entry);
  }
}

loadBtn.addEventListener("click", () => {
  triggerLoad();
});
zoomBtn.addEventListener("click", () => {
  zoomToCurrentTileset();
});
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    triggerLoad();
  }
});

tokenInput.addEventListener("change", () => {
  applyToken();
  syncTerrain();
  updateQuery(parseTilesetUrls(urlInput.value), tokenInput.value.trim(), getTerrainMode(), isUnderpassColorsEnabled());
});

terrainSelect.addEventListener("change", () => {
  syncTerrain();
  updateQuery(parseTilesetUrls(urlInput.value), tokenInput.value.trim(), getTerrainMode(), isUnderpassColorsEnabled());
});

underpassColorToggle.addEventListener("change", () => {
  syncUnderpassStyle();
  updateQuery(parseTilesetUrls(urlInput.value), tokenInput.value.trim(), getTerrainMode(), isUnderpassColorsEnabled());
});

const initialTilesets = searchParams.getAll("tileset");
const initialTilesetUrls = initialTilesets.flatMap(parseTilesetUrls);
const initialToken = searchParams.get("token") ?? DEFAULT_TOKEN;
const initialTerrainParam = searchParams.get("terrain");
const initialTerrainMode: TerrainMode =
  initialTerrainParam === TERRAIN_CESIUM || initialTerrainParam === "1"
    ? TERRAIN_CESIUM
    : initialTerrainParam === TERRAIN_PDOK
      ? TERRAIN_PDOK
      : DEFAULT_TERRAIN_MODE;
const initialUnderpassColorsEnabled =
  searchParams.get("underpassColors") === "1" || DEFAULT_UNDERPASS_COLORS_ENABLED;

urlInput.value = formatTilesetUrls(initialTilesetUrls);
tokenInput.value = initialToken;
terrainSelect.value = initialTerrainMode;
underpassColorToggle.checked = initialUnderpassColorsEnabled;
syncUnderpassLegend();
setupInspector();

fetchManifestTilesets().then((manifestTilesets) => {
  setAvailableTilesets(manifestTilesets);

  const initialUrl = initialTilesetUrls[0];
  const initialEntry = initialUrl ? findAvailableTileset(initialUrl) : undefined;
  const selectedEntry = initialEntry ?? availableTilesets.at(-1);

  if (selectedEntry) {
    return loadAvailableTileset(selectedEntry, {
      zoomToTileset: false,
    });
  }

  urlInput.value = "";
  return Promise.resolve();
}).then(() => {
  setInitialMinimalView();
});
