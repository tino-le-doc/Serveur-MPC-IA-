/**
 * Preload script — pont sécurisé entre le renderer et le main process
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Préférences
  savePref:  (key, value) => ipcRenderer.invoke('save-pref', key, value),
  getPref:   (key)        => ipcRenderer.invoke('get-pref', key),
  // URL de l'API locale
  getApiUrl: ()           => ipcRenderer.invoke('get-api-url'),
  // Plateforme
  platform:  process.platform,
  isElectron: true,
});
