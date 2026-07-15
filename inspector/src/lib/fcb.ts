import initFcb, {
  HttpFcbReader,
  WasmAttrQuery,
} from "@/vendor/fcb-wasm/fcb_wasm.js";

export interface CityJsonTransform {
  scale: [number, number, number];
  translate: [number, number, number];
}

export interface CityObjectGeometry {
  type: string;
  lod?: string | number;
  boundaries: unknown;
  semantics?: {
    surfaces?: Array<{ type?: string; [key: string]: unknown }>;
    values?: unknown;
  };
}

export interface CityObject {
  type: string;
  attributes?: Record<string, unknown>;
  children?: string[];
  geographicalExtent?: [number, number, number, number, number, number];
  geometry?: CityObjectGeometry[];
}

export interface CityJsonFeature {
  type: "CityJSONFeature";
  id?: string;
  CityObjects: Record<string, CityObject>;
  vertices: Array<[number, number, number]>;
}

export interface CityJsonMetadata {
  transform?: CityJsonTransform;
  [key: string]: unknown;
}

export interface BuildingRecord {
  id: string;
  feature: CityJsonFeature;
  metadata: CityJsonMetadata;
}

// The wasm-bindgen constructor is async at runtime, despite its generated declaration.
type AsyncReaderConstructor = new (url: string) => Promise<HttpFcbReader>;
const AsyncHttpFcbReader = HttpFcbReader as unknown as AsyncReaderConstructor;

let wasmReady: Promise<unknown> | undefined;

function ensureWasm() {
  wasmReady ??= initFcb();
  return wasmReady;
}

export function normalizeBuildingId(value: string) {
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) {
    return `NL.IMBAG.Pand.${trimmed}`;
  }
  return trimmed;
}

export async function loadBuildingById(url: string, rawId: string): Promise<BuildingRecord> {
  const id = normalizeBuildingId(rawId);
  if (!id) {
    throw new Error("A building ID is required.");
  }

  await ensureWasm();
  const reader = await new AsyncHttpFcbReader(url);
  const metadata = reader.cityjson() as CityJsonMetadata;
  const query = new WasmAttrQuery([["identificatie", "Eq", id]]);
  try {
    // This generated method consumes the reader handle, so only the iterator needs freeing.
    const iterator = await reader.select_attr_query_paged(query, 1, 0);
    try {
      const feature = (await iterator.next()) as CityJsonFeature | undefined;
      if (!feature) {
        throw new Error(`No building found for ${id}.`);
      }
      return { id, feature, metadata };
    } finally {
      iterator.free();
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/index|attribute/i.test(message)) {
      throw new Error(
        "The FlatCityBuf file does not contain an identificatie attribute index.",
      );
    }
    throw error;
  } finally {
    query.free();
  }
}

export function getBuildingObject(record: BuildingRecord) {
  const direct = record.feature.CityObjects[record.id];
  if (direct) return direct;

  return Object.values(record.feature.CityObjects).find(
    (object) => object.attributes?.identificatie === record.id,
  );
}
