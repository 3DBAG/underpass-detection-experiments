import earcut from "earcut";
import {
  Box3,
  BufferGeometry,
  DoubleSide,
  EdgesGeometry,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshStandardMaterial,
  Vector3,
} from "three";
import type {
  BuildingRecord,
  CityJsonTransform,
  CityObjectGeometry,
} from "@/lib/fcb";

type VertexIndex = number;
type Ring = VertexIndex[];
type Surface = Ring[];

interface SurfaceRecord {
  surface: Surface;
  semantic: string;
  semanticSurface: SemanticSurfacePick;
}

interface SemanticMeshData {
  semantic: string;
  underpassId?: string;
  positions: number[];
  surfaceByTriangle: SemanticSurfacePick[];
}

export interface SemanticSurfacePick {
  type: string;
  cityObjectId: string;
  attributes: Record<string, unknown>;
}

export const OUTER_CEILING_SURFACE = "OuterCeilingSurface";
export const UNDERPASS_CANDIDATE_PEAKS_ATTRIBUTE = "underpass_candidate_peaks";

export interface UnderpassSurface {
  id: string;
  cityObjectId: string;
  attributes: Record<string, unknown>;
  hasCandidatePeaks: boolean;
}

export function underpassIdFromAttributes(attributes?: Record<string, unknown>) {
  const value = attributes?.underpass_id;
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : undefined;
}

export function underpassesForRecord(record: BuildingRecord): UnderpassSurface[] {
  const underpasses = new Map<string, UnderpassSurface>();
  Object.entries(record.feature.CityObjects).forEach(([cityObjectId, object]) => {
    object.geometry?.forEach((geometry) => {
      geometry.semantics?.surfaces?.forEach((surface) => {
        if (surface.type !== OUTER_CEILING_SURFACE) return;
        const attributes = { ...surface };
        delete attributes.type;
        const id = underpassIdFromAttributes(attributes);
        if (!id) return;
        underpasses.set(id, {
          id,
          cityObjectId,
          attributes,
          hasCandidatePeaks: Object.prototype.hasOwnProperty.call(
            attributes,
            UNDERPASS_CANDIDATE_PEAKS_ATTRIBUTE,
          ),
        });
      });
    });
  });
  return [...underpasses.values()].sort((a, b) =>
    a.id.localeCompare(b.id, undefined, { numeric: true }),
  );
}

export interface BuildingScene {
  group: Group;
  origin: Vector3;
  bounds: Box3;
  localBounds: Box3;
  lod: string;
  surfaceCount: number;
  vertexCount: number;
}

const SEMANTIC_COLORS: Record<string, number> = {
  RoofSurface: 0xd9654f,
  WallSurface: 0xcbd1cc,
  GroundSurface: 0x66736b,
  ClosureSurface: 0xa4aaa6,
  [OUTER_CEILING_SURFACE]: 0xf06292,
  OuterFloorSurface: 0x747d76,
  default: 0xbfc7c1,
};

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function semanticSurface(
  geometry: CityObjectGeometry,
  value: unknown,
  cityObjectId: string,
): SemanticSurfacePick {
  const surface = typeof value === "number"
    ? geometry.semantics?.surfaces?.[value]
    : undefined;
  const { type = "default", ...attributes } = surface ?? {};
  return { type, cityObjectId, attributes };
}

function surfaceRecord(
  geometry: CityObjectGeometry,
  surface: unknown,
  semanticValue: unknown,
  cityObjectId: string,
): SurfaceRecord {
  const semantic = semanticSurface(geometry, semanticValue, cityObjectId);
  return {
    surface: surface as Surface,
    semantic: semantic.type,
    semanticSurface: semantic,
  };
}

function collectSurfaces(
  geometry: CityObjectGeometry,
  cityObjectId: string,
): SurfaceRecord[] {
  const boundaries = asArray(geometry.boundaries);
  const values = geometry.semantics?.values;

  if (geometry.type === "MultiSurface" || geometry.type === "CompositeSurface") {
    const semanticValues = asArray(values);
    return boundaries.map((surface, index) =>
      surfaceRecord(geometry, surface, semanticValues[index], cityObjectId),
    );
  }

  if (geometry.type === "Solid") {
    const semanticShells = asArray(values);
    return boundaries.flatMap((shell, shellIndex) => {
      const shellValues = asArray(semanticShells[shellIndex]);
      return asArray(shell).map((surface, surfaceIndex) =>
        surfaceRecord(geometry, surface, shellValues[surfaceIndex], cityObjectId),
      );
    });
  }

  if (geometry.type === "MultiSolid" || geometry.type === "CompositeSolid") {
    const semanticSolids = asArray(values);
    return boundaries.flatMap((solid, solidIndex) => {
      const solidValues = asArray(semanticSolids[solidIndex]);
      return asArray(solid).flatMap((shell, shellIndex) => {
        const shellValues = asArray(solidValues[shellIndex]);
        return asArray(shell).map((surface, surfaceIndex) =>
          surfaceRecord(geometry, surface, shellValues[surfaceIndex], cityObjectId),
        );
      });
    });
  }

  return [];
}

function transformedVertex(
  vertex: [number, number, number],
  transform: CityJsonTransform,
) {
  return new Vector3(
    vertex[0] * transform.scale[0] + transform.translate[0],
    vertex[1] * transform.scale[1] + transform.translate[1],
    vertex[2] * transform.scale[2] + transform.translate[2],
  );
}

function withoutClosingVertex(ring: Vector3[]) {
  if (ring.length > 2 && ring[0].distanceToSquared(ring[ring.length - 1]) < 1e-12) {
    return ring.slice(0, -1);
  }
  return ring;
}

function projectionAxis(ring: Vector3[]) {
  const normal = new Vector3();
  for (let index = 0; index < ring.length; index += 1) {
    const current = ring[index];
    const next = ring[(index + 1) % ring.length];
    normal.x += (current.y - next.y) * (current.z + next.z);
    normal.y += (current.z - next.z) * (current.x + next.x);
    normal.z += (current.x - next.x) * (current.y + next.y);
  }
  const x = Math.abs(normal.x);
  const y = Math.abs(normal.y);
  const z = Math.abs(normal.z);
  if (x >= y && x >= z) return 0;
  if (y >= z) return 1;
  return 2;
}

function appendProjected(coordinates: number[], vertex: Vector3, droppedAxis: number) {
  if (droppedAxis === 0) coordinates.push(vertex.y, vertex.z);
  else if (droppedAxis === 1) coordinates.push(vertex.x, vertex.z);
  else coordinates.push(vertex.x, vertex.y);
}

function triangulateSurface(rings: Vector3[][]) {
  const cleaned = rings.map(withoutClosingVertex).filter((ring) => ring.length >= 3);
  if (cleaned.length === 0) return { vertices: [] as Vector3[], indices: [] as number[] };

  const droppedAxis = projectionAxis(cleaned[0]);
  const vertices = cleaned.flat();
  const coordinates: number[] = [];
  const holes: number[] = [];
  let offset = 0;

  cleaned.forEach((ring, ringIndex) => {
    if (ringIndex > 0) holes.push(offset);
    ring.forEach((vertex) => appendProjected(coordinates, vertex, droppedAxis));
    offset += ring.length;
  });

  return { vertices, indices: earcut(coordinates, holes, 2) };
}

export function availableLods(record: BuildingRecord) {
  const lods = new Set<string>();
  Object.values(record.feature.CityObjects).forEach((object) => {
    object.geometry?.forEach((geometry) => {
      if (geometry.lod !== undefined) lods.add(String(geometry.lod));
    });
  });
  return [...lods].sort((a, b) => Number(a) - Number(b));
}

export function createBuildingScene(record: BuildingRecord, requestedLod?: string): BuildingScene {
  const lods = availableLods(record);
  const lod = requestedLod && lods.includes(requestedLod) ? requestedLod : lods.at(-1) ?? "0";
  const transform = record.metadata.transform ?? {
    scale: [1, 1, 1],
    translate: [0, 0, 0],
  };
  const worldVertices = record.feature.vertices.map((vertex) => transformedVertex(vertex, transform));
  const bounds = new Box3();
  const surfaces: SurfaceRecord[] = [];

  Object.entries(record.feature.CityObjects).forEach(([cityObjectId, object]) => {
    object.geometry
      ?.filter((geometry) => String(geometry.lod ?? "") === lod)
      .forEach((geometry) => surfaces.push(...collectSurfaces(geometry, cityObjectId)));
  });

  const usedIndices = new Set(surfaces.flatMap(({ surface }) => surface.flat()));
  usedIndices.forEach((index) => {
    const vertex = worldVertices[index];
    if (vertex) bounds.expandByPoint(vertex);
  });
  if (bounds.isEmpty()) {
    throw new Error(`LoD ${lod} contains no renderable surfaces.`);
  }

  const origin = bounds.getCenter(new Vector3());
  const dataBySemantic = new Map<string, SemanticMeshData>();

  surfaces.forEach(({ surface, semantic, semanticSurface: surfaceMetadata }) => {
    const rings = surface.map((ring) =>
      ring.map((index) => worldVertices[index]).filter((vertex): vertex is Vector3 => Boolean(vertex)),
    );
    const { vertices, indices } = triangulateSurface(rings);
    const underpassId = semantic === OUTER_CEILING_SURFACE
      ? underpassIdFromAttributes(surfaceMetadata.attributes)
      : undefined;
    const meshKey = underpassId ? `${semantic}:${underpassId}` : semantic;
    const data = dataBySemantic.get(meshKey) ?? {
      semantic,
      underpassId,
      positions: [],
      surfaceByTriangle: [],
    };
    for (let index = 0; index < indices.length; index += 3) {
      indices.slice(index, index + 3).forEach((vertexIndex) => {
        const vertex = vertices[vertexIndex];
        data.positions.push(vertex.x - origin.x, vertex.y - origin.y, vertex.z - origin.z);
      });
      data.surfaceByTriangle.push(surfaceMetadata);
    }
    dataBySemantic.set(meshKey, data);
  });

  const group = new Group();
  group.name = record.id;

  dataBySemantic.forEach(({ semantic, underpassId, positions, surfaceByTriangle }) => {
    if (positions.length === 0) return;
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    const material = new MeshStandardMaterial({
      color: SEMANTIC_COLORS[semantic] ?? SEMANTIC_COLORS.default,
      roughness: 0.82,
      metalness: 0,
      side: DoubleSide,
      flatShading: true,
    });
    const mesh = new Mesh(geometry, material);
    mesh.name = semantic;
    mesh.userData.underpassId = underpassId;
    mesh.userData.surfaceByTriangle = surfaceByTriangle;
    group.add(mesh);

    const edges = new LineSegments(
      new EdgesGeometry(geometry, 28),
      new LineBasicMaterial({ color: 0x34433a, transparent: true, opacity: 0.28 }),
    );
    edges.name = `${semantic}:edges`;
    edges.userData.underpassId = underpassId;
    edges.renderOrder = 2;
    group.add(edges);
  });

  return {
    group,
    origin,
    bounds,
    localBounds: bounds.clone().translate(origin.clone().multiplyScalar(-1)),
    lod,
    surfaceCount: surfaces.length,
    vertexCount: usedIndices.size,
  };
}

export function semanticSurfaceForFace(mesh: Mesh, faceIndex?: number | null) {
  if (faceIndex === undefined || faceIndex === null) return undefined;
  const surfaces: unknown = mesh.userData.surfaceByTriangle;
  if (!Array.isArray(surfaces)) return undefined;
  return surfaces[faceIndex] as SemanticSurfacePick | undefined;
}

export function disposeBuildingScene(scene: BuildingScene) {
  scene.group.traverse((object) => {
    if (object instanceof Mesh || object instanceof LineSegments) {
      object.geometry.dispose();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material) => material.dispose());
    }
  });
}

export function setBuildingDisplay(
  scene: BuildingScene,
  visible: boolean,
  outerCeilingOnly: boolean,
) {
  scene.group.visible = visible;
  scene.group.children.forEach((object) => {
    object.visible =
      !outerCeilingOnly ||
      object.name === OUTER_CEILING_SURFACE ||
      object.name === `${OUTER_CEILING_SURFACE}:edges`;
  });
}

export function setSelectedUnderpass(scene: BuildingScene, underpassId?: string) {
  scene.group.children.forEach((object) => {
    if (object.name !== OUTER_CEILING_SURFACE) return;
    const material = object instanceof Mesh ? object.material : undefined;
    if (!(material instanceof MeshStandardMaterial)) return;
    const selected = underpassId !== undefined && object.userData.underpassId === underpassId;
    material.color.setHex(selected ? 0xff3d8d : underpassId ? 0xd59aad : SEMANTIC_COLORS[OUTER_CEILING_SURFACE]);
    material.emissive.setHex(selected ? 0x4a001b : 0x000000);
    material.emissiveIntensity = selected ? 0.24 : 0;
    material.needsUpdate = true;
  });
}
