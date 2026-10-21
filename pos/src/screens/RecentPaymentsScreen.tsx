import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../api/client';
import { fetchRecentPayments, runControl } from '../api/pos';
import type { RecentPayment } from '../api/types';
import ControlSheet, { type ControlFields } from '../components/ControlSheet';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'RecentPayments'>;

/** Sales from the last day, newest first — the starting point for a refund. */
export default function RecentPaymentsScreen({ navigation }: Props) {
  const money = useMoney();
  const token = usePosStore((s) => s.posSessionToken);
  const [rows, setRows] = useState<RecentPayment[] | null>(null);
  const [error, setError] = useState('');
  const [picked, setPicked] = useState<RecentPayment | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    fetchRecentPayments(token).then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load recent sales'));
  }, [token]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function refund(fields: ControlFields, override?: string) {
    if (!token || !picked) return;
    await runControl(token, 'REFUND', { type: picked.kind === 'TAB' ? 'tab' : 'order', id: picked.id }, fields, override);
    load();
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Recent sales</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {rows === null && !error ? <ActivityIndicator /> : (
        <FlatList
          data={rows ?? []}
          keyExtractor={(r) => `${r.kind}-${r.id}`}
          ListEmptyComponent={<Text style={styles.empty}>No sales in the last 24 hours.</Text>}
          renderItem={({ item }) => (
            <TouchableOpacity style={styles.row} onPress={() => setPicked(item)}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{item.label}</Text>
                <Text style={styles.meta}>{new Date(item.paid_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · {item.method.toLowerCase()}</Text>
              </View>
              <Text style={styles.amount}>{money(item.amount)}</Text>
              <Text style={styles.refund}>Refund</Text>
            </TouchableOpacity>
          )}
        />
      )}
      <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}><Text style={styles.backText}>Close</Text></TouchableOpacity>
      {picked && (
        <ControlSheet visible title={`Refund ${picked.label} — ${money(picked.amount)}`} kind="REFUND" onClose={() => setPicked(null)} onRun={refund} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff', padding: 20 },
  title: { fontSize: 24, fontWeight: '700', marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#f0f0f0', gap: 12 },
  label: { fontSize: 16, fontWeight: '600' },
  meta: { fontSize: 12, color: '#888' },
  amount: { fontSize: 16, fontWeight: '700' },
  refund: { color: '#c0392b', fontWeight: '600' },
  empty: { color: '#888', textAlign: 'center', marginTop: 24 },
  error: { color: '#c0392b', marginBottom: 8 },
  back: { alignItems: 'center', marginTop: 12 },
  backText: { color: '#888' },
});
