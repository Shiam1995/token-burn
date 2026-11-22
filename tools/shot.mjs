// Real-time screenshot via Chrome DevTools Protocol.
// usage: node shot.mjs URL out.png [W=1300] [H=800] [waitMs=4000] [mobile] [gpu]
// Several shots: waitMs can be "2000,6000,15000" -> out-2000.png, out-6000.png ...
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [url, out, W = '1300', H = '800', waitArg = '4000', ...flags] = process.argv.slice(2);
if (!url || !out) { console.error('usage: node shot.mjs URL out.png [W] [H] [waitMs[,ms..]] [mobile] [gpu]'); process.exit(2); }
const mobile = flags.includes('mobile');
const gpu = flags.includes('gpu');
const waits = String(waitArg).split(',').map(Number);
const dir = mkdtempSync(join(process.env.TB_TMP || tmpdir(), 'tbshot-'));
const port = 9300 + Math.floor(Math.random() * 600);
const args = ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`,
  '--no-first-run', '--hide-scrollbars', '--mute-audio', '--window-size=1400,1000',
  ...(gpu ? ['--use-angle=vulkan', '--enable-gpu', '--ignore-gpu-blocklist'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']),
  'about:blank'];
const chrome = spawn('google-chrome', args, { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pend = new Map(); const logs = [];
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const i = ++id; pend.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method, params, ...(sessionId ? { sessionId } : {}) }));
});
try {
  let ver;
  for (let t = 0; t < 60 && !ver; t++) { await sleep(200); try { ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch {} }
  ws = new WebSocket(ver.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    else if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) logs.push(m.params.type + ': ' + m.params.args.map(a => a.value ?? a.description).join(' '));
    else if (m.method === 'Runtime.exceptionThrown') logs.push('EXCEPTION: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
  };
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId: s } = await send('Target.attachToTarget', { targetId, flatten: true });
  await send('Runtime.enable', {}, s); await send('Page.enable', {}, s);
  await send('Emulation.setDeviceMetricsOverride', { width: +W, height: +H, deviceScaleFactor: mobile ? 2 : 1, mobile }, s);
  if (mobile) await send('Emulation.setTouchEmulationEnabled', { enabled: true }, s);
  await send('Page.navigate', { url }, s);
  let last = 0;
  for (const w of waits) {
    await sleep(w - last); last = w;
    const { data } = await send('Page.captureScreenshot', { format: 'png' }, s);
    const f = waits.length > 1 ? out.replace(/\.png$/, `-${w}.png`) : out;
    writeFileSync(f, Buffer.from(data, 'base64')); console.log('wrote', f);
  }
  const { result } = await send('Runtime.evaluate', { expression: 'document.documentElement.scrollWidth+"x"+document.documentElement.scrollHeight', returnByValue: true }, s);
  console.log('page size', result.value);
  if (logs.length) console.log('CONSOLE:\n' + logs.join('\n')); else console.log('console clean');
} catch (e) { console.error('shot failed:', e.message); process.exitCode = 1; }
finally { try { ws?.close(); } catch {} chrome.kill('SIGKILL'); await sleep(300); try { rmSync(dir, { recursive: true, force: true }); } catch {} }
