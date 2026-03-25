/**
 * MCP IA Desktop — Electron Main Process
 * Démarre le backend FastAPI Python, puis ouvre la fenêtre Electron
 */

const { app, BrowserWindow, Menu, Tray, shell, dialog, ipcMain } = require('electron');
const path  = require('path');
const { spawn, exec } = require('child_process');
const http  = require('http');
const fs    = require('fs');

// ─── Store simplifié (remplace electron-store ESM) ──────────────────────────
class SimpleStore {
  constructor() {
    this.file = path.join(app.getPath('userData'), 'preferences.json');
    try {
      this._data = JSON.parse(fs.readFileSync(this.file, 'utf8'));
    } catch {
      this._data = {};
    }
  }
  get(key) { return this._data[key]; }
  set(key, value) {
    this._data[key] = value;
    fs.writeFileSync(this.file, JSON.stringify(this._data, null, 2));
  }
}

const store = new SimpleStore();

// ─── Configuration ───────────────────────────
const PORT     = 8000;
const DEV_MODE = process.env.NODE_ENV === 'development';
const APP_NAME = 'MCP IA';

let mainWindow   = null;
let splashWindow = null;
let tray         = null;
let apiProcess   = null;
let apiReady     = false;

// ─── Chemins ─────────────────────────────────
function getResourcePath(...parts) {
  if (DEV_MODE) {
    return path.join(__dirname, '..', ...parts);
  }
  return path.join(process.resourcesPath, ...parts);
}

// ─── Démarrer le backend Python (FastAPI) ────
function startBackend() {
  return new Promise((resolve, reject) => {
    const saasPath  = getResourcePath('saas', 'backend', 'main.py');
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const apiKey    = store.get('anthropic_api_key') || process.env.ANTHROPIC_API_KEY || '';

    console.log(`[MCP IA] Démarrage backend : ${saasPath}`);

    const env = {
      ...process.env,
      ANTHROPIC_API_KEY: apiKey,
      PORT: String(PORT),
    };

    apiProcess = spawn(pythonCmd, ['-u', saasPath], {
      env,
      cwd: getResourcePath('saas', 'backend'),
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    apiProcess.stdout.on('data', (data) => {
      const msg = data.toString();
      console.log('[API]', msg.trim());
      if (msg.includes('Uvicorn running') || msg.includes('Application startup complete')) {
        apiReady = true;
        resolve();
      }
    });

    apiProcess.stderr.on('data', (data) => {
      const msg = data.toString();
      console.error('[API ERR]', msg.trim());
      // uvicorn écrit sur stderr même sans erreur
      if (msg.includes('Uvicorn running') || msg.includes('Started server process')) {
        apiReady = true;
        resolve();
      }
    });

    apiProcess.on('error', (err) => {
      console.error('[API] Impossible de démarrer Python :', err.message);
      reject(err);
    });

    // Timeout de secours : 15 secondes max
    setTimeout(() => {
      if (!apiReady) resolve();
    }, 15000);
  });
}

// Attendre que le port soit disponible
function waitForPort(port, maxTries = 30) {
  return new Promise((resolve) => {
    let tries = 0;
    const check = () => {
      const req = http.get(`http://localhost:${port}/api/stats`, (res) => {
        resolve(true);
      });
      req.on('error', () => {
        tries++;
        if (tries < maxTries) setTimeout(check, 500);
        else resolve(false);
      });
      req.setTimeout(500, () => {
        req.destroy();
        tries++;
        if (tries < maxTries) setTimeout(check, 500);
        else resolve(false);
      });
    };
    check();
  });
}

// ─── Splash Screen ───────────────────────────
function createSplash() {
  splashWindow = new BrowserWindow({
    width: 480,
    height: 320,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    webPreferences: { contextIsolation: true },
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.center();
}

// ─── Fenêtre principale ──────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    title: APP_NAME,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(`http://localhost:${PORT}`);

  mainWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
    mainWindow.show();
    if (DEV_MODE) mainWindow.webContents.openDevTools();
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  buildMenu();
}

// ─── Menu application ────────────────────────
function buildMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{
      label: APP_NAME,
      submenu: [
        { role: 'about', label: `À propos de ${APP_NAME}` },
        { type: 'separator' },
        { label: 'Préférences…', accelerator: 'Cmd+,', click: openPreferences },
        { type: 'separator' },
        { role: 'quit', label: 'Quitter MCP IA' },
      ],
    }] : []),
    {
      label: 'Modules',
      submenu: [
        { label: '🧠 Assistant IA',  click: () => navigate('/') },
        { label: '💹 Finance',        click: () => navigate('/?page=finance') },
        { label: '🖥 Surveillance',    click: () => navigate('/?page=surveillance') },
        { label: '🔔 Alertes',        click: () => navigate('/?page=alerts') },
        { type: 'separator' },
        { label: 'Recharger', role: 'reload', accelerator: 'CmdOrCtrl+R' },
      ],
    },
    {
      label: 'Affichage',
      submenu: [
        { role: 'togglefullscreen', label: 'Plein écran' },
        { role: 'zoomin',    label: 'Zoom +', accelerator: 'CmdOrCtrl+=' },
        { role: 'zoomout',   label: 'Zoom -', accelerator: 'CmdOrCtrl+-' },
        { role: 'resetzoom', label: 'Zoom normal' },
      ],
    },
    {
      label: 'Aide',
      submenu: [
        { label: 'Documentation', click: () => shell.openExternal('https://github.com/tino-le-doc/Serveur-MPC-IA-') },
        { label: 'API Anthropic',  click: () => shell.openExternal('https://console.anthropic.com') },
        ...(!isMac ? [
          { type: 'separator' },
          { label: 'Préférences…', click: openPreferences },
          { label: `À propos de ${APP_NAME}`, role: 'about' },
        ] : []),
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function navigate(p) {
  if (mainWindow) mainWindow.loadURL(`http://localhost:${PORT}${p}`);
}

// ─── Préférences (clé API) ───────────────────
let prefsWindow = null;
function openPreferences() {
  if (prefsWindow) { prefsWindow.focus(); return; }

  prefsWindow = new BrowserWindow({
    width: 500,
    height: 320,
    title: 'Préférences — MCP IA',
    resizable: false,
    modal: true,
    parent: mainWindow,
    backgroundColor: '#1a1d27',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  });

  const current = store.get('anthropic_api_key') || '';

  prefsWindow.loadURL(`data:text/html,${encodeURIComponent(`
    <!DOCTYPE html>
    <html style="background:#1a1d27;color:#e2e8f0;font-family:system-ui;padding:2rem">
    <h2 style="margin-bottom:1rem">Preferences</h2>
    <label style="font-size:.85rem;color:#64748b">Cle API Anthropic</label>
    <input id="key" type="password" value="${current}"
      style="width:100%;padding:.6rem;background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;color:#e2e8f0;font-size:.9rem;margin-top:.4rem">
    <div style="margin-top:.5rem;font-size:.8rem;color:#64748b">
      Obtenez votre cle sur <a href="https://console.anthropic.com" style="color:#6c63ff">console.anthropic.com</a>
    </div>
    <button onclick="save()" style="margin-top:1.5rem;padding:.65rem 1.4rem;background:#6c63ff;color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:600">
      Enregistrer
    </button>
    <script>
      function save() {
        window.electronAPI.savePref('anthropic_api_key', document.getElementById('key').value);
        window.close();
      }
    </script>
    </html>
  `)}`);

  prefsWindow.on('closed', () => { prefsWindow = null; });
}

// ─── Tray ────────────────────────────────────
function createTray() {
  const iconPath = path.join(__dirname, 'assets',
    process.platform === 'win32' ? 'tray.ico' : 'tray.png');
  if (!fs.existsSync(iconPath)) return;
  tray = new Tray(iconPath);
  tray.setToolTip(APP_NAME);
  const menu = Menu.buildFromTemplate([
    { label: 'Ouvrir MCP IA', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    { type: 'separator' },
    { label: 'Quitter', click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
  tray.on('click', () => { mainWindow?.show(); mainWindow?.focus(); });
}

// ─── IPC Handlers ────────────────────────────
ipcMain.handle('save-pref',   (_, key, value) => store.set(key, value));
ipcMain.handle('get-pref',    (_, key)         => store.get(key));
ipcMain.handle('get-api-url', ()               => `http://localhost:${PORT}`);

// ─── Lifecycle ───────────────────────────────
app.whenReady().then(async () => {
  createSplash();

  try {
    await startBackend();
    await waitForPort(PORT);
  } catch (err) {
    console.error('Backend non disponible :', err?.message);
    dialog.showErrorBox('Erreur de démarrage',
      `Impossible de démarrer le backend Python.\n\nAssurez-vous que Python 3.10+ est installe et que les dependances sont presentes.\n\n${err?.message || ''}`
    );
  }

  createMainWindow();
  createTray();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (!mainWindow) createMainWindow();
  else mainWindow.show();
});

app.on('before-quit', () => {
  if (apiProcess) {
    try {
      if (process.platform === 'win32') {
        exec(`taskkill /pid ${apiProcess.pid} /f /t`);
      } else {
        apiProcess.kill('SIGTERM');
      }
    } catch (e) {}
  }
});

// Sécurité : liens externes → navigateur système
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, url) => {
    if (!url.startsWith(`http://localhost:${PORT}`)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
});
