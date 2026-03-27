/**
 * MCP IA Desktop — Electron Main Process
 * Sert le dashboard via un serveur HTTP local embarqué
 * pour éviter tous les problèmes file:// (CSP, chemins absolus, SW, CDN)
 */

const { app, BrowserWindow, Menu, Tray, shell, ipcMain } = require('electron');
const path   = require('path');
const { spawn, exec } = require('child_process');
const http   = require('http');
const fs     = require('fs');
const url    = require('url');

// ─── Store simplifié ─────────────────────────────────────────────────────────
class SimpleStore {
  constructor() {
    this.file = path.join(app.getPath('userData'), 'preferences.json');
    try { this._data = JSON.parse(fs.readFileSync(this.file, 'utf8')); }
    catch { this._data = {}; }
  }
  get(key) { return this._data[key]; }
  set(key, value) {
    this._data[key] = value;
    fs.writeFileSync(this.file, JSON.stringify(this._data, null, 2));
  }
}
const store = new SimpleStore();

// ─── Configuration ───────────────────────────────────────────────────────────
const PYTHON_PORT  = 8000;   // FastAPI backend Python
const STATIC_PORT  = 8080;   // Serveur statique embarqué
const DEV_MODE     = process.env.NODE_ENV === 'development';
const APP_NAME     = 'MCP IA';

let mainWindow   = null;
let splashWindow = null;
let tray         = null;
let apiProcess   = null;
let apiReady     = false;
let staticServer = null;

// ─── Chemins ressources ──────────────────────────────────────────────────────
function getResourcePath(...parts) {
  if (DEV_MODE) return path.join(__dirname, '..', ...parts);
  return path.join(process.resourcesPath, ...parts);
}

// ─── Serveur HTTP statique embarqué ─────────────────────────────────────────
// Sert saas/frontend/ sur http://localhost:STATIC_PORT
// Résout tous les problèmes file:// (manifest, icons, sw.js, chemins absolus)
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.ico':  'image/x-icon',
  '.svg':  'image/svg+xml',
  '.woff2':'font/woff2',
};

function startStaticServer() {
  return new Promise((resolve) => {
    const frontendDir = getResourcePath('saas', 'frontend');

    staticServer = http.createServer((req, res) => {
      let reqPath = url.parse(req.url).pathname;
      if (reqPath === '/' || reqPath === '') reqPath = '/dashboard.html';

      const filePath = path.join(frontendDir, reqPath);
      const ext = path.extname(filePath).toLowerCase();

      fs.readFile(filePath, (err, data) => {
        if (err) {
          // Fallback: toujours servir le dashboard
          const index = path.join(frontendDir, 'dashboard.html');
          fs.readFile(index, (e2, d2) => {
            if (e2) { res.writeHead(404); res.end('Not found'); return; }
            res.writeHead(200, { 'Content-Type': MIME['.html'] });
            res.end(d2);
          });
          return;
        }
        res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
        res.end(data);
      });
    });

    staticServer.listen(STATIC_PORT, '127.0.0.1', () => {
      console.log(`[MCP IA] Serveur statique → http://localhost:${STATIC_PORT}`);
      resolve();
    });

    staticServer.on('error', (err) => {
      console.error('[Static] Erreur serveur:', err.message);
      resolve(); // continuer même si ça échoue
    });
  });
}

// ─── Backend Python (FastAPI) ────────────────────────────────────────────────
function startBackend() {
  return new Promise((resolve) => {
    const saasPath  = getResourcePath('saas', 'backend', 'main.py');
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const apiKey    = store.get('anthropic_api_key') || process.env.ANTHROPIC_API_KEY || '';

    if (!fs.existsSync(saasPath)) {
      console.warn('[MCP IA] main.py introuvable — mode démo');
      resolve(); return;
    }

    const env = { ...process.env, ANTHROPIC_API_KEY: apiKey, PORT: String(PYTHON_PORT) };

    apiProcess = spawn(pythonCmd, ['-u', saasPath], {
      env,
      cwd: getResourcePath('saas', 'backend'),
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    const onData = (data) => {
      const msg = data.toString();
      if (msg.includes('Uvicorn running') || msg.includes('Started server process') || msg.includes('Application startup')) {
        apiReady = true;
        resolve();
      }
    };
    apiProcess.stdout.on('data', onData);
    apiProcess.stderr.on('data', onData);
    apiProcess.on('error', () => resolve()); // python3 absent → mode démo silencieux
    setTimeout(() => { if (!apiReady) resolve(); }, 12000);
  });
}

function waitForPort(port, maxTries = 20) {
  return new Promise((resolve) => {
    let tries = 0;
    const check = () => {
      const req = http.get(`http://localhost:${port}/api/stats`, () => resolve(true));
      req.on('error', () => { if (++tries < maxTries) setTimeout(check, 500); else resolve(false); });
      req.setTimeout(500, () => { req.destroy(); if (++tries < maxTries) setTimeout(check, 500); else resolve(false); });
    };
    check();
  });
}

// ─── Déterminer l'URL à charger ──────────────────────────────────────────────
function getAppURL() {
  if (apiReady) return `http://localhost:${PYTHON_PORT}`;
  return `http://localhost:${STATIC_PORT}`;
}

// ─── Splash ──────────────────────────────────────────────────────────────────
function createSplash() {
  splashWindow = new BrowserWindow({
    width: 480, height: 320,
    frame: false, transparent: true, alwaysOnTop: true,
    webPreferences: { contextIsolation: true },
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.center();
}

// ─── Fenêtre principale ──────────────────────────────────────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280, height: 800,
    minWidth: 900, minHeight: 600,
    show: false, title: APP_NAME,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const appURL = getAppURL();
  console.log(`[MCP IA] Chargement → ${appURL}`);
  mainWindow.loadURL(appURL);

  mainWindow.webContents.on('did-fail-load', (e, code, desc) => {
    console.warn('[MCP IA] Échec chargement:', desc, '— repli sur serveur statique');
    mainWindow.loadURL(`http://localhost:${STATIC_PORT}`);
  });

  mainWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close(); splashWindow = null;
    }
    mainWindow.show();
    if (DEV_MODE) mainWindow.webContents.openDevTools();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
  mainWindow.webContents.setWindowOpenHandler(({ url: u }) => {
    shell.openExternal(u); return { action: 'deny' };
  });

  buildMenu();
}

// ─── Menu ────────────────────────────────────────────────────────────────────
function buildMenu() {
  const isMac = process.platform === 'darwin';
  const nav = (p) => () => mainWindow?.loadURL(`${getAppURL()}${p}`);
  const tmpl = [
    ...(isMac ? [{ label: APP_NAME, submenu: [
      { role: 'about', label: `À propos de ${APP_NAME}` },
      { type: 'separator' },
      { label: 'Préférences…', accelerator: 'Cmd+,', click: openPreferences },
      { type: 'separator' },
      { role: 'quit', label: 'Quitter MCP IA' },
    ]}] : []),
    { label: 'Modules', submenu: [
      { label: '🧠 Assistant IA',  click: nav('/') },
      { label: '💹 Finance',        click: nav('/?page=finance') },
      { label: '🖥 Surveillance',    click: nav('/?page=surveillance') },
      { label: '🔔 Alertes',        click: nav('/?page=alerts') },
      { type: 'separator' },
      { label: 'Recharger', role: 'reload', accelerator: 'CmdOrCtrl+R' },
    ]},
    { label: 'Affichage', submenu: [
      { role: 'togglefullscreen', label: 'Plein écran' },
      { role: 'zoomin',    label: 'Zoom +', accelerator: 'CmdOrCtrl+=' },
      { role: 'zoomout',   label: 'Zoom -', accelerator: 'CmdOrCtrl+-' },
      { role: 'resetzoom', label: 'Zoom normal' },
    ]},
    { label: 'Aide', submenu: [
      { label: 'Documentation', click: () => shell.openExternal('https://github.com/tino-le-doc/Serveur-MPC-IA-') },
      { label: 'API Anthropic',  click: () => shell.openExternal('https://console.anthropic.com') },
      ...(!isMac ? [{ type: 'separator' }, { label: 'Préférences…', click: openPreferences }] : []),
    ]},
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(tmpl));
}

// ─── Préférences ─────────────────────────────────────────────────────────────
let prefsWindow = null;
function openPreferences() {
  if (prefsWindow) { prefsWindow.focus(); return; }
  prefsWindow = new BrowserWindow({
    width: 500, height: 320, title: 'Préférences — MCP IA',
    resizable: false, modal: true, parent: mainWindow,
    backgroundColor: '#1a1d27',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  });
  const current = store.get('anthropic_api_key') || '';
  prefsWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!DOCTYPE html><html style="background:#1a1d27;color:#e2e8f0;font-family:system-ui;padding:2rem">
    <h2 style="margin-bottom:1rem">Preferences</h2>
    <label style="font-size:.85rem;color:#64748b">Cle API Anthropic</label>
    <input id="key" type="password" value="${current}"
      style="width:100%;padding:.6rem;background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;color:#e2e8f0;font-size:.9rem;margin-top:.4rem">
    <div style="margin-top:.5rem;font-size:.8rem;color:#64748b">
      Obtenez votre cle sur <a href="#" onclick="open('https://console.anthropic.com')" style="color:#6c63ff">console.anthropic.com</a>
    </div>
    <button onclick="save()" style="margin-top:1.5rem;padding:.65rem 1.4rem;background:#6c63ff;color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:600">
      Enregistrer
    </button>
    <script>function save(){window.electronAPI.savePref('anthropic_api_key',document.getElementById('key').value);window.close();}</script>
    </html>
  `)}`);
  prefsWindow.on('closed', () => { prefsWindow = null; });
}

// ─── Tray ────────────────────────────────────────────────────────────────────
function createTray() {
  const iconPath = path.join(__dirname, 'assets',
    process.platform === 'win32' ? 'icon.ico' : 'icon.png');
  if (!fs.existsSync(iconPath)) return;
  tray = new Tray(iconPath);
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Ouvrir MCP IA', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    { type: 'separator' },
    { label: 'Quitter', click: () => app.quit() },
  ]));
  tray.on('click', () => { mainWindow?.show(); mainWindow?.focus(); });
}

// ─── IPC ─────────────────────────────────────────────────────────────────────
ipcMain.handle('save-pref',   (_, k, v) => store.set(k, v));
ipcMain.handle('get-pref',    (_, k)    => store.get(k));
ipcMain.handle('get-api-url', ()        => `http://localhost:${PYTHON_PORT}`);

// ─── Lifecycle ───────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  createSplash();
  createTray();

  // Démarrer serveur statique EN PREMIER (toujours disponible)
  await startStaticServer();

  // Tenter de démarrer Python en parallèle (optionnel)
  await Promise.race([
    startBackend().then(() => waitForPort(PYTHON_PORT)),
    new Promise(r => setTimeout(r, 10000)), // max 10s d'attente
  ]);

  createMainWindow();
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => {
  if (app.isReady()) {
    if (!mainWindow) createMainWindow(); else mainWindow.show();
  }
});
app.on('before-quit', () => {
  staticServer?.close();
  if (apiProcess) {
    try {
      process.platform === 'win32'
        ? exec(`taskkill /pid ${apiProcess.pid} /f /t`)
        : apiProcess.kill('SIGTERM');
    } catch {}
  }
});
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, navUrl) => {
    const isLocal = navUrl.startsWith(`http://localhost:${PYTHON_PORT}`) ||
                    navUrl.startsWith(`http://localhost:${STATIC_PORT}`) ||
                    navUrl.startsWith('data:');
    if (!isLocal) { event.preventDefault(); shell.openExternal(navUrl); }
  });
});
