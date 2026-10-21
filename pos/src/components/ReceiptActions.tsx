import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import * as Print from 'expo-print';
import { ApiError } from '../api/client';
import { emailReceipt, fetchReceipt } from '../api/pos';
import type { ReceiptTarget } from '../api/types';
import { usePosStore } from '../state/store';
import { kickDrawer, printReceipt } from '../utils/printer';

type Props = {
  target: ReceiptTarget;
  /** The sale was paid in cash: open the drawer (if this till has one wired to its printer). */
  cash?: boolean;
};

type Receipt = {
  restaurant_name: string; title: string; reference: string; lines: { quantity: number; name: string; options: string[]; amount: string }[];
  subtotal: string; discount: string; service_charge: string; tax: string; delivery_fee: string; total: string; balance: string;
};

const html = (r: Receipt) => `<html><body style="font-family:-apple-system,Helvetica;max-width:320px;margin:auto;font-size:14px">
<h2 style="text-align:center;margin:0">${r.restaurant_name}</h2><p style="text-align:center">${r.title} · ${r.reference}</p><hr>
${r.lines.map((l) => `<div style="display:flex;justify-content:space-between"><span>${l.quantity} × ${l.name}</span><span>$${l.amount}</span></div>`).join('')}<hr>
<div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>$${r.subtotal}</span></div>
${Number(r.discount) > 0 ? `<div style="display:flex;justify-content:space-between"><span>Discount</span><span>-$${r.discount}</span></div>` : ''}
${Number(r.service_charge) > 0 ? `<div style="display:flex;justify-content:space-between"><span>Service charge</span><span>$${r.service_charge}</span></div>` : ''}
<div style="display:flex;justify-content:space-between"><span>Tax</span><span>$${r.tax}</span></div>
<div style="display:flex;justify-content:space-between;font-weight:700"><span>Total</span><span>$${r.total}</span></div>
${Number(r.balance) > 0 ? `<p style="text-align:center">Balance due $${r.balance}</p>` : ''}</body></html>`;

/**
 * Receipt buttons for a finished sale: print (network thermal printer if the till has one, else AirPrint), or email a
 * copy. Prints by itself when the till is set to auto-print, and kicks the drawer on cash sales.
 */
export default function ReceiptActions({ target, cash = false }: Props) {
  const token = usePosStore((s) => s.posSessionToken);
  const printer = usePosStore((s) => s.printer);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [emailing, setEmailing] = useState(false);
  const [email, setEmail] = useState('');

  async function print(kick: boolean) {
    if (!token) return;
    setBusy(true);
    setMessage('');
    try {
      if (printer.host) {
        await printReceipt(token, target, printer, kick && printer.cash_drawer);
      } else {
        const receipt = (await fetchReceipt(token, target)) as unknown as Receipt;
        await Print.printAsync({ html: html(receipt) }); // AirPrint
      }
      setMessage('Sent to the printer');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Could not print');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // Deferred a tick so the state updates inside print() happen in a callback, not synchronously in the effect.
    const timer = setTimeout(() => {
      if (printer.host && printer.auto_print) void print(cash);
      else if (printer.host && printer.cash_drawer && cash) kickDrawer(printer).catch(() => setMessage('Could not open the drawer'));
    }, 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function sendEmail() {
    if (!token || !email.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      await emailReceipt(token, target, email.trim());
      setMessage(`Receipt emailed to ${email.trim()}`);
      setEmailing(false);
      setEmail('');
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not send the email');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <TouchableOpacity style={styles.btn} onPress={() => print(cash)} disabled={busy}>
          <Text style={styles.btnText}>Print receipt</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.btn} onPress={() => setEmailing((v) => !v)} disabled={busy}>
          <Text style={styles.btnText}>Email receipt</Text>
        </TouchableOpacity>
      </View>
      {emailing && (
        <View style={styles.row}>
          <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder="customer@email.com" keyboardType="email-address" autoCapitalize="none" autoCorrect={false} />
          <TouchableOpacity style={styles.send} onPress={sendEmail} disabled={busy}><Text style={styles.sendText}>Send</Text></TouchableOpacity>
        </View>
      )}
      {busy ? <ActivityIndicator style={{ marginTop: 8 }} /> : message ? <Text style={styles.message}>{message}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', marginTop: 16, gap: 8 },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  btn: { borderWidth: 1, borderColor: '#2c6f53', borderRadius: 10, paddingVertical: 10, paddingHorizontal: 18 },
  btnText: { color: '#2c6f53', fontWeight: '600' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 10, width: 230, fontSize: 15 },
  send: { backgroundColor: '#2c6f53', borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16 },
  sendText: { color: '#fff', fontWeight: '600' },
  message: { color: '#555', fontSize: 13, textAlign: 'center', maxWidth: 320 },
});
