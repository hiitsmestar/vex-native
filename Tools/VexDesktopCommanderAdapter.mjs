import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const VERSION = '0.1.0';
const PORT = Number(process.env.VEX_DC_ADAPTER_PORT || 8776);
const home = os.homedir();
const logPath = path.join(home, 'AppData', 'Roaming', 'VexBridge', 'desktop-commander-audit.jsonl');
fs.mkdirSync(path.dirname(logPath), { recursive: true });

const where = execFileSync('where.exe', ['desktop-commander.cmd'], { encoding: 'utf8' })
  .split(/\r?\n/).map(x => x.trim()).filter(Boolean)[0];
if (!where) throw new Error('desktop-commander.cmd not found on PATH');
const nodeModules = path.dirname(path.dirname(where));
const sdkClient = path.join(nodeModules, '@modelcontextprotocol', 'sdk', 'dist', 'esm', 'client', 'index.js');
const sdkStdio = path.join(nodeModules, '@modelcontextprotocol', 'sdk', 'dist', 'esm', 'client', 'stdio.js');
const { Client } = await import(pathToFileURL(sdkClient).href);
const { StdioClientTransport } = await import(pathToFileURL(sdkStdio).href);

const READ_ONLY = new Set([
  'get_config', 'read_file', 'read_multiple_files', 'list_directory', 'get_file_info',
  'list_processes', 'list_sessions', 'list_searches', 'get_more_search_results'
]);
const ROOTS = [
  path.join(home, 'Documents'), path.join(home, 'Downloads'), path.join(home, 'Desktop'),
  path.join(home, 'AppData', 'Roaming', 'VexBridge'), path.join(home, 'AppData', 'Roaming', 'VexWindows')
];
if (fs.existsSync('G:\\VexModels')) ROOTS.push('G:\\VexModels');

const audit = (event, data = {}) => fs.appendFileSync(
  logPath, JSON.stringify({ time: new Date().toISOString(), event, ...data }) + '\n'
);
const insideRoots = value => {
  if (typeof value !== 'string' || !/^[A-Za-z]:\\/.test(value)) return true;
  const candidate = path.win32.resolve(value).toLowerCase();
  return ROOTS.some(root => candidate === root.toLowerCase() || candidate.startsWith(root.toLowerCase() + '\\'));
};
const argsAllowed = args => Object.entries(args || {}).every(([key, value]) => {
  if (['path', 'source', 'destination', 'file_path'].includes(key)) return insideRoots(value);
  if (key === 'paths' && Array.isArray(value)) return value.every(insideRoots);
  return true;
});

const client = new Client({ name: 'vexnative-desktop-commander-adapter', version: VERSION }, { capabilities: {} });
const transport = new StdioClientTransport({
  command: 'cmd.exe', args: ['/d', '/s', '/c', 'desktop-commander'], stderr: 'pipe'
});
await client.connect(transport);
const listed = await client.listTools();
const available = new Set(listed.tools.map(tool => tool.name));
audit('adapter_started', { port: PORT, available: [...available] });

const reply = (res, code, value) => {
  const body = JSON.stringify(value);
  res.writeHead(code, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) });
  res.end(body);
};

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    return reply(res, 200, { ok: true, backend: 'desktop-commander-mcp', version: VERSION, mode: 'read-only', toolCount: available.size });
  }
  if (req.method === 'GET' && req.url === '/capabilities') {
    return reply(res, 200, { ok: true, tools: [...READ_ONLY].filter(name => available.has(name)), roots: ROOTS });
  }
  if (req.method !== 'POST' || req.url !== '/call') return reply(res, 404, { ok: false, error: 'not found' });
  let raw = '';
  for await (const chunk of req) raw += chunk;
  let body;
  try { body = raw ? JSON.parse(raw) : {}; } catch { return reply(res, 400, { ok: false, error: 'bad json' }); }
  const tool = String(body.tool || '');
  const args = body.arguments || {};
  if (!READ_ONLY.has(tool) || !available.has(tool)) return reply(res, 403, { ok: false, error: 'tool not allowed', tool });
  if (!argsAllowed(args)) return reply(res, 403, { ok: false, error: 'path outside Vex adapter roots' });
  try {
    const result = await client.callTool({ name: tool, arguments: args });
    audit('call_ok', { tool });
    return reply(res, 200, { ok: true, backend: 'desktop-commander-mcp', tool, result });
  } catch (error) {
    audit('call_fail', { tool, error: String(error) });
    return reply(res, 500, { ok: false, error: String(error) });
  }
});
server.listen(PORT, '127.0.0.1', () => console.log(`Vex Desktop Commander adapter ${VERSION} listening on 127.0.0.1:${PORT}`));
process.on('SIGINT', async () => { try { await client.close(); } catch {} server.close(() => process.exit(0)); });
