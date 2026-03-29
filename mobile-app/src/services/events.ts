type Listener = (data: Record<string, unknown>) => void;

const listeners: Record<string, Listener[]> = {};

export function emit(event: string, data: Record<string, unknown>) {
  (listeners[event] || []).forEach(fn => fn(data));
}

export function on(event: string, fn: Listener) {
  if (!listeners[event]) listeners[event] = [];
  listeners[event].push(fn);
  return () => {
    listeners[event] = listeners[event].filter(f => f !== fn);
  };
}
