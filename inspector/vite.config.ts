import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { IncomingMessage, ServerResponse } from "node:http";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

const DEFAULT_FCB_PATH = "/data2/rypeters/ams-run-07-15-rf/seq_underpasses_manifold/city.viewer.fcb";
const DEFAULT_COPC_PATH = "/data2/rypeters/amsterdam_data/2025/merged.copc";

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

  return {
    plugins: [
      react(),
      tailwindcss(),
      localDatasetPlugin(fcbPath, copcPath, underpassPath),
    ],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: { port: 5173 },
  };
});
