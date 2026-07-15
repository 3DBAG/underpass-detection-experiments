/// <reference lib="webworker" />

import {
  Bounds,
  Copc,
  Key,
  Las,
  type Getter,
  type Hierarchy,
} from "copc";

interface LoadRequest {
  type: "load";
  url: string;
  bounds: [[number, number, number], [number, number, number]];
  origin: [number, number, number];
  pointBudget: number;
}

interface CopcNodeRecord {
  key: string;
  node: Hierarchy.Node;
  depth: number;
}

function post(data: unknown, transfer: Transferable[] = []) {
  self.postMessage(data, { transfer });
}

function makeRangeGetter(url: string): Getter {
  return async (begin, end) => {
    const response = await fetch(url, { headers: { Range: `bytes=${begin}-${end - 1}` } });
    if (!response.ok) throw new Error(`COPC range request failed (${response.status}).`);
    return new Uint8Array(await response.arrayBuffer());
  };
}

function intersects(a: Bounds, b: Bounds) {
  return !(
    a[3] < b[0] || a[0] > b[3] ||
    a[4] < b[1] || a[1] > b[4] ||
    a[5] < b[2] || a[2] > b[5]
  );
}

function pointTargetDepth(pointBudget: number) {
  if (pointBudget <= 500_000) return 9;
  if (pointBudget <= 1_000_000) return 10;
  if (pointBudget <= 2_000_000) return 11;
  return 12;
}

function expandBounds(bounds: LoadRequest["bounds"]): Bounds {
  return [
    bounds[0][0] - 3,
    bounds[0][1] - 3,
    bounds[0][2] - 3,
    bounds[1][0] + 3,
    bounds[1][1] + 3,
    bounds[1][2] + 3,
  ];
}

async function discoverNodes(getter: Getter, copc: Copc, target: Bounds, maxDepth: number) {
  const queue: Hierarchy.Page[] = [copc.info.rootHierarchyPage];
  const visitedPages = new Set<string>();
  const nodes = new Map<string, CopcNodeRecord>();

  for (let queueIndex = 0; queueIndex < queue.length; queueIndex += 1) {
    const page = queue[queueIndex];
    const pageId = `${page.pageOffset}:${page.pageLength}`;
    if (visitedPages.has(pageId)) continue;
    visitedPages.add(pageId);
    const subtree = await Copc.loadHierarchyPage(getter, page);

    Object.entries(subtree.nodes).forEach(([key, node]) => {
      if (!node || node.pointCount === 0 || node.pointDataLength === 0) return;
      const parsed = Key.parse(key);
      if (parsed[0] <= maxDepth && intersects(Bounds.stepTo(copc.info.cube, parsed), target)) {
        nodes.set(key, { key, node, depth: parsed[0] });
      }
    });
    Object.entries(subtree.pages).forEach(([key, childPage]) => {
      if (!childPage) return;
      const parsed = Key.parse(key);
      if (parsed[0] < maxDepth && intersects(Bounds.stepTo(copc.info.cube, parsed), target)) {
        queue.push(childPage);
      }
    });
  }

  return [...nodes.values()].sort((a, b) => b.depth - a.depth || a.key.localeCompare(b.key));
}

function colorGetter(view: Awaited<ReturnType<typeof Copc.loadPointDataView>>) {
  if (view.dimensions.Red && view.dimensions.Green && view.dimensions.Blue) {
    const red = view.getter("Red");
    const green = view.getter("Green");
    const blue = view.getter("Blue");
    return (index: number): [number, number, number] => {
      const redValue = red(index);
      const greenValue = green(index);
      const blueValue = blue(index);
      const divisor = Math.max(redValue, greenValue, blueValue) > 255 ? 65535 : 255;
      return [redValue / divisor, greenValue / divisor, blueValue / divisor];
    };
  }
  if (view.dimensions.Intensity) {
    const intensity = view.getter("Intensity");
    return (index: number): [number, number, number] => {
      const value = Math.min(1, Math.sqrt(intensity(index) / 65535));
      return [value, value, value];
    };
  }
  return (): [number, number, number] => [0.32, 0.42, 0.38];
}

async function load(request: LoadRequest) {
  const getter = makeRangeGetter(request.url);
  const copc = await Copc.create(getter);
  const lazPerf = await Las.PointData.createLazPerf({
    locateFile: () => new URL("/laz-perf.wasm", self.location.origin).href,
  });
  post({ type: "metadata", totalPoints: copc.header.pointCount });
  const target = expandBounds(request.bounds);
  const nodes = await discoverNodes(getter, copc, target, pointTargetDepth(request.pointBudget));
  const candidateCount = nodes.reduce((sum, record) => sum + record.node.pointCount, 0);
  const stride = Math.max(1, Math.ceil(candidateCount / request.pointBudget));

  for (let nodeIndex = 0; nodeIndex < nodes.length; nodeIndex += 1) {
    const view = await Copc.loadPointDataView(getter, copc, nodes[nodeIndex].node, {
      lazPerf,
      include: ["X", "Y", "Z", "Red", "Green", "Blue", "Intensity"],
    });
    const getX = view.getter("X");
    const getY = view.getter("Y");
    const getZ = view.getter("Z");
    const getColor = colorGetter(view);
    const positions: number[] = [];
    const colors: number[] = [];

    for (let index = 0; index < view.pointCount; index += stride) {
      const x = getX(index);
      const y = getY(index);
      const z = getZ(index);
      if (x < target[0] || x > target[3] || y < target[1] || y > target[4] || z < target[2] || z > target[5]) continue;
      positions.push(x - request.origin[0], y - request.origin[1], z - request.origin[2]);
      colors.push(...getColor(index));
    }

    const progress = (nodeIndex + 1) / nodes.length;
    if (positions.length > 0) {
      const positionArray = new Float32Array(positions);
      const colorArray = new Float32Array(colors);
      post(
        { type: "chunk", positions: positionArray, colors: colorArray, pointCount: positionArray.length / 3, progress },
        [positionArray.buffer, colorArray.buffer],
      );
    } else {
      post({ type: "progress", progress });
    }
  }
  post({ type: "done" });
}

self.onmessage = ({ data }: MessageEvent<LoadRequest>) => {
  if (data.type !== "load") return;
  load(data).catch((error: unknown) => {
    post({ type: "error", message: error instanceof Error ? error.message : String(error) });
  });
};
