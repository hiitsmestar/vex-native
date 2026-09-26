#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn, spawnSync } from "node:child_process";
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

const guard = setTimeout(() => {
  console.error("FAIL global parity test timeout");
  process.exit(99);
}, 120000);
guard.unref();

function env(extra = {}) {
  return { ...process.env, VEX_DESKTOP_PARITY_ROOT: ROOT, ...extra };
}

function wait(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function timed(promise, label, ms = 20000) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("timeout: " + label)), ms);
      })
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function stdioClient(script, name) {
  console.log("STEP connect " + name);
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [script],
    env: env()
  });
  const client = new Client({ name, version: "0.15.6" }, { capabilities: {} });
  await timed(client.connect(transport), "connect " + name, 25000);
  console.log("PASS connect " + name);
  return { client, transport };
}

async function closePair(pair, label) {
  if (!pair) return;
  console.log("STEP close " + label);
  try { await timed(pair.client.close(), "client close " + label, 5000); } catch (e) { console.warn(String(e)); }
  try { await timed(pair.transport.close(), "transport close " + label, 5000); } catch (e) { console.warn(String(e)); }
  console.log("PASS close " + label);
}

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

  console.log("STEP direct list_tools");
  const directTools = await timed(direct.client.listTools(), "direct list_tools", 25000);
  const directNames = new Set((directTools.tools || []).map((x) => x.name));
  for (const name of expected) assert(directNames.has(name), "missing direct tool: " + name);
  assert(directNames.has("__vex_node_identity"), "missing node identity control");
  console.log("PASS direct tool parity " + directNames.size);

  console.log("STEP direct get_config");
  const directConfig = await timed(direct.client.callTool({ name: "get_config", arguments: {} }), "direct get_config", 20000);
  assert(Array.isArray(directConfig.content), "direct get_config returned no content");
  console.log("PASS direct get_config");

  await closePair(direct, "direct");
  direct = null;

  console.log("STEP start authenticated node HTTP gateway");
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

  let gatewayStdout = "";
  let gatewayStderr = "";
  gateway.stdout.on("data", (d) => { gatewayStdout += d.toString(); });
  gateway.stderr.on("data", (d) => { gatewayStderr += d.toString(); });
  await wait(3500);
  assert.equal(gateway.exitCode, null, "node HTTP gateway exited early: " + gatewayStderr.slice(-1600));
  console.log("PASS gateway process alive");

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

  console.log("STEP hub list_tools");
  const hubTools = await timed(hub.client.listTools(), "hub list_tools", 30000);
  const hubMap = new Map((hubTools.tools || []).map((x) => [x.name, x]));
  for (const name of ["list_devices", "who_am_i", "ping", "shutdown", ...expected]) {
    assert(hubMap.has(name), "missing hub tool: " + name);
  }
  for (const name of expected) {
    const schema = hubMap.get(name).inputSchema || {};
    assert(schema.properties && schema.properties.deviceId, "deviceId not injected for " + name);
    assert(Array.isArray(schema.required) && schema.required.includes("deviceId"), "deviceId not required for " + name);
  }
  console.log("PASS hub tool parity " + hubMap.size);

  console.log("STEP hub list_devices");
  const devicesResult = await timed(hub.client.callTool({ name: "list_devices", arguments: {} }), "hub list_devices", 20000);
  const devicesText = (devicesResult.content || []).find((x) => x.type === "text")?.text || "{}";
  const devices = JSON.parse(devicesText).devices || [];
  assert.equal(devices.length, 1, "hub did not return exactly one CI node");
  assert.equal(devices[0].deviceId, "ci-node-1", "hub did not preserve node device ID");
  assert.equal(devices[0].online, true, "CI node was not online");
  console.log("PASS hub list_devices");

  console.log("STEP routed get_config");
  const routedConfig = await timed(hub.client.callTool({ name: "get_config", arguments: { deviceId: "ci-node-1" } }), "routed get_config", 20000);
  assert(Array.isArray(routedConfig.content), "hub routed get_config returned no content");
  console.log("PASS routed get_config");

  console.log("STEP routed ping");
  const pingResult = await timed(hub.client.callTool({ name: "ping", arguments: { deviceId: "ci-node-1" } }), "routed ping", 20000);
  const pingText = (pingResult.content || []).find((x) => x.type === "text")?.text || "{}";
  assert.equal(JSON.parse(pingText).deviceId, "ci-node-1", "hub ping routed to wrong node");
  console.log("PASS routed ping");

  console.log("PASS Vex Desktop Parity v0.15.6: upstream tool proxy + authenticated multi-device routing");
} finally {
  clearTimeout(guard);
  await closePair(hub, "hub");
  await closePair(direct, "direct-final");

  if (gateway && gateway.exitCode === null) {
    console.log("STEP stop gateway tree");
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/PID", String(gateway.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      gateway.kill("SIGKILL");
    }
  }

  for (const name of ["node-config.json", "nodes.json", "node-disabled.flag"]) {
    try { fs.rmSync(path.join(ROOT, name), { force: true }); } catch {}
  }
}
