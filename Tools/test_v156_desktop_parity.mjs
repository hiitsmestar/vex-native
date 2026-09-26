#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const ROOT = process.cwd();
const NODE_SCRIPT = path.join(ROOT, "Tools", "VexDesktopParityNode.mjs");
const HUB_SCRIPT = path.join(ROOT, "Tools", "VexDesktopParityHub.mjs");
const TOKEN = "ci-vex-desktop-parity-token";
const PORT = 18790;

const expected = [
  "get_config", "set_config_value",
  "read_file", "read_multiple_files", "write_file", "write_pdf",
  "create_directory", "list_directory", "move_file",
  "start_search", "get_more_search_results", "stop_search", "list_searches",
  "get_file_info", "edit_block",
  "start_process", "read_process_output", "interact_with_process", "force_terminate",
  "list_sessions", "list_processes", "kill_process",
  "get_usage_stats", "get_recent_tool_calls", "get_prompts"
];

function env(extra = {}) {
  return { ...process.env, VEX_DESKTOP_PARITY_ROOT: ROOT, ...extra };
}

async function stdioClient(script, name) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [script],
    env: env()
  });
  const client = new Client({ name, version: "0.15.6" }, { capabilities: {} });
  await client.connect(transport);
  return { client, transport };
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

fs.writeFileSync(path.join(ROOT, "node-config.json"), JSON.stringify({
  version: "0.15.6",
  deviceId: "ci-node-1",
  name: "ci-node"
}, null, 2));

let direct = null;
let hub = null;
let gateway = null;

try {
  direct = await stdioClient(NODE_SCRIPT, "vex-parity-ci-direct");
  const directTools = await direct.client.listTools();
  const directNames = new Set((directTools.tools || []).map((x) => x.name));
  for (const name of expected) assert(directNames.has(name), "missing direct tool: " + name);
  assert(directNames.has("__vex_node_identity"), "missing node identity control");

  const directConfig = await direct.client.callTool({ name: "get_config", arguments: {} });
  assert(Array.isArray(directConfig.content), "direct get_config returned no content");
  await direct.client.close();
  direct = null;

  gateway = spawn("python", [
    "-m", "mcp_stdio", "serve",
    "--host", "127.0.0.1",
    "--port", String(PORT),
    "--",
    process.execPath, NODE_SCRIPT
  ], {
    cwd: ROOT,
    env: env({ MCP_STDIO_SERVE_TOKEN: TOKEN }),
    stdio: ["ignore", "pipe", "pipe"]
  });

  let gatewayStderr = "";
  gateway.stderr.on("data", (d) => { gatewayStderr += d.toString(); });
  await sleep(3500);
  assert.equal(gateway.exitCode, null, "node HTTP gateway exited early: " + gatewayStderr.slice(-1200));

  fs.writeFileSync(path.join(ROOT, "nodes.json"), JSON.stringify({
    version: "0.15.6",
    nodes: [{
      name: "ci-node",
      endpoint: "http://127.0.0.1:" + PORT + "/mcp",
      token: TOKEN,
      enabled: true
    }]
  }, null, 2));

  hub = await stdioClient(HUB_SCRIPT, "vex-parity-ci-hub");
  const hubTools = await hub.client.listTools();
  const hubMap = new Map((hubTools.tools || []).map((x) => [x.name, x]));

  for (const name of ["list_devices", "who_am_i", "ping", "shutdown", ...expected]) {
    assert(hubMap.has(name), "missing hub tool: " + name);
  }
  for (const name of expected) {
    const schema = hubMap.get(name).inputSchema || {};
    assert(schema.properties && schema.properties.deviceId, "deviceId not injected for " + name);
    assert(Array.isArray(schema.required) && schema.required.includes("deviceId"), "deviceId not required for " + name);
  }

  const devicesResult = await hub.client.callTool({ name: "list_devices", arguments: {} });
  const devicesText = (devicesResult.content || []).find((x) => x.type === "text")?.text || "{}";
  const devices = JSON.parse(devicesText).devices || [];
  assert.equal(devices.length, 1, "hub did not return exactly one CI node");
  assert.equal(devices[0].deviceId, "ci-node-1", "hub did not preserve node device ID");
  assert.equal(devices[0].online, true, "CI node was not online");

  const routedConfig = await hub.client.callTool({ name: "get_config", arguments: { deviceId: "ci-node-1" } });
  assert(Array.isArray(routedConfig.content), "hub routed get_config returned no content");

  const pingResult = await hub.client.callTool({ name: "ping", arguments: { deviceId: "ci-node-1" } });
  const pingText = (pingResult.content || []).find((x) => x.type === "text")?.text || "{}";
  assert.equal(JSON.parse(pingText).deviceId, "ci-node-1", "hub ping routed to wrong node");

  console.log("PASS Vex Desktop Parity v0.15.6: exact upstream tool proxy + multi-device routing");
} finally {
  try { await hub?.client.close(); } catch {}
  try { await direct?.client.close(); } catch {}
  if (gateway && gateway.exitCode === null) gateway.kill();
  for (const name of ["node-config.json", "nodes.json", "node-disabled.flag"]) {
    try { fs.rmSync(path.join(ROOT, name), { force: true }); } catch {}
  }
}
