import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const HUB_DIR = path.dirname(fileURLToPath(import.meta.url)); // dashboard_hub/hub
const ROOT_DIR = path.resolve(HUB_DIR, '..'); // dashboard_hub
const REGISTRY = path.join(ROOT_DIR, 'dashboards.json');

interface RegistryEntry {
  id: string;
  status: string;
  port?: number;
}

const registry = JSON.parse(readFileSync(REGISTRY, 'utf8')) as {
  basePrefix: string;
  sections: { dashboards: RegistryEntry[] }[];
};

const allDashboards = registry.sections.flatMap((section) => section.dashboards);

const prefix = (registry.basePrefix ?? '/d').replace(/\/$/, '');

// One proxy entry per dashboard that has its own Streamlit process, so the hub
// and the dashboards share an origin and the iframes are not cross-site. `ws: true`
// is required: Streamlit pushes every rerender over a websocket.
//
// This prefix is reserved for the dashboards — the hub's own client routes live
// under /s/* so the proxy never swallows them.
const proxy = Object.fromEntries([
  ...allDashboards
    .filter((entry) => entry.status === 'stub' && entry.port)
    .map((entry) => [
      `${prefix}/${entry.id}`,
      { target: `http://localhost:${entry.port}`, changeOrigin: true, ws: true },
    ]),
  // Data for the hub's own native pages. Yahoo rejects direct browser calls, so
  // this goes through the Python market API rather than out from the client.
  ['/api/market', { target: 'http://localhost:8600', changeOrigin: true }],
]);

export default defineConfig({
  plugins: [react()],
  // dashboards.json lives one level up, beside the dashboards themselves, so
  // Python, Vite and React all read the same file. The alias plus the fs.allow
  // below are what let an import reach outside this Vite root.
  resolve: { alias: { '@registry': REGISTRY } },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [ROOT_DIR] },
    proxy,
  },
});
