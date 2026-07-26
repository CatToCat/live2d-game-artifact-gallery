// 为缺少现成头像图标(_icon.png)的角色，用无头浏览器渲染 Spine 生成缩略图。
//
// 依赖：本地已启动 http server（在仓库根目录），viewer 可访问；playwright + chromium。
// 用法：
//   node gen_thumbs.mjs <baseUrl> <dataDir> <id1> <id2> ...
//   例：node gen_thumbs.mjs http://127.0.0.1:8899 ../data azxservicetime_1 ...
//
// 若不带 id，则读取 manifest，自动为所有缺 _icon.png 的角色生成。
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const baseUrl = process.argv[2] || 'http://127.0.0.1:8899';
const dataDir = path.resolve(process.argv[3] || path.join(__dirname, '..', 'data'));
let ids = process.argv.slice(4);

// 允许通过环境变量指定 chromium（playwright 版本不匹配时）
const launchOpts = {};
if (process.env.CHROMIUM_PATH) launchOpts.executablePath = process.env.CHROMIUM_PATH;

if (ids.length === 0) {
  // 自动挑选缺 _icon.png 的角色
  const manifest = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', 'viewer', 'nikke_manifest.json'), 'utf-8')
  );
  ids = manifest.characters
    .map((c) => c.id)
    .filter((id) => !fs.existsSync(path.join(dataDir, id, '_icon.png')));
  console.log(`自动选取缺图标角色 ${ids.length} 个`);
}

const b = await chromium.launch(launchOpts);
const page = await b.newPage();
await page.setViewportSize({ width: 800, height: 900 });

let ok = 0;
for (const id of ids) {
  try {
    await page.goto(`${baseUrl}/nikke/viewer/index.html`, { waitUntil: 'networkidle' });
    await page.waitForSelector('.card', { timeout: 15000 });
    await page.fill('#search', id);
    await page.waitForTimeout(400);
    const clicked = await page.evaluate((cid) => {
      const cards = [...document.querySelectorAll('.card')];
      const c = cards.find((x) => x.querySelector('.name')?.textContent.includes(cid)) || cards[0];
      if (c) { c.click(); return true; }
      return false;
    }, id);
    if (!clicked) { console.log(id, 'NOCARD'); continue; }

    await page
      .waitForFunction(() => {
        const cv = [...document.querySelectorAll('#player-container canvas')].pop();
        return cv && cv.width > 400;
      }, { timeout: 20000 })
      .catch(() => {});
    await page.waitForTimeout(3500);

    const dataUrl = await page.evaluate(() => {
      const cv = [...document.querySelectorAll('#player-container canvas')].pop();
      if (!cv) return null;
      const t = document.createElement('canvas');
      t.width = cv.width; t.height = cv.height;
      const cx = t.getContext('2d'); cx.drawImage(cv, 0, 0);
      const { data } = cx.getImageData(0, 0, t.width, t.height);
      let minX = t.width, minY = t.height, maxX = 0, maxY = 0, found = false;
      for (let y = 0; y < t.height; y++)
        for (let x = 0; x < t.width; x++) {
          if (data[(y * t.width + x) * 4 + 3] > 24) {
            found = true;
            if (x < minX) minX = x; if (x > maxX) maxX = x;
            if (y < minY) minY = y; if (y > maxY) maxY = y;
          }
        }
      if (!found) return null;
      const pad = 12;
      minX = Math.max(0, minX - pad); minY = Math.max(0, minY - pad);
      maxX = Math.min(t.width - 1, maxX + pad); maxY = Math.min(t.height - 1, maxY + pad);
      const w = maxX - minX + 1, h = maxY - minY + 1;
      const out = document.createElement('canvas');
      out.width = w; out.height = h;
      out.getContext('2d').drawImage(t, minX, minY, w, h, 0, 0, w, h);
      return out.toDataURL('image/png');
    });
    if (!dataUrl) { console.log(id, 'EMPTY'); continue; }
    const buf = Buffer.from(dataUrl.split(',')[1], 'base64');
    fs.mkdirSync(path.join(dataDir, id), { recursive: true });
    fs.writeFileSync(path.join(dataDir, id, '_icon.png'), buf);
    ok++;
    console.log(id, 'OK', buf.length);
  } catch (e) {
    console.log(id, 'ERR', e.message);
  }
}
console.log(`\n完成 ${ok}/${ids.length}`);
await b.close();
