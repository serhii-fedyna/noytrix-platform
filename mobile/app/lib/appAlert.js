let handler = null;

export function setAppAlertHandler(fn) {
  handler = fn;
}

export function showAppAlert(title, message) {
  if (handler) handler({ title, message });
}





