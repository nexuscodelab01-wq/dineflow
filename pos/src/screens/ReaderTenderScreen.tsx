import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { cancelReader, fetchPaymentStatus, payOnReader } from '../api/pos';
import type { CardReader } from '../api/types';
import ReceiptActions from '../components/ReceiptActions';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'ReaderTender'>;
type Stage = 'choose' | 'sending' | 'waiting' | 'paid' | 'failed';

/**
 * Card payment on a smart reader (WisePOS E / S700) on the venue network: the till sends the amount, the customer
 * taps or inserts their card — and picks a tip — on the reader itself, and this screen follows the payment.
 */
export default function ReaderTenderScreen({ route, navigation }: Props) {
  const money = useMoney();
  const { kind, id, label, total, readers, split } = route.params;
  const token = usePosStore((s) => s.posSessionToken);
  const [stage, setStage] = useState<Stage>(readers.length === 1 ? 'sending' : 'choose');
  const [error, setError] = useState('');
  const [tip, setTip] = useState('0.00');
  const [reader, setReader] = useState<CardReader | null>(readers.length === 1 ? readers[0] : null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (poll.current) clearInterval(poll.current);
    poll.current = null;
  }

  async function start(chosen: CardReader) {
    if (!token) return;
    setReader(chosen);
    setStage('sending');
    setError('');
    try {
      const result = await payOnReader(token, { kind, id }, chosen.id, split);
      if (result.payment_id == null || result.closed) {
        setStage('paid'); // settled at once (no real reader involved)
        return;
      }
      setStage('waiting');
      const paymentId = result.payment_id;
      poll.current = setInterval(async () => {
        try {
          const status = await fetchPaymentStatus(token, paymentId);
          if (status.status === 'COMPLETED') {
            stopPolling();
            setTip(status.tip_amount);
            setStage('paid');
          } else if (status.status === 'FAILED' || (status.status === 'PENDING' && status.failure_message)) {
            stopPolling();
            setError(status.failure_message ?? 'The payment did not go through');
            setStage('failed');
          }
        } catch {
          // a missed poll is fine — the next one catches up
        }
      }, 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the card reader');
      setStage('failed');
    }
  }

  // With a single reader there is nothing to choose: start straight away. (The work happens in the async
  // callback below, after the first paint, so the screen shows "Sending…" immediately.)
  useEffect(() => {
    const timer = readers.length === 1 ? setTimeout(() => void start(readers[0]), 0) : null;
    return () => {
      if (timer) clearTimeout(timer);
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function cancel() {
    stopPolling();
    if (token && reader) await cancelReader(token, reader.id).catch(() => {});
    setError('Cancelled');
    setStage('failed');
  }

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.total}>{money(total)}</Text>

      {stage === 'choose' && (
        <>
          <Text style={styles.status}>Which reader?</Text>
          {readers.map((r) => (
            <TouchableOpacity key={r.id} style={styles.reader} onPress={() => start(r)}>
              <Text style={styles.readerText}>{r.label}</Text>
              <Text style={styles.readerMeta}>{r.status}</Text>
            </TouchableOpacity>
          ))}
        </>
      )}
      {(stage === 'sending' || stage === 'waiting') && (
        <>
          <ActivityIndicator style={{ marginBottom: 12 }} />
          <Text style={styles.status}>{stage === 'sending' ? 'Sending to the reader…' : `Waiting for the customer on ${reader?.label ?? 'the reader'}…`}</Text>
          <TouchableOpacity style={styles.secondary} onPress={cancel}><Text style={styles.secondaryText}>Cancel</Text></TouchableOpacity>
        </>
      )}
      {stage === 'paid' && (
        <>
          <Text style={styles.paid}>Paid — card</Text>
          {Number(tip) > 0 && <Text style={styles.status}>Tip {money(tip)}</Text>}
          <ReceiptActions target={{ kind, id }} />
          <TouchableOpacity
            style={styles.button}
            onPress={() => (kind === 'tab' ? navigation.replace('TableTender', { sessionId: id, tableNumber: label, total }) : navigation.popToTop())}
          >
            <Text style={styles.buttonText}>{kind === 'tab' ? 'Back to the bill' : 'New order'}</Text>
          </TouchableOpacity>
        </>
      )}
      {stage === 'failed' && (
        <>
          <Text style={styles.error}>{error}</Text>
          <TouchableOpacity style={styles.button} onPress={() => (reader ? start(reader) : setStage('choose'))}>
            <Text style={styles.buttonText}>Try again</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondary} onPress={() => navigation.goBack()}><Text style={styles.secondaryText}>Back</Text></TouchableOpacity>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', padding: 32 },
  label: { fontSize: 18, color: '#555', marginBottom: 8 },
  total: { fontSize: 48, fontWeight: '800', marginBottom: 28 },
  status: { fontSize: 16, color: '#555', marginBottom: 12, textAlign: 'center' },
  paid: { fontSize: 22, fontWeight: '700', color: '#2c6f53', marginBottom: 8 },
  error: { color: '#c0392b', marginBottom: 16, textAlign: 'center' },
  reader: { width: 280, borderWidth: 1, borderColor: '#ccc', borderRadius: 12, padding: 16, marginBottom: 10, flexDirection: 'row', justifyContent: 'space-between' },
  readerText: { fontSize: 16, fontWeight: '600' },
  readerMeta: { color: '#888' },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, paddingVertical: 16, paddingHorizontal: 36, marginTop: 20 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '700' },
  secondary: { marginTop: 16, padding: 10 },
  secondaryText: { color: '#2c6f53', fontSize: 15, fontWeight: '600' },
});
