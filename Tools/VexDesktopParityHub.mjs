#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const VERSION = "0.15.6";
const ROOT = process.env.VEX_DESKTOP_PARITY_ROOT || path.join(process.env.LOCALAPPDATA || os.homedir(), "VexNative", "DesktopParity");
const REGISTRY = path.join(ROOT, "nodes.json");
const INTERNAL_PREFIX = "__vex_";
const connections = new Map();

function readRegistry() {
  try {
    const value = JSON.parse(fs.readFileSync(REGISTRY, "utf8"));
    return Array.isArray(value.nodes) ? value : { nodes: [] };
  } catch {
    return { nodes: [] };
  }
}

function jsonResult(value) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

function parseTextResult(result) {
  try {
    const part = Array.isArray(result.content) ? result.content.find((x) => x && x.type === "text") : null;
    return part ? JSON.parse(part.text) : {};
  } catch {
    return {};
  }
}

async function connection(entry) {
  const key = String(entry.endpoint || "") + "|" + String(entry.token || "");
  if (connections.has(key)) return connections.get(key);
  const client = new Client({ name: "vex-desktop-parity-hub", version: VERSION }, { capabilities: {} });
  const headers = {};
  if (entry.token) headers.Authorization = "Bearer " + String(entry.token);
  const transport = new StreamableHTTPClientTransport(new URL(String(entry.endpoint)), {
    requestInit: { headers }
  });
  await client.connect(transport);
  const value = { client, transport };
  connections.set(key, value);
  client.onclose = () => connections.delete(key);
  return value;
}

async function identity(entry) {
  const c = await connection(entry);
  const result = await c.client.callTool({ name: "__vex_node_identity", arguments: {} });
  return parseTextResult(result);
}

async function listDeviceSnapshots() {
  const registry = readRegistry();
  const out = [];
  for (const entry of registry.nodes.filter((x) => x && x.enabled !== false)) {
    try {
      const id = await identity(entry);
      out.push({
        deviceId: String(id.deviceId || entry.deviceId || entry.name || ""),
        name: String(id.name || entry.name || id.hostname || "Vex node"),
        hostname: String(id.hostname || entry.name || ""),
        online: true,
        version: String(id.version || ""),
        engine: String(id.engine || "")
      });
    } catch (error) {
      out.push({
        deviceId: String(entry.deviceId || entry.name || ""),
        name: String(entry.name || "Vex node"),
        hostname: String(entry.name || ""),
        online: false,
        error: error instanceof Error ? error.message.slice(0, 180) : String(error).slice(0, 180)
      });
    }
  }
  return out;
}

async function resolveNode(deviceId) {
  const wanted = String(deviceId || "").trim();
  if (!wanted) throw new Error("deviceId is required");
  const registry = readRegistry();
  for (const entry of registry.nodes.filter((x) => x && x.enabled !== false)) {
    if (String(entry.deviceId || "") === wanted || String(entry.name || "") === wanted) return entry;
  }
  for (const entry of registry.nodes.filter((x) => x && x.enabled !== false)) {
    try {
      const id = await identity(entry);
      if (String(id.deviceId || "") === wanted || String(id.name || "") === wanted || String(id.hostname || "") === wanted) {
        return entry;
      }
    } catch {}
  }
  throw new Error("Unknown or offline deviceId: " + wanted);
}

async function upstreamTools() {
  const registry = readRegistry();
  let lastError = null;
  for (const entry of registry.nodes.filter((x) => x && x.enabled !== false)) {
    try {
      const c = await connection(entry);
      const listed = await c.client.listTools();
      return (listed.tools || []).filter((tool) => !String(tool.name || "").startsWith(INTERNAL_PREFIX));
    } catch (error) {
      lastError = error;
    }
  }
  if (lastError) throw lastError;
  return [];
}

function withDeviceId(tool) {
  const schema = tool.inputSchema && typeof tool.inputSchema === "object" ? structuredClone(tool.inputSchema) : { type: "object" };
  schema.type = "object";
  schema.properties = {
    deviceId: {
      type: "string",
      description: "Target Vex Desktop Parity device ID or registered node name."
    },
    ...(schema.properties || {})
  };
  schema.required = Array.from(new Set(["deviceId", ...(Array.isArray(schema.required) ? schema.required : [])]));
  return {
    ...tool,
    description: "Run on the selected Vex Desktop Parity device. " + String(tool.description || ""),
    inputSchema: schema
  };
}

const metaTools = [
  {
    name: "list_devices",
    description: "List Vex Desktop Parity computers and their live reachability.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  },
  {
    name: "who_am_i",
    description: "Return this self-hosted Vex Desktop Parity hub identity.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  },
  {
    name: "ping",
    description: "Probe one Vex Desktop Parity computer.",
    inputSchema: {
      type: "object",
      properties: { deviceId: { type: "string" } },
      required: ["deviceId"],
      additionalProperties: false
    }
  },
  {
    name: "shutdown",
    description: "Disconnect and disable one Vex Desktop Parity node until it is re-enabled locally.",
    inputSchema: {
      type: "object",
      properties: { deviceId: { type: "string" } },
      required: ["deviceId"],
      additionalProperties: false
    }
  }
];

const server = new Server(
  { name: "vex-desktop-parity-hub", version: VERSION },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  const mirrored = (await upstreamTools()).map(withDeviceId);
  return { tools: [...metaTools, ...mirrored] };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const name = request.params.name;
  const args = { ...(request.params.arguments || {}) };

  if (name === "list_devices") return jsonResult({ devices: await listDeviceSnapshots(), version: VERSION });
  if (name === "who_am_i") {
    return jsonResult({
      name: "Vex Desktop Parity",
      version: VERSION,
      mode: "self-hosted",
      hostname: os.hostname(),
      registry: REGISTRY
    });
  }

  if (name === "ping" || name === "shutdown") {
    const entry = await resolveNode(args.deviceId);
    const c = await connection(entry);
    const toolName = name === "ping" ? "__vex_node_identity" : "__vex_node_shutdown";
    return await c.client.callTool({ name: toolName, arguments: {} });
  }

  const deviceId = args.deviceId;
  delete args.deviceId;
  const entry = await resolveNode(deviceId);
  const c = await connection(entry);
  return await c.client.callTool({ name, arguments: args });
});

const transport = new StdioServerTransport();
await server.connect(transport);

async function close() {
  for (const value of connections.values()) {
    try { await value.client.close(); } catch {}
  }
  try { await server.close(); } catch {}
}
process.on("SIGINT", async () => { await close(); process.exit(0); });
process.on("SIGTERM", async () => { await close(); process.exit(0); });
