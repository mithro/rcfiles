// Merge Playwright storage state (cookies + localStorage) out of on-disk
// Chrome profiles (e.g. the old per-cwd ~/.cache/ms-playwright-mcp/mcp-chrome-*
// ones) into one file for playwright-stealth-mcp.service's --storage-state.
// usage: node ~/bin/playwright-mcp-export-storage-state.js \
//          ~/.config/playwright-mcp/stealth-storage-state.json WORKDIR PROFILE_DIR...
// Each profile's cookie/localStorage files are COPIED into WORKDIR first (so a
// profile a live browser holds open is never touched) -- those copies contain
// live cookies: delete WORKDIR afterwards. Output is written 0600.
// Profiles are processed oldest-Cookies-mtime first so newer values win.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.HOME + '/.local/share/playwright-mcp/node_modules/playwright-core');

const [out, work, ...profiles] = process.argv.slice(2);
const KEEP = ['Local State', 'Default/Cookies', 'Default/Local Storage', 'Default/Preferences'];

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
    for (const rel of KEEP) {
      const src = path.join(p, rel);
      if (fs.existsSync(src))
        fs.cpSync(src, path.join(copy, rel), { recursive: true });
    }
    const ctx = await chromium.launchPersistentContext(copy, {
      executablePath: '/usr/bin/google-chrome', headless: true,
    });
    const st = await ctx.storageState();
    await ctx.close();
    for (const c of st.cookies) cookies.set(`${c.name}\t${c.domain}\t${c.path}`, c);
    for (const o of st.origins) origins.set(o.origin, o);
    console.error(`${path.basename(p)} (${new Date(t).toISOString()}): ${st.cookies.length} cookies, ${st.origins.length} origins`);
  }
  const now = Date.now() / 1000;
  const live = [...cookies.values()].filter(c => c.expires === -1 || c.expires > now);
  fs.writeFileSync(out, JSON.stringify({ cookies: live, origins: [...origins.values()] }, null, 1), { mode: 0o600 });
  console.error(`wrote ${out}: ${live.length} cookies (${cookies.size - live.length} expired dropped), ${origins.size} origins`);
})().catch(e => { console.error(e); process.exit(1); });
