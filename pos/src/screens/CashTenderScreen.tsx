import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { payCash } from '../api/pos';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'CashTender'>;

export default function CashTenderScreen({ route, navigation }: Props) {
  const money = useMoney();
  const { orderId, orderNumber, total } = route.params;
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const [busy, setBusy] = useState(false);
  const [paid, setPaid] = useState(false);
  const [error, setError] = useState('');

  async function markPaid() {
    if (!posSessionToken) return;
    setBusy(true);
    setError('');
    try {
      await payCash(posSessionToken, orderId);
      setPaid(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not record the payment');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.orderNumber}>Order {orderNumber}</Text>
      <Text style={styles.total}>{money(total)}</Text>

      {paid ? (
        <>
          <Text style={styles.paidText}>Paid — cash</Text>
          <TouchableOpacity style={styles.button} onPress={() => navigation.popToTop()}>
            <Text style={styles.buttonText}>New order</Text>
          </TouchableOpacity>
        </>
      ) : (
        <>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={markPaid} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Mark Paid (Cash)</Text>}
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.secondaryButton}
            onPress={() => navigation.replace('CardTender', { orderId, orderNumber, total })}
            disabled={busy}
          >
            <Text style={styles.secondaryButtonText}>Pay by card</Text>
          </TouchableOpacity>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', padding: 32 },
  orderNumber: { fontSize: 18, color: '#555', marginBottom: 8 },
  total: { fontSize: 48, fontWeight: '800', marginBottom: 32 },
  paidText: { fontSize: 20, fontWeight: '700', color: '#2c6f53', marginBottom: 24 },
  error: { color: '#c0392b', marginBottom: 16 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, paddingVertical: 18, paddingHorizontal: 40 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  secondaryButton: { marginTop: 16, paddingVertical: 10, paddingHorizontal: 20 },
  secondaryButtonText: { color: '#2c6f53', fontSize: 15, fontWeight: '600' },
});
