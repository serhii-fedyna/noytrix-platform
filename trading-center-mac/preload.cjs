const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('trading', {
  currentActivation: () => ipcRenderer.invoke('activation:current'),
  activate: (input) => ipcRenderer.invoke('activation:activate', input),
  status: () => ipcRenderer.invoke('trader:status')
});
