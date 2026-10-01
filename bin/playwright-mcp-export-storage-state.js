// Merge Playwright storage state (cookies + localStorage) out of on-disk
// Chrome profiles (e.g. the old per-cwd ~/.cache/ms-playwright-mcp/mcp-chrome-*
// ones) into one file for playwright-stealth-mcp.service's --storage-state.
// usage: node ~/bin/playwright-mcp-export-storage-state.js \
//          ~/.config/playwright-mcp/stealth-storage-state.json WORKDIR PROFILE_DIR...
// Each profile's cookie/localStorage files (with any SQLite -journal/-wal, so
// a profile a live browser is writing still opens consistently) are COPIED
// into WORKDIR/<profile> first, so no live profile is ever touched; each copy
// holds live cookies and is deleted as soon as it has been read. The output
// is forced to 0600. Profiles are processed oldest-Cookies-mtime first so
// newer values win.
const fs = require('fs');
const path = require('path');

const USAGE = 'usage: playwright-mcp-export-storage-state.js OUT.json WORKDIR PROFILE_DIR...';
const [out, work, ...profiles] = process.argv.slice(2);
if (!out || !work || profiles.length === 0) {
  console.error(USAGE);
  process.exit(2);
}
if (!fs.existsSync(work) || !fs.statSync(work).isDirectory()) {
  console.error(`WORKDIR ${work} is not an existing directory\n${USAGE}`);
  process.exit(2);
}

const { chromium } = require(process.env.HOME + '/.local/share/playwright-mcp/node_modules/playwright-core');
const KEEP = ['Local State', 'Default/Cookies', 'Default/Local Storage', 'Default/Preferences'];
const SQLITE_SIDECARS = ['-journal', '-wal'];

(async () => {
  const withTime = profiles
    .filter(p => fs.existsSync(path.join(p, 'Default/Cookies')))
    .map(p => ({ p, t: fs.statSync(path.join(p, 'Default/Cookies')).mtimeMs }))
    .sort((a, b) => a.t - b.t);
  const cookies = new Map();
  const origins = new Map();
  for (const { p, t } of withTime) {
    const copy = path.join(work, path.basename(p));
    fs.rmSync(copy, { recursive: true, force: true });
    try {
      for (const rel of KEEP) {
        for (const suffix of ['', ...SQLITE_SIDECARS]) {
          const src = path.join(p, rel + suffix);
          if (fs.existsSync(src))
            fs.cpSync(src, path.join(copy, rel + suffix), { recursive: true });
        }
      }
      const ctx = await chromium.launchPersistentContext(copy, {
        executablePath: '/usr/bin/google-chrome', headless: true,
      });
      const st = await ctx.storageState();
      await ctx.close();
      for (const c of st.cookies) cookies.set(`${c.name}\t${c.domain}\t${c.path}`, c);
      for (const o of st.origins) origins.set(o.origin, o);
      console.error(`${path.basename(p)} (${new Date(t).toISOString()}): ${st.cookies.length} cookies, ${st.origins.length} origins`);
    } finally {
      fs.rmSync(copy, { recursive: true, force: true });
    }
  }
  const now = Date.now() / 1000;
  const live = [...cookies.values()].filter(c => c.expires === -1 || c.expires > now);
  fs.writeFileSync(out, JSON.stringify({ cookies: live, origins: [...origins.values()] }, null, 1), { mode: 0o600 });
  fs.chmodSync(out, 0o600);  // `mode` above only applies when creating the file
  console.error(`wrote ${out}: ${live.length} cookies (${cookies.size - live.length} expired dropped), ${origins.size} origins`);
})().catch(e => { console.error(e); process.exit(1); });
