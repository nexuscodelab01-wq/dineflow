import { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../api/client';
import { fetchReaders, fetchTab, payCashForTable } from '../api/pos';
import ReceiptActions from '../components/ReceiptActions';
import type { SplitPayload, TabDetail } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'TableTender'>;
type Mode = 'FULL' | 'EVEN' | 'ITEMS' | 'AMOUNT';

/** Settle a table's bill — all at once, or in parts: split evenly, by item, or an amount. Repeats until nothing is owed. */
export default function TableTenderScreen({ route, navigation }: Props) {
  const money = useMoney();
  const { sessionId, tableNumber } = route.params;
  const token = usePosStore((s) => s.posSessionToken);
  const [tab, setTab] = useState<TabDetail | null>(null);
  const [settled, setSettled] = useState(false);
  const [mode, setMode] = useState<Mode>('FULL');
  const [parts, setParts] = useState(2);
  const [picked, setPicked] = useState<number[]>([]);
  const [amountText, setAmountText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [lastPaid, setLastPaid] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    // A tab that has just been fully paid is closed, so fetching it fails: that is the "settled" signal.
    fetchTab(token, sessionId).then((t) => { setTab(t); setSettled(false); }).catch(() => setSettled(true));
  }, [token, sessionId]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const items = (tab?.rounds ?? []).filter((r) => r.status !== 'CANCELLED').flatMap((r) => r.items).filter((i) => i.item_id != null);
  const balance = Number(tab?.balance ?? 0);

  const split: SplitPayload | undefined = (() => {
    if (mode === 'EVEN') return { mode, parts_remaining: parts };
    if (mode === 'ITEMS') return { mode, item_ids: picked };
    if (mode === 'AMOUNT') return { mode, amount: amountText.trim() };
    return undefined;
  })();

  const thisPayment = (() => {
    if (mode === 'EVEN') return parts <= 1 ? balance : Math.round((balance / parts) * 100) / 100;
    if (mode === 'ITEMS') return Math.min(items.filter((i) => picked.includes(i.item_id as number)).reduce((s, i) => s + Number(i.amount_due), 0), balance);
    if (mode === 'AMOUNT') return Math.min(Number(amountText) || 0, balance);
    return balance;
  })();
  const ready = thisPayment > 0 && !(mode === 'ITEMS' && picked.length === 0);

  async function payCash() {
    if (!token || !ready) return;
    setBusy(true);
    setError('');
    try {
      await payCashForTable(token, sessionId, split);
      setLastPaid(money(thisPayment));
      if (mode === 'EVEN') setParts((p) => Math.max(1, p - 1));
      setPicked([]);
      setAmountText('');
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not record the payment');
    } finally {
      setBusy(false);
    }
  }

  if (settled) {
    return (
      <View style={styles.container}>
        <Text style={styles.orderNumber}>Table {tableNumber}</Text>
        <Text style={styles.paidText}>{lastPaid ? `Paid ${lastPaid} — ` : ''}tab settled</Text>
        <ReceiptActions target={{ kind: 'tab', id: sessionId }} cash />
        <TouchableOpacity style={styles.button} onPress={() => navigation.popToTop()}><Text style={styles.buttonText}>Done</Text></TouchableOpacity>
      </View>
    );
  }
  if (!tab) return <View style={styles.container}><ActivityIndicator /></View>;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.orderNumber}>Table {tableNumber}{tab.tab_name ? ` · ${tab.tab_name}` : ''}</Text>
      <Text style={styles.total}>{money(balance)}</Text>
      <Text style={styles.sub}>{Number(tab.paid) > 0 ? `${money(tab.paid)} already paid of ${money(tab.total)}` : 'still to pay'}</Text>

      <View style={styles.modes}>
        {([['FULL', 'All'], ['EVEN', 'Split evenly'], ['ITEMS', 'By item'], ['AMOUNT', 'Amount']] as [Mode, string][]).map(([m, label]) => (
          <TouchableOpacity key={m} style={[styles.modeChip, mode === m && styles.modeChipOn]} onPress={() => setMode(m)}>
            <Text style={[styles.modeText, mode === m && styles.modeTextOn]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {mode === 'EVEN' && (
        <View style={styles.row}>
          <Text style={styles.label}>Ways left to split</Text>
          <View style={styles.stepper}>
            <TouchableOpacity onPress={() => setParts((p) => Math.max(1, p - 1))}><Text style={styles.stepBtn}>−</Text></TouchableOpacity>
            <Text style={styles.qty}>{parts}</Text>
            <TouchableOpacity onPress={() => setParts((p) => Math.min(20, p + 1))}><Text style={styles.stepBtn}>+</Text></TouchableOpacity>
          </View>
        </View>
      )}
      {mode === 'AMOUNT' && (
        <TextInput style={styles.input} value={amountText} onChangeText={setAmountText} placeholder="Amount to take now" keyboardType="decimal-pad" />
      )}
      {mode === 'ITEMS' && (
        <View style={styles.items}>
          {items.map((i) => {
            const on = picked.includes(i.item_id as number);
            return (
              <TouchableOpacity
                key={i.item_id}
                disabled={i.paid}
                style={[styles.item, on && styles.itemOn, i.paid && styles.itemPaid]}
                onPress={() => setPicked((cur) => (on ? cur.filter((id) => id !== i.item_id) : [...cur, i.item_id as number]))}
              >
                <Text style={styles.itemText}>{i.quantity} × {i.name}</Text>
                <Text style={styles.itemText}>{i.paid ? 'Paid' : money(i.amount_due)}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      )}

      <Text style={styles.now}>{ready ? `Taking ${money(thisPayment)} now` : 'Choose what to take'}</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <TouchableOpacity style={[styles.button, (busy || !ready) && styles.buttonDisabled]} onPress={payCash} disabled={busy || !ready}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Mark Paid (Cash)</Text>}
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.secondaryButton}
        disabled={busy || !ready}
        onPress={async () => {
          const readers = token ? await fetchReaders(token).catch(() => []) : [];
          if (readers.length > 0) navigation.replace('ReaderTender', { kind: 'tab', id: sessionId, label: tableNumber, total: String(thisPayment), readers, split });
          else navigation.replace('TableCardTender', { sessionId, tableNumber, total: String(thisPayment), split });
        }}
      >
        <Text style={[styles.secondaryButtonText, !ready && { opacity: 0.4 }]}>Pay by card</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', padding: 28 },
  orderNumber: { fontSize: 18, color: '#555', marginBottom: 4 },
  total: { fontSize: 48, fontWeight: '800' },
  sub: { color: '#888', marginBottom: 20 },
  paidText: { fontSize: 20, fontWeight: '700', color: '#2c6f53', marginBottom: 24 },
  modes: { flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap', justifyContent: 'center' },
  modeChip: { borderWidth: 1, borderColor: '#ccc', borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8 },
  modeChipOn: { backgroundColor: '#2c6f53', borderColor: '#2c6f53' },
  modeText: { color: '#444' },
  modeTextOn: { color: '#fff', fontWeight: '600' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 16, marginBottom: 12 },
  label: { fontSize: 15, color: '#555' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  stepBtn: { fontSize: 30, paddingHorizontal: 12, color: '#2c6f53' },
  qty: { fontSize: 20, fontWeight: '700' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 12, fontSize: 18, width: 220, textAlign: 'center', marginBottom: 12 },
  items: { alignSelf: 'stretch', marginBottom: 8 },
  item: { flexDirection: 'row', justifyContent: 'space-between', borderWidth: 1, borderColor: '#ddd', borderRadius: 10, padding: 12, marginBottom: 6 },
  itemOn: { borderColor: '#2c6f53', backgroundColor: '#e8f3ee' },
  itemPaid: { opacity: 0.4 },
  itemText: { fontSize: 15 },
  now: { fontSize: 16, fontWeight: '600', marginVertical: 12 },
  error: { color: '#c0392b', marginBottom: 12 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, paddingVertical: 18, paddingHorizontal: 40 },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  secondaryButton: { marginTop: 16, paddingVertical: 10, paddingHorizontal: 20 },
  secondaryButtonText: { color: '#2c6f53', fontSize: 15, fontWeight: '600' },
});
