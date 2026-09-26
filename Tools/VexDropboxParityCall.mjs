#!/usr/bin/env node
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.env.VEX_DESKTOP_PARITY_ROOT || process.cwd();
const clientUrl = pathToFileURL(path.join(root, "node_modules", "@modelcontextprotocol", "sdk", "dist", "esm", "client", "index.js")).href;
const transportUrl = pathToFileURL(path.join(root, "node_modules", "@modelcontextprotocol", "sdk", "dist", "esm", "client", "streamableHttp.js")).href;
const { Client } = await import(clientUrl);
const { StreamableHTTPClientTransport } = await import(transportUrl);

const input = JSON.parse(process.argv[2] || "{}");
const headers = input.token ? { Authorization: "Bearer " + input.token } : {};
const client = new Client({ name: "vex-dropbox-parity", version: "0.15.6" }, { capabilities: {} });
const transport = new StreamableHTTPClientTransport(new URL(input.endpoint), { requestInit: { headers } });
await client.connect(transport);
try {
  const result = await client.callTool({ name: String(input.tool), arguments: input.arguments || {} });
  process.stdout.write(JSON.stringify(result));
} finally {
  await client.close();
}
