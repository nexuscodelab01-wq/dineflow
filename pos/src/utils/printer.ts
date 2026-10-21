import { fetchReceiptBytes } from '../api/pos';
import type { PrinterSettings, ReceiptTarget } from '../api/types';

// ESC p 0 25 250 — pulses the cash-drawer port on the printer. Same bytes the backend adds to a receipt.
const DRAWER_KICK_BASE64 = 'G3AAGfo=';

type TcpSocketModule = {
  createConnection: (
    options: { host: string; port: number },
    callback: () => void,
  ) => { write: (data: string, encoding: string, cb?: (err?: Error) => void) => void; destroy: () => void; on: (e: string, cb: (err: Error) => void) => void };
};

/** react-native-tcp-socket is a native module: an app build from before it was added doesn't have it. */
function tcp(): TcpSocketModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('react-native-tcp-socket').default as TcpSocketModule;
  } catch {
    return null;
  }
}

function send(printer: PrinterSettings, base64: string): Promise<void> {
  const sockets = tcp();
  if (!sockets || !printer.host) return Promise.reject(new Error('This app build cannot talk to a network printer yet — it needs the updated build.'));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Could not reach the printer at ${printer.host}`)), 6000);
    const socket = sockets.createConnection({ host: printer.host as string, port: printer.port }, () => {
      socket.write(base64, 'base64', (err) => {
        clearTimeout(timer);
        socket.destroy();
        if (err) reject(err);
        else resolve();
      });
    });
    socket.on('error', (err) => {
      clearTimeout(timer);
      reject(new Error(`Printer error: ${err.message}`));
    });
  });
}

/** Print a receipt on the till's network printer (kicking the drawer too when asked and wired up). */
export async function printReceipt(token: string, target: ReceiptTarget, printer: PrinterSettings, kick = false): Promise<void> {
  const { data } = await fetchReceiptBytes(token, target, kick);
  await send(printer, data);
}

/** Open the cash drawer without printing (a cash sale with auto-print off). */
export function kickDrawer(printer: PrinterSettings): Promise<void> {
  return send(printer, DRAWER_KICK_BASE64);
}
