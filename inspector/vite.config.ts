import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { IncomingMessage, ServerResponse } from "node:http";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";
import {
  HIGHLIGHT_TAG,
  isReviewStatus,
  isReviewTag,
  normalizeBuildingTags,
  normalizeReviewTags,
  normalizeReviewStatuses,
  type BuildingTag,
  type ReviewStatus,
  type ReviewTag,
} from "./src/lib/review-tags";

const DEFAULT_FCB_PATH = "/data2/rypeters/ams-run-07-15-rf/seq_underpasses_manifold/city.viewer.fcb";
const DEFAULT_COPC_PATH = "/data2/rypeters/amsterdam_data/2025/merged.copc";

interface UnderpassTagRecord {
  tags: ReviewStatus[];
  updatedAt: string;
  automatic?: boolean;
}

interface LegacyStatusRecord {
  tag: ReviewStatus;
  updatedAt: string;
}

interface BuildingTagRecord {
  tags: BuildingTag[];
  updatedAt?: string;
  underpasses: Record<string, UnderpassTagRecord>;
  legacyStatus?: LegacyStatusRecord;
}

interface TagDatabase {
  version: 2;
  buildings: Record<string, BuildingTagRecord>;
}

function sendJson(response: ServerResponse, status: number, value: unknown) {
  const body = JSON.stringify(value);
  response.statusCode = status;
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Content-Length", Buffer.byteLength(body));
  response.end(body);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function migrateVersionOneDatabase(value: Record<string, unknown>): TagDatabase {
  if (!isObject(value.buildings)) {
    throw new Error("The tag database has an invalid structure.");
  }
  const buildings: Record<string, BuildingTagRecord> = {};
  for (const [buildingId, rawRecord] of Object.entries(value.buildings)) {
    if (!isObject(rawRecord) || typeof rawRecord.updatedAt !== "string") {
      throw new Error(`Invalid tag record for ${buildingId}.`);
    }
    const legacyTags = normalizeReviewTags(rawRecord.tags);
    const status = legacyTags.find(isReviewStatus);
    const highlighted = legacyTags.includes(HIGHLIGHT_TAG);
    buildings[buildingId] = {
      tags: highlighted ? [HIGHLIGHT_TAG] : [],
      updatedAt: highlighted ? rawRecord.updatedAt : undefined,
      underpasses: {},
      legacyStatus: status ? { tag: status, updatedAt: rawRecord.updatedAt } : undefined,
    };
  }
  return { version: 2, buildings };
}

function parseTagDatabase(value: unknown): TagDatabase {
  if (!isObject(value)) throw new Error("The tag database has an invalid structure.");
  if (value.version === 1) return migrateVersionOneDatabase(value);
  if (value.version !== 2 || !isObject(value.buildings)) {
    throw new Error("The tag database has an invalid structure.");
  }

  const buildings: Record<string, BuildingTagRecord> = {};
  for (const [buildingId, rawRecord] of Object.entries(value.buildings)) {
    if (!isObject(rawRecord) || !isObject(rawRecord.underpasses)) {
      throw new Error(`Invalid tag record for ${buildingId}.`);
    }
    const underpasses: Record<string, UnderpassTagRecord> = {};
    for (const [underpassId, rawUnderpass] of Object.entries(rawRecord.underpasses)) {
      if (!isObject(rawUnderpass) || typeof rawUnderpass.updatedAt !== "string") {
        throw new Error(`Invalid tag record for ${buildingId}/${underpassId}.`);
      }
      underpasses[underpassId] = {
        tags: normalizeReviewStatuses(rawUnderpass.tags),
        updatedAt: rawUnderpass.updatedAt,
        automatic: rawUnderpass.automatic === true,
      };
    }
    let legacyStatus: LegacyStatusRecord | undefined;
    if (rawRecord.legacyStatus !== undefined) {
      if (
        !isObject(rawRecord.legacyStatus) ||
        !isReviewStatus(rawRecord.legacyStatus.tag) ||
        typeof rawRecord.legacyStatus.updatedAt !== "string"
      ) {
        throw new Error(`Invalid legacy tag record for ${buildingId}.`);
      }
      legacyStatus = {
        tag: rawRecord.legacyStatus.tag,
        updatedAt: rawRecord.legacyStatus.updatedAt,
      };
    }
    const tags = normalizeBuildingTags(rawRecord.tags);
    const updatedAt = typeof rawRecord.updatedAt === "string" ? rawRecord.updatedAt : undefined;
    buildings[buildingId] = { tags, updatedAt, underpasses, legacyStatus };
  }
  return { version: 2, buildings };
}

async function readTagDatabase(filePath: string): Promise<TagDatabase> {
  try {
    return parseTagDatabase(JSON.parse(await fs.promises.readFile(filePath, "utf8")) as unknown);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { version: 2, buildings: {} };
    }
    throw error;
  }
}

function emptyBuildingRecord(): BuildingTagRecord {
  return { tags: [], underpasses: {} };
}

function isEmptyBuildingRecord(record: BuildingTagRecord) {
  return record.tags.length === 0 &&
    Object.keys(record.underpasses).length === 0 &&
    !record.legacyStatus;
}

function reviewResponse(buildingId: string, record?: BuildingTagRecord) {
  return {
    buildingId,
    tags: record?.tags ?? [],
    updatedAt: record?.updatedAt,
    underpasses: record?.underpasses ?? {},
    legacyStatus: record?.legacyStatus,
  };
}

function decodePathSegment(value: string, label: string) {
  try {
    const decoded = decodeURIComponent(value);
    if (!decoded) throw new Error();
    return decoded;
  } catch {
    throw new Error(`Invalid ${label}.`);
  }
}

async function writeTagDatabase(filePath: string, database: TagDatabase) {
  await fs.promises.mkdir(path.dirname(filePath), { recursive: true });
  const temporaryPath = `${filePath}.${process.pid}.tmp`;
  await fs.promises.writeFile(temporaryPath, `${JSON.stringify(database, null, 2)}\n`);
  await fs.promises.rename(temporaryPath, filePath);
}

async function readJsonBody(request: IncomingMessage) {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > 32_768) throw new Error("Request body is too large.");
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
}

function tagStorePlugin(databasePath: string): Plugin {
  let mutations: Promise<void> = Promise.resolve();

  function mutate<T>(task: () => Promise<T>) {
    const result = mutations.then(task, task);
    mutations = result.then(() => undefined, () => undefined);
    return result;
  }

  return {
    name: "building-review-tags",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const url = request.url ? new URL(request.url, "http://local") : undefined;
        if (!url || (url.pathname !== "/api/tags" && !url.pathname.startsWith("/api/tags/"))) {
          next();
          return;
        }

        void (async () => {
          if (url.pathname === "/api/tags") {
            if (request.method !== "GET") {
              sendJson(response, 405, { error: "Method not allowed." });
              return;
            }
            const requestedTag = url.searchParams.get("tag");
            if (requestedTag !== null && !isReviewTag(requestedTag)) {
              sendJson(response, 400, { error: "Unsupported tag." });
              return;
            }
            await mutations;
            const database = await readTagDatabase(databasePath);
            const objects = Object.entries(database.buildings).flatMap(
              ([buildingId, record]) => {
                const matches: Array<{
                  buildingId: string;
                  underpassId?: string;
                  legacy?: boolean;
                  tags: ReviewTag[];
                  updatedAt?: string;
                }> = [];
                if (requestedTag === null || record.tags.includes(requestedTag as BuildingTag)) {
                  if (record.tags.length > 0) {
                    matches.push({ buildingId, tags: record.tags, updatedAt: record.updatedAt });
                  }
                }
                for (const [underpassId, underpass] of Object.entries(record.underpasses)) {
                  if (requestedTag === null || underpass.tags.includes(requestedTag as ReviewStatus)) {
                    if (underpass.tags.length > 0) {
                      matches.push({ buildingId, underpassId, ...underpass });
                    }
                  }
                }
                if (
                  record.legacyStatus &&
                  (requestedTag === null || record.legacyStatus.tag === requestedTag)
                ) {
                  matches.push({
                    buildingId,
                    legacy: true,
                    tags: [record.legacyStatus.tag],
                    updatedAt: record.legacyStatus.updatedAt,
                  });
                }
                return matches;
              },
            ).sort((a, b) =>
              a.buildingId.localeCompare(b.buildingId) ||
              (a.underpassId ?? "").localeCompare(b.underpassId ?? "", undefined, { numeric: true }),
            );
            sendJson(response, 200, {
              tag: requestedTag,
              buildingIds: [...new Set(objects.map(({ buildingId }) => buildingId))],
              objects,
            });
            return;
          }

          let buildingId: string;
          let underpassId: string | undefined;
          try {
            const path = url.pathname.slice("/api/tags/".length).split("/");
            if (path.length > 2) throw new Error("Invalid tag path.");
            buildingId = decodePathSegment(path[0], "building ID");
            underpassId = path[1]
              ? decodePathSegment(path[1], "underpass ID")
              : undefined;
          } catch (error) {
            sendJson(response, 400, {
              error: error instanceof Error ? error.message : String(error),
            });
            return;
          }

          if (request.method === "GET") {
            if (underpassId) {
              sendJson(response, 405, { error: "Method not allowed." });
              return;
            }
            const underpassIds = [...new Set(
              url.searchParams.getAll("underpass").filter(Boolean),
            )];
            const result = await mutate(async () => {
              const database = await readTagDatabase(databasePath);
              const record = database.buildings[buildingId];
              if (
                record?.legacyStatus &&
                underpassIds.length === 1 &&
                !record.underpasses[underpassIds[0]]
              ) {
                record.underpasses[underpassIds[0]] = {
                  tags: [record.legacyStatus.tag],
                  updatedAt: record.legacyStatus.updatedAt,
                };
                delete record.legacyStatus;
                await writeTagDatabase(databasePath, database);
              }
              return reviewResponse(buildingId, record);
            });
            sendJson(response, 200, result);
            return;
          }

          if (request.method === "PUT") {
            let tags: BuildingTag[] | ReviewStatus[];
            let resolveLegacy = false;
            let automatic = false;
            try {
              const body = await readJsonBody(request);
              if (!isObject(body)) throw new Error("The request body must be an object.");
              tags = underpassId
                ? normalizeReviewStatuses(body.tags)
                : normalizeBuildingTags(body.tags);
              if (underpassId) {
                if (body.resolveLegacy !== undefined && typeof body.resolveLegacy !== "boolean") {
                  throw new Error("resolveLegacy must be a boolean.");
                }
                if (body.automatic !== undefined && typeof body.automatic !== "boolean") {
                  throw new Error("automatic must be a boolean.");
                }
                resolveLegacy = body.resolveLegacy === true;
                automatic = body.automatic === true;
              }
            } catch (error) {
              sendJson(response, 400, {
                error: error instanceof Error ? error.message : String(error),
              });
              return;
            }
            const updatedAt = new Date().toISOString();
            await mutate(async () => {
              const database = await readTagDatabase(databasePath);
              const record = database.buildings[buildingId] ?? emptyBuildingRecord();
              if (underpassId) {
                record.underpasses[underpassId] = {
                  tags: tags as ReviewStatus[],
                  updatedAt,
                  automatic,
                };
                if (resolveLegacy) delete record.legacyStatus;
              } else {
                record.tags = tags as BuildingTag[];
                record.updatedAt = tags.length > 0 ? updatedAt : undefined;
              }
              if (isEmptyBuildingRecord(record)) delete database.buildings[buildingId];
              else database.buildings[buildingId] = record;
              await writeTagDatabase(databasePath, database);
            });
            sendJson(response, 200, {
              buildingId,
              underpassId,
              tags,
              updatedAt,
              automatic: underpassId ? automatic : undefined,
            });
            return;
          }

          sendJson(response, 405, { error: "Method not allowed." });
        })().catch((error: unknown) => {
          sendJson(response, 500, {
            error: error instanceof Error ? error.message : String(error),
          });
        });
      });
    },
  };
}

function sendRangeFile(
  request: IncomingMessage,
  response: ServerResponse,
  filePath: string,
) {
  const stat = fs.statSync(filePath);
  const range = request.headers.range;

  response.setHeader("Accept-Ranges", "bytes");
  response.setHeader("Cache-Control", "no-cache");
  response.setHeader("Content-Type", "application/octet-stream");

  if (!range) {
    response.statusCode = 200;
    response.setHeader("Content-Length", stat.size);
    fs.createReadStream(filePath).pipe(response);
    return;
  }

  const match = /^bytes=(\d+)-(\d*)$/.exec(range);
  if (!match) {
    response.statusCode = 416;
    response.setHeader("Content-Range", `bytes */${stat.size}`);
    response.end();
    return;
  }

  const start = Number(match[1]);
  const end = match[2] ? Math.min(Number(match[2]), stat.size - 1) : stat.size - 1;
  if (start > end || start >= stat.size) {
    response.statusCode = 416;
    response.setHeader("Content-Range", `bytes */${stat.size}`);
    response.end();
    return;
  }

  response.statusCode = 206;
  response.setHeader("Content-Length", end - start + 1);
  response.setHeader("Content-Range", `bytes ${start}-${end}/${stat.size}`);
  fs.createReadStream(filePath, { start, end }).pipe(response);
}

function localDatasetPlugin(
  fcbPath: string,
  copcPath: string,
  underpassPath: string,
): Plugin {
  const routes = new Map([
    ["/data/city.fcb", fcbPath],
    ["/data/merged.copc", copcPath],
    ["/data/underpasses.json", underpassPath],
  ]);

  return {
    name: "local-dataset-ranges",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = request.url ? new URL(request.url, "http://local").pathname : "";
        const filePath = routes.get(pathname);
        if (!filePath) {
          next();
          return;
        }
        if (!fs.existsSync(filePath)) {
          response.statusCode = 404;
          response.end(`Dataset not found: ${filePath}`);
          return;
        }
        sendRangeFile(request, response, filePath);
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const fcbPath = path.resolve(env.FCB_PATH || DEFAULT_FCB_PATH);
  const copcPath = path.resolve(env.COPC_PATH || DEFAULT_COPC_PATH);
  const underpassPath = path.resolve(
    env.UNDERPASS_MANIFEST_PATH || fcbPath.replace(/\.fcb$/, ".underpasses.json"),
  );
  const tagDatabasePath = path.resolve(env.TAG_DB_PATH || ".viewer-tags.json");

  return {
    plugins: [
      react(),
      tailwindcss(),
      localDatasetPlugin(fcbPath, copcPath, underpassPath),
      tagStorePlugin(tagDatabasePath),
    ],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: { port: 5173 },
  };
});
