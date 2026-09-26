#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const VERSION = "0.15.6";
const ROOT = process.env.VEX_DESKTOP_PARITY_ROOT || path.join(process.env.LOCALAPPDATA || os.homedir(), "VexNative", "DesktopParity");
const NODE_CONFIG = path.join(ROOT, "node-config.json");
const DISABLED_FLAG = path.join(ROOT, "node-disabled.flag");
const UPSTREAM = path.join(ROOT, "node_modules", "@wonderwhy-er", "desktop-commander", "dist", "index.js");

function readJson(file, fallback = {}) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
}

function jsonResult(value) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

if (fs.existsSync(DISABLED_FLAG)) {
  console.error("Vex Desktop Parity node is disabled. Remove " + DISABLED_FLAG + " to re-enable.");
  process.exit(23);
}
if (!fs.existsSync(UPSTREAM)) {
  console.error("Desktop Commander engine not found at " + UPSTREAM);
  process.exit(24);
}

let upstreamClient = null;
let upstreamTransport = null;

async function upstream() {
  if (upstreamClient) return upstreamClient;
  upstreamTransport = new StdioClientTransport({
    command: process.execPath,
    args: [UPSTREAM],
    env: { ...process.env, DC_REMOTE_DEVICE: "true" }
  });
  upstreamClient = new Client({ name: "vex-desktop-parity-node", version: VERSION }, { capabilities: {} });
  upstreamClient.onclose = () => { upstreamClient = null; upstreamTransport = null; };
  await upstreamClient.connect(upstreamTransport);
  return upstreamClient;
}

const server = new Server(
  { name: "vex-desktop-parity-node", version: VERSION },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  const client = await upstream();
  const listed = await client.listTools();
  const tools = Array.isArray(listed.tools) ? listed.tools.slice() : [];
  tools.push({
    name: "__vex_node_identity",
    description: "Internal Vex parity node identity/status probe.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  });
  tools.push({
    name: "__vex_node_shutdown",
    description: "Internal Vex parity node disconnect control.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  });
  return { tools };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const name = request.params.name;
  const args = request.params.arguments || {};
  if (name === "__vex_node_identity") {
    const cfg = readJson(NODE_CONFIG, {});
    return jsonResult({
      ok: true,
      version: VERSION,
      engine: "@wonderwhy-er/desktop-commander@0.2.51",
      deviceId: String(cfg.deviceId || os.hostname()),
      name: String(cfg.name || os.hostname()),
      hostname: os.hostname(),
      platform: process.platform,
      pid: process.pid
    });
  }
  if (name === "__vex_node_shutdown") {
    fs.writeFileSync(DISABLED_FLAG, new Date().toISOString() + "\n", "utf8");
    setTimeout(async () => {
      try { await upstreamClient?.close(); } catch {}
      process.exit(0);
    }, 250);
    return jsonResult({ ok: true, disabled: true, message: "Node will disconnect and stay disabled until re-enabled locally." });
  }
  const client = await upstream();
  return await client.callTool({ name, arguments: args });
});

const transport = new StdioServerTransport();
await server.connect(transport);

async function close() {
  try { await upstreamClient?.close(); } catch {}
  try { await server.close(); } catch {}
}
process.on("SIGINT", async () => { await close(); process.exit(0); });
process.on("SIGTERM", async () => { await close(); process.exit(0); });
