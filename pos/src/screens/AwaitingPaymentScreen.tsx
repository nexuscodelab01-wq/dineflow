import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../api/client';
import { fetchAwaitingPayment } from '../api/pos';
import type { AwaitingPayment } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'AwaitingPayment'>;

/** Online orders the customer will pay for at collection or on delivery. Tap one to take the money. */
export default function AwaitingPaymentScreen({ navigation }: Props) {
  const money = useMoney();
  const token = usePosStore((s) => s.posSessionToken);
  const [rows, setRows] = useState<AwaitingPayment[] | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const load = useCallback(() => {
    if (!token) return;
    fetchAwaitingPayment(token).then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load orders'));
  }, [token]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const q = search.trim().toLowerCase();
  const shown = (rows ?? []).filter((r) => !q || r.order_number.toLowerCase().includes(q) || r.customer_name.toLowerCase().includes(q) || (r.customer_phone ?? '').includes(q));

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Waiting to be paid</Text>
      <TextInput style={styles.search} value={search} onChangeText={setSearch} placeholder="Order number, name or phone" autoCapitalize="none" autoCorrect={false} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {rows === null && !error ? <ActivityIndicator /> : (
        <FlatList
          data={shown}
          keyExtractor={(r) => String(r.order_id)}
          ListEmptyComponent={<Text style={styles.empty}>Nothing is waiting to be paid.</Text>}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={styles.row}
              onPress={() => navigation.replace('CashTender', { orderId: item.order_id, orderNumber: item.order_number, total: item.total })}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{item.order_number} · {item.customer_name}</Text>
                <Text style={styles.meta}>
                  {item.order_type === 'DELIVERY' ? 'Delivery' : 'Pickup'}{item.customer_phone ? ` · ${item.customer_phone}` : ''} · {item.status.toLowerCase()}
                </Text>
              </View>
              <Text style={styles.amount}>{money(item.total)}</Text>
            </TouchableOpacity>
          )}
        />
      )}
      <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}><Text style={styles.backText}>Close</Text></TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff', padding: 20 },
  title: { fontSize: 24, fontWeight: '700', marginBottom: 12 },
  search: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 12, fontSize: 15, marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#f0f0f0', gap: 12 },
  label: { fontSize: 16, fontWeight: '600' },
  meta: { fontSize: 12, color: '#888' },
  amount: { fontSize: 17, fontWeight: '700', color: '#2c6f53' },
  empty: { color: '#888', textAlign: 'center', marginTop: 24 },
  error: { color: '#c0392b', marginBottom: 8 },
  back: { alignItems: 'center', marginTop: 12 },
  backText: { color: '#888' },
});
