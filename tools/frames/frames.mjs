// Frame test for Brain: scroll, open/close a tile and Settings, re-flow the board, and hover, in each theme, and record
//  (1) in-page frame times (requestAnimationFrame) -> fps, dropped frames (>25ms) and the worst frame, per step
//  (2) Chrome's own screencast frames -> saved to disk; diff.py flags pauses and boxes what changed
// Usage (Brain running on :4747; Chrome installed):
//   node tools/frames/frames.mjs <outdir> http://127.0.0.1:4747/ classic/dark riso/paper ...
// Phone app (serve the repo: python3 -m http.server 4849; uses your real phone/state.json):
//   PHONE=4 STATE=~/Notes/phone/state.json node tools/frames/frames.mjs <outdir> http://127.0.0.1:4849/mobile/index.html brain/dark
//   PHONE=<n> slows the CPU n times. CSS="..." injects a style first (for A/B tests, e.g. turning the grain off).
// Then: python3 tools/frames/diff.py <outdir>
// Known quirk: headless Chrome's screencast drops the first ~250ms of any CSS transition (a blank page does it too),
// so a gap right as a sheet opens is the harness, not Brain. Trust the rAF numbers for those.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const [out, base, ...themes] = process.argv.slice(2);
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = 9333;
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${out}/profile`,
  process.env.PHONE ? "--window-size=390,844" : "--window-size=1440,900", "--hide-scrollbars", "--enable-gpu", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));

let targets;
for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(200); } }
const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const wait = new Map(), handlers = [];
ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result ?? d); wait.delete(d.id); } else handlers.forEach(h => h(d)); };
const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJs = async expr => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.value;

await send("Page.enable");
const PHONE = process.env.PHONE;
if (PHONE) {
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 3, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true });
  await send("Emulation.setCPUThrottlingRate", { rate: +PHONE });
  await send("Page.navigate", { url: base }); await sleep(1500);
  const state = (await import("node:fs")).readFileSync(process.env.STATE, "utf8");
  await evalJs(`localStorage.setItem("brain.cfg", JSON.stringify({repo:"zacfink/notes-offline",token:"x"}));localStorage.setItem("brain.state", ${JSON.stringify(state)});0`);
}
const report = {};
for (const theme of themes) {
  const dir = `${out}/${theme.replace("/", "-")}`; mkdirSync(dir, { recursive: true });
  await send("Page.navigate", { url: `${base}?theme=${theme}` });
  await sleep(3000);
  if (process.env.CSS) await evalJs(`document.head.insertAdjacentHTML("beforeend", "<style>" + ${JSON.stringify(process.env.CSS)} + "</style>");0`), await sleep(500);
  const frames = [];
  const onFrame = d => {
    if (d.method !== "Page.screencastFrame") return;
    const { data, metadata, sessionId } = d.params;
    frames.push(metadata.timestamp); writeFileSync(`${dir}/${String(frames.length).padStart(4, "0")}.jpg`, Buffer.from(data, "base64"));
    send("Page.screencastFrameAck", { sessionId });
  };
  handlers.push(onFrame);
  await evalJs(`window.__f=[];window.__mark=[];(function t(n){__f.push(n);requestAnimationFrame(t)})(performance.now());0`);
  await send("Page.startScreencast", { format: "jpeg", quality: 40, everyNthFrame: 1, maxWidth: 720, maxHeight: 450 });
  // Act 1: smooth scroll down then up (wheel ticks every 16ms)
  await evalJs(`__mark.push(["scroll",performance.now()])`);
  const y0 = await evalJs("scrollY");
  if (PHONE) {
    await send("Input.synthesizeScrollGesture", { x: 195, y: 600, yDistance: -2500, speed: 2500, gestureSourceType: "touch" });
    await send("Input.synthesizeScrollGesture", { x: 195, y: 300, yDistance: 2500, speed: 2500, gestureSourceType: "touch" });
    await evalJs(`__mark.push(["swipe",performance.now()])`);
    await send("Input.synthesizeScrollGesture", { x: 330, y: 260, xDistance: -900, yDistance: 0, speed: 1800, gestureSourceType: "touch" });
  } else for (let i = 0; i < 90; i++) { await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: 700, y: 500, deltaX: 0, deltaY: i < 45 ? 60 : -60 }); await sleep(16); }
  await sleep(400);
  console.log("  max scroll", await evalJs("document.documentElement.scrollHeight-innerHeight"));
  // Act 2: open and close a tile (it grows from its spot), then Settings (theme picker inside)
  const close = `(document.getElementById("pageDone") || document.querySelector("#page [data-close]")).click()`;
  await evalJs(`scrollTo(0,0);__mark.push(["open",performance.now()]);document.querySelectorAll("#board .bt .bt-part, #board .pt")[1].click()`); await sleep(900);
  await evalJs(`__mark.push(["close",performance.now()]);${close}`); await sleep(900);
  if (PHONE) { await evalJs(`__mark.push(["settings",performance.now()]);document.getElementById("openSettings").click()`); await sleep(900);
    await evalJs(`document.querySelector("#settings [data-close]").click()`); }
  else { await evalJs(`__mark.push(["settings",performance.now()]);document.getElementById("settingsBtn").click()`); await sleep(900); await evalJs(`document.getElementById("setClose").click()`); }
  await sleep(700);
  // Act 3: re-flow (the cover length changes, every piece glides to its new spot)
  await evalJs(`__mark.push(["reflow",performance.now()]);document.querySelector('${PHONE ? "[data-lay=cover][data-v=long]" : "#segCover [data-v=long]"}').click()`); await sleep(1000);
  await evalJs(`document.querySelector('${PHONE ? "[data-lay=cover][data-v=medium]" : "#segCover [data-v=medium]"}').click()`);
  await evalJs(`__mark.push(["hover",performance.now()])`);
  for (let i = 0; i < 60; i++) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 100 + i * 20, y: 300 + (i % 10) * 30 }); await sleep(16); }
  await sleep(300);
  await send("Page.stopScreencast");
  handlers.splice(handlers.indexOf(onFrame), 1);
  const { f, mark } = await evalJs(`({f:__f,mark:__mark})`);
  const gaps = f.slice(1).map((t, i) => t - f[i]);
  const acts = mark.map(([name, start], i) => {
    const end = mark[i + 1]?.[1] ?? f.at(-1);
    const g = gaps.filter((_, k) => f[k] >= start && f[k] < end);
    return { name, fps: +(1000 * g.length / (end - start)).toFixed(1), dropped: g.filter(x => x > 25).length, worst: +Math.max(...g).toFixed(1) };
  });
  report[theme] = { acts, screencast: frames.length, scrolled: await evalJs("scrollY") };
  writeFileSync(`${dir}/times.json`, JSON.stringify({ frames, mark: mark.map(([n, t]) => [n, t]), rafStart: f[0], wall: await evalJs("performance.timeOrigin/1000") }));
  console.log(theme, JSON.stringify(acts));
}
writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 1));
ws.close(); chrome.kill();
