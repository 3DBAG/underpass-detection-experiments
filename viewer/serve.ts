import { join, resolve } from "node:path";
import { existsSync, statSync } from "node:fs";

const distDir = resolve("dist");
if (!existsSync(distDir)) {
  console.error("dist/ does not exist. Run 'bun run build' first.");
  process.exit(1);
}

const basePort = Number(process.env.PORT ?? 3000);

function startServer(port: number): ReturnType<typeof Bun.serve> {
  try {
    return Bun.serve({
      port,
      async fetch(req) {
        const url = new URL(req.url);
        let pathname = decodeURIComponent(url.pathname);
        if (pathname === "/") pathname = "/index.html";

        const filePath = join(distDir, pathname);
        if (!filePath.startsWith(distDir)) {
          return new Response("Forbidden", { status: 403 });
        }
        if (!existsSync(filePath) || !statSync(filePath).isFile()) {
          return new Response("Not Found", { status: 404 });
        }
        return new Response(Bun.file(filePath));
      },
    });
  } catch (e: any) {
    if (e?.code === "EADDRINUSE" && port < basePort + 10) {
      return startServer(port + 1);
    }
    throw e;
  }
}

const server = startServer(basePort);
console.log(`Serving http://localhost:${server.port}`);
