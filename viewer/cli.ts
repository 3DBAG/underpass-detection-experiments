import { createServer } from "node:http";
import { access, stat } from "node:fs/promises";
import { constants } from "node:fs";
import { basename, dirname, extname, normalize, relative, resolve, sep } from "node:path";

type CliOptions = {
  host: string;
  port: number;
  viewerPort: number;
  tilesets: string[];
};

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 9010;
const DEFAULT_VIEWER_PORT = 9011;
const DEFAULT_TILESETS = [
  "/data2/rypeters/ams-run-07-07-rf/seq_underpasses_pmp_3dt",
  "/data2/rypeters/amsterdam_data/2025/cropped-3dtiles",
];
const VIEWER_DIST_DIR = resolve(import.meta.dir, "dist");

const MIME_TYPES: Record<string, string> = {
  ".b3dm": "application/octet-stream",
  ".bin": "application/octet-stream",
  ".cmpt": "application/octet-stream",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".i3dm": "application/octet-stream",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".json": "application/json",
  ".ktx2": "image/ktx2",
  ".pnts": "application/octet-stream",
  ".png": "image/png",
  ".subtree": "application/octet-stream",
  ".svg": "image/svg+xml",
  ".terrain": "application/octet-stream",
  ".wasm": "application/wasm",
};

function printHelp() {
  console.log(`3dtiles-tester

Usage:
  nix run <repo> -- [options]

Options:
  --host <host>             Bind host (default: ${DEFAULT_HOST})
  --port <port>             Tileset server port (default: ${DEFAULT_PORT})
  --viewer-port <port>      Viewer server port (default: ${DEFAULT_VIEWER_PORT})
  --tileset <path>          Tileset file or directory. Can be repeated.
                            Default tilesets:
                            ${DEFAULT_TILESETS.join("\n                            ")}
  -h, --help                Show help
`);
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
    viewerPort: DEFAULT_VIEWER_PORT,
    tilesets: DEFAULT_TILESETS,
  };
  let customTilesets = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    }

    const value = argv[index + 1];
    if (!value) {
      throw new Error(`Missing value for ${arg}`);
    }

    switch (arg) {
      case "--host":
        options.host = value;
        index += 1;
        break;
      case "--port":
        options.port = Number.parseInt(value, 10);
        index += 1;
        break;
      case "--viewer-port":
        options.viewerPort = Number.parseInt(value, 10);
        index += 1;
        break;
      case "--tileset":
        if (!customTilesets) {
          options.tilesets = [];
          customTilesets = true;
        }
        options.tilesets.push(value);
        index += 1;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!Number.isInteger(options.port) || options.port <= 0) {
    throw new Error(`Invalid port: ${options.port}`);
  }
  if (!Number.isInteger(options.viewerPort) || options.viewerPort <= 0) {
    throw new Error(`Invalid viewer port: ${options.viewerPort}`);
  }
  if (options.tilesets.length === 0) {
    throw new Error("At least one tileset is required");
  }

  return options;
}

function buildViewerUrl(baseUrl: string, tilesetUrls: string[], tilesetLabels: string[]): string {
  const url = new URL(baseUrl);
  for (const tilesetUrl of tilesetUrls) {
    url.searchParams.append("tileset", tilesetUrl);
  }
  for (const tilesetLabel of tilesetLabels) {
    url.searchParams.append("tilesetLabel", tilesetLabel);
  }
  return url.toString();
}

function resolveRequestPath(rootDir: string, pathname: string): string {
  const decoded = decodeURIComponent(pathname);
  const normalized = normalize(decoded).replace(new RegExp(`^\\${sep}+`), "");
  return resolve(rootDir, normalized);
}

function buildServer(
  rootDir: string,
  host: string,
  port: number,
  defaultPath: string,
) {
  return createServer(async (req, res) => {
    const requestOrigin = req.headers.origin;
    res.setHeader("Access-Control-Allow-Origin", typeof requestOrigin === "string" ? requestOrigin : "*");
    res.setHeader("Access-Control-Allow-Headers", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    res.setHeader("Access-Control-Allow-Private-Network", "true");
    res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
    res.setHeader(
      "Vary",
      "Origin, Access-Control-Request-Headers, Access-Control-Request-Method, Access-Control-Request-Private-Network",
    );

    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405);
      res.end("Method Not Allowed");
      return;
    }

    const reqUrl = new URL(req.url ?? "/", `http://${req.headers.host ?? `${host}:${port}`}`);
    const targetPath = resolveRequestPath(rootDir, reqUrl.pathname === "/" ? defaultPath : reqUrl.pathname);

    if (targetPath !== rootDir && !targetPath.startsWith(`${rootDir}${sep}`)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    try {
      const targetStat = await stat(targetPath);
      if (!targetStat.isFile()) {
        res.writeHead(404);
        res.end("Not Found");
        return;
      }

      const file = Bun.file(targetPath);
      const contentType = MIME_TYPES[extname(targetPath).toLowerCase()] ?? file.type ?? "application/octet-stream";
      res.writeHead(200, {
        "Content-Length": targetStat.size,
        "Content-Type": contentType,
      });

      if (req.method === "HEAD") {
        res.end();
        return;
      }

      const buffer = Buffer.from(await file.arrayBuffer());
      res.end(buffer);
    } catch {
      res.writeHead(404);
      res.end("Not Found");
    }
  });
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

async function resolveTilesetPath(cwd: string, tileset: string): Promise<string> {
  const inputPath = resolve(cwd, tileset);
  const inputStat = await stat(inputPath);
  if (inputStat.isDirectory()) {
    return resolve(inputPath, "tileset.json");
  }
  return inputPath;
}

async function choosePort(host: string, startPort: number): Promise<number> {
  for (let port = startPort; port < startPort + 20; port += 1) {
    const available = await new Promise<boolean>((resolvePort) => {
      const server = createServer();
      server.once("error", () => resolvePort(false));
      server.listen(port, host, () => {
        server.close(() => resolvePort(true));
      });
    });

    if (available) {
      return port;
    }
  }

  throw new Error(`Could not find an open port starting at ${startPort}`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const cwd = process.cwd();
  if (!(await pathExists(resolve(VIEWER_DIST_DIR, "index.html")))) {
    throw new Error(`Viewer bundle not found: ${VIEWER_DIST_DIR}`);
  }

  const tilesetServers: ReturnType<typeof buildServer>[] = [];
  const loopbackTilesetUrls: string[] = [];
  const tilesetLabels: string[] = [];

  for (const [index, tileset] of options.tilesets.entries()) {
    let tilesetPath: string;
    try {
      tilesetPath = await resolveTilesetPath(cwd, tileset);
    } catch {
      throw new Error(`Tileset not found: ${resolve(cwd, tileset)}`);
    }

    if (!(await pathExists(tilesetPath))) {
      throw new Error(`Tileset not found: ${tilesetPath}`);
    }

    const tilesetIsInCwd = tilesetPath === cwd || tilesetPath.startsWith(`${cwd}${sep}`);
    const tilesetRootDir = tilesetIsInCwd ? cwd : dirname(tilesetPath);
    const tilesetPathForUrl = (
      tilesetIsInCwd ? relative(cwd, tilesetPath) : basename(tilesetPath)
    ).split(sep).join("/");

    const tilesetPort = await choosePort(options.host, options.port + index);
    const tilesetServer = buildServer(tilesetRootDir, options.host, tilesetPort, `/${tilesetPathForUrl}`);
    await new Promise<void>((resolveStart, rejectStart) => {
      tilesetServer.once("error", rejectStart);
      tilesetServer.listen(tilesetPort, options.host, () => resolveStart());
    });

    tilesetServers.push(tilesetServer);
    loopbackTilesetUrls.push(new URL(tilesetPathForUrl, `http://127.0.0.1:${tilesetPort}/`).toString());
    tilesetLabels.push(basename(dirname(tilesetPath)));
    console.log(`Serving ${tilesetRootDir}`);
    console.log(`Loopback tileset URL ${index + 1}: ${loopbackTilesetUrls[index]}`);
  }

  const viewerPort = await choosePort(options.host, options.viewerPort);
  const viewerServer = buildServer(VIEWER_DIST_DIR, options.host, viewerPort, "/index.html");
  await new Promise<void>((resolveStart, rejectStart) => {
    viewerServer.once("error", rejectStart);
    viewerServer.listen(viewerPort, options.host, () => resolveStart());
  });

  const localViewerLoopbackUrl = buildViewerUrl(`http://127.0.0.1:${viewerPort}/`, loopbackTilesetUrls, tilesetLabels);

  console.log(`Local viewer URL (loopback): ${localViewerLoopbackUrl}`);

  const shutdown = () => {
    let remaining = tilesetServers.length + 1;
    const finish = () => {
      remaining -= 1;
      if (remaining === 0) process.exit(0);
    };

    for (const tilesetServer of tilesetServers) {
      tilesetServer.close(finish);
    }
    viewerServer.close(finish);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

void main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(message);
  process.exit(1);
});
