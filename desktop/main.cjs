"use strict";

// The microphone and speaker run inside Electron/Chromium, using the same
// navigator.mediaDevices/getUserMedia pipeline proven by PTTConnect-PC.
// A separate WebSpeak3 gateway and TeamSpeak connector keep the UI isolated.
const { app, BrowserWindow, session, shell } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const SERVER = "heerlen.mijnts3.nl";
const PARTITION = "persist:teamspeak-heerlen";
let gatewayProcess = null;
let mainWindow = null;

function freeLocalPort() {
  return new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.on("error", reject);
    listener.listen(0, "127.0.0.1", () => {
      const a = listener.address();
      if (!a || typeof a !== "object") {
        listener.close();
        reject(new Error("Geen lokale gateway-poort beschikbaar."));
        return;
      }
      listener.close(() => resolve(a.port));
    });
  });
}

function waitForGateway(port, retries = 90) {
  return new Promise((resolve, reject) => {
    const probe = (remaining) => {
      if (!gatewayProcess || gatewayProcess.exitCode !== null) {
        reject(new Error("De TeamSpeak audio-engine is gestopt."));
        return;
      }
      const req = http.get({
        hostname: "127.0.0.1",
        port,
        path: "/",
        timeout: 900,
      }, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) resolve();
        else retry(remaining);
      });
      req.once("error", () => retry(remaining));
      req.once("timeout", () => req.destroy());
    };
    const retry = (remaining) => {
      if (remaining > 0) setTimeout(() => probe(remaining - 1), 250);
      else reject(new Error("De lokale TeamSpeak-gateway reageert niet."));
    };
    probe(retries);
  });
}

function runtime(...parts) {
  return path.join(process.resourcesPath, "runtime", ...parts);
}

function startGateway(port) {
  const entry = runtime("gateway", "dist", "index.js");
  const env = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: "1",
    PORT: String(port),
    WEB_DIST: runtime("web"),
    CONNECTOR_BIN: runtime("connector", "ts-connector.exe"),
    ALLOWED_SERVERS: SERVER,
    // Do not set DEFAULT_SERVER: it triggers automatic connection *before*
    // the user has typed a nickname. The Heerlen UI has an explicit join form.
    FEEDBACK_ENABLED: "0",
    STORE_ENABLED: "0",
    LOG_CONNECTIONS: "0",
  };
  gatewayProcess = spawn(process.execPath, [entry], {
    cwd: path.dirname(entry),
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  gatewayProcess.stdout?.on("data", (data) => {
    console.log("[Heerlen gateway]", data.toString().trim());
  });
  gatewayProcess.stderr?.on("data", (data) => {
    console.error("[Heerlen gateway]", data.toString().trim());
  });
}

function stopGateway() {
  if (gatewayProcess && gatewayProcess.exitCode === null) {
    gatewayProcess.kill();
  }
  gatewayProcess = null;
}

async function createWindow() {
  const port = await freeLocalPort();
  const origin = "http://127.0.0.1:" + port;
  const allowedPage = (url) => {
    try { return new URL(url).origin === origin; } catch { return false; }
  };

  startGateway(port);
  await waitForGateway(port);

  const webSession = session.fromPartition(PARTITION);
  // Chromium can grant microphone permission, unlike the previous failing
  // CPAL driver. Only the private loopback gateway may request this.
  webSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(allowedPage(webContents.getURL()) &&
      (permission === "media" || permission === "notifications"));
  });
  webSession.setPermissionCheckHandler((webContents, permission, requestingOrigin) =>
    allowedPage(requestingOrigin) &&
      (permission === "media" || permission === "notifications")
  );

  mainWindow = new BrowserWindow({
    title: "TeamSpeak Heerlen PC",
    width: 1440,
    height: 910,
    minWidth: 1000,
    minHeight: 690,
    center: true,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#030c1b",
    icon: path.join(__dirname, "Heerlen.ico"),
    webPreferences: {
      partition: PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.removeMenu();
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if ((url.startsWith("https://") || url.startsWith("http://")) && !allowedPage(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!allowedPage(url)) {
      event.preventDefault();
    }
  });
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    mainWindow.focus();
  });
  await mainWindow.loadURL(origin);
}

app.setName("TeamSpeak Heerlen PC");
const locked = app.requestSingleInstanceLock();
if (!locked) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });
  app.on("before-quit", stopGateway);
  app.on("window-all-closed", () => {
    stopGateway();
    app.quit();
  });
  app.whenReady().then(createWindow).catch((err) => {
    console.error(err);
    stopGateway();
    app.quit();
  });
}
