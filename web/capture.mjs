import { spawn } from 'child_process';
import fs from 'fs';

async function main() {
  const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
    '--headless=new',
    '--user-data-dir=/tmp/chrome_cdp_profile',
    '--remote-debugging-port=9222',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--window-size=2048,1536'
  ]);

  let wsUrl = null;
  for (let i = 0; i < 25; i++) {
    await new Promise(r => setTimeout(r, 300));
    try {
      const res = await fetch('http://127.0.0.1:9222/json/version');
      const data = await res.json();
      wsUrl = data.webSocketDebuggerUrl;
      if (wsUrl) break;
    } catch {}
  }

  if (!wsUrl) {
    console.error('CDP failed');
    chrome.kill();
    return;
  }

  const ws = new WebSocket(wsUrl);
  let id = 1;
  const send = (method, params = {}) => {
    const msgId = id++;
    return new Promise((resolve, reject) => {
      const handler = (event) => {
        const data = JSON.parse(event.data);
        if (data.id === msgId) {
          ws.removeEventListener('message', handler);
          if (data.error) reject(data.error);
          else resolve(data.result);
        }
      };
      ws.addEventListener('message', handler);
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });
  };

  await new Promise(r => ws.addEventListener('open', r));

  const { targetId } = await send('Target.createTarget', { url: 'http://localhost:5173' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });

  const sendTarget = (method, params = {}) => {
    const msgId = id++;
    return new Promise((resolve, reject) => {
      const handler = (event) => {
        const data = JSON.parse(event.data);
        if (data.id === msgId) {
          ws.removeEventListener('message', handler);
          if (data.error) reject(data.error);
          else resolve(data.result);
        }
      };
      ws.addEventListener('message', handler);
      ws.send(JSON.stringify({ id: msgId, sessionId, method, params }));
    });
  };

  ws.addEventListener('message', (e) => {
    const d = JSON.parse(e.data);
    if (d.method === 'Runtime.consoleAPICalled') {
      console.log('CONSOLE:', d.params.type, d.params.args.map(a => a.value || a.description));
    }
    if (d.method === 'Runtime.exceptionThrown') {
      console.error('EXCEPTION:', d.params.exceptionDetails?.exception?.description || d.params.exceptionDetails);
    }
  });

  await sendTarget('Runtime.enable');
  await sendTarget('Page.enable');

  await new Promise(r => setTimeout(r, 3000));

  // Check DOM
  const domRes = await sendTarget('Runtime.evaluate', {
    expression: 'document.getElementById("root")?.innerHTML || document.body.innerHTML'
  });
  console.log('DOM HTML preview:', domRes.result?.value?.slice(0, 300));

  const shot = await sendTarget('Page.captureScreenshot', {
    format: 'png',
    clip: { x: 0, y: 0, width: 2048, height: 1536, scale: 1 }
  });

  fs.writeFileSync('public/live_dashboard_render.png', Buffer.from(shot.data, 'base64'));
  console.log('Screenshot saved! Size:', shot.data.length);

  ws.close();
  chrome.kill();
}

main().catch(console.error);
