// SVG -> PNG with headless Chromium (exact SVG filters, transparency kept).
//   node branding/rasterize.cjs jobs.json   where jobs = [{ svg: "<svg…>" | file, out, w, h }]
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const b = await chromium.launch(); const p = await b.newPage();
  for (const j of jobs) {
    const svg = j.svg.trim().startsWith('<') ? j.svg : fs.readFileSync(j.svg, 'utf8');
    await p.setViewportSize({ width: j.w, height: j.h });
    await p.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
    await p.screenshot({ path: j.out, omitBackground: true, clip: { x: 0, y: 0, width: j.w, height: j.h } });
  }
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
