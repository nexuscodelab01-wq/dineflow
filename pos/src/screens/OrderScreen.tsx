import { useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { decodeJwtPayload } from '../api/jwt';
import { createCounterOrder, createTableOrder, fetchMenu, fetchOpenTableSessions } from '../api/pos';
import type { MenuItem, OpenSession } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'Order'>;

export default function OrderScreen({ navigation }: Props) {
  const deviceToken = usePosStore((s) => s.deviceToken);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const staffName = usePosStore((s) => s.staffName);
  const logoutPin = usePosStore((s) => s.logoutPin);
  const cart = usePosStore((s) => s.cart);
  const addToCart = usePosStore((s) => s.addToCart);
  const clearCart = usePosStore((s) => s.clearCart);

  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [loadingMenu, setLoadingMenu] = useState(true);
  const [mode, setMode] = useState<'counter' | 'table'>('counter');
  const [openSessions, setOpenSessions] = useState<OpenSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const restaurantId = deviceToken ? decodeJwtPayload<{ tenant: number }>(deviceToken).tenant : null;

  useEffect(() => {
    if (!restaurantId) return;
    fetchMenu(restaurantId)
      .then((res) => setMenu(res.items.filter((i) => i.is_available)))
      .catch(() => setError('Could not load the menu'))
      .finally(() => setLoadingMenu(false));
  }, [restaurantId]);

  useEffect(() => {
    if (mode !== 'table' || !deviceToken) return;
    fetchOpenTableSessions(deviceToken)
      .then((res) => setOpenSessions(res.sessions))
      .catch(() => setError('Could not load open tables'));
  }, [mode, deviceToken]);

  const total = cart.reduce((sum, line) => sum + line.price * line.quantity, 0);

  async function send() {
    if (!posSessionToken || cart.length === 0) return;
    if (mode === 'table' && selectedSession == null) {
      setError('Pick a table first');
      return;
    }
    setSending(true);
    setError('');
    const items = cart.map((l) => ({ menu_item_id: l.menuItemId, quantity: l.quantity, modifier_option_ids: [] }));
    try {
      if (mode === 'counter') {
        const order = await createCounterOrder(posSessionToken, items);
        clearCart();
        navigation.navigate('CashTender', { orderId: order.order_id, orderNumber: order.order_number, total: order.total });
      } else {
        await createTableOrder(posSessionToken, selectedSession as number, items);
        clearCart();
        setSelectedSession(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the order');
    } finally {
      setSending(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.staffName}>{staffName}</Text>
        <TouchableOpacity onPress={logoutPin}><Text style={styles.switchUser}>Switch user</Text></TouchableOpacity>
      </View>

      <View style={styles.modeToggle}>
        <TouchableOpacity style={[styles.modeButton, mode === 'counter' && styles.modeButtonActive]} onPress={() => setMode('counter')}>
          <Text style={[styles.modeText, mode === 'counter' && styles.modeTextActive]}>Counter</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.modeButton, mode === 'table' && styles.modeButtonActive]} onPress={() => setMode('table')}>
          <Text style={[styles.modeText, mode === 'table' && styles.modeTextActive]}>Table</Text>
        </TouchableOpacity>
      </View>

      {mode === 'table' && (
        <FlatList
          horizontal
          data={openSessions}
          keyExtractor={(s) => String(s.session_id)}
          style={styles.tableList}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[styles.tableChip, selectedSession === item.session_id && styles.tableChipActive]}
              onPress={() => setSelectedSession(item.session_id)}
            >
              <Text style={selectedSession === item.session_id ? styles.tableChipTextActive : styles.tableChipText}>
                Table {item.table_number}
              </Text>
            </TouchableOpacity>
          )}
          ListEmptyComponent={<Text style={styles.empty}>No open tables</Text>}
        />
      )}

      <View style={styles.body}>
        <View style={styles.menuColumn}>
          {loadingMenu ? <ActivityIndicator /> : (
            <FlatList
              data={menu}
              keyExtractor={(i) => String(i.id)}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.menuItem}
                  onPress={() => addToCart({ menuItemId: item.id, name: item.name, price: Number(item.price) })}
                >
                  <Text style={styles.menuItemName}>{item.name}</Text>
                  <Text style={styles.menuItemPrice}>${Number(item.price).toFixed(2)}</Text>
                </TouchableOpacity>
              )}
            />
          )}
        </View>

        <View style={styles.cartColumn}>
          <Text style={styles.cartTitle}>Cart</Text>
          <FlatList
            data={cart}
            keyExtractor={(l) => String(l.menuItemId)}
            renderItem={({ item }) => (
              <View style={styles.cartLine}>
                <Text style={styles.cartLineText}>{item.quantity}× {item.name}</Text>
                <Text style={styles.cartLineText}>${(item.price * item.quantity).toFixed(2)}</Text>
              </View>
            )}
            ListEmptyComponent={<Text style={styles.empty}>Tap items to add them</Text>}
          />
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Total</Text>
            <Text style={styles.totalValue}>${total.toFixed(2)}</Text>
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <TouchableOpacity
            style={[styles.sendButton, (cart.length === 0 || sending) && styles.sendButtonDisabled]}
            onPress={send}
            disabled={cart.length === 0 || sending}
          >
            {sending ? <ActivityIndicator color="#fff" /> : <Text style={styles.sendButtonText}>Send to Kitchen</Text>}
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    padding: 16, borderBottomWidth: 1, borderBottomColor: '#eee',
  },
  staffName: { fontSize: 18, fontWeight: '700' },
  switchUser: { color: '#2c6f53', fontSize: 14, fontWeight: '600' },
  modeToggle: { flexDirection: 'row', padding: 12, gap: 8 },
  modeButton: { paddingVertical: 8, paddingHorizontal: 20, borderRadius: 20, backgroundColor: '#f0f0f0' },
  modeButtonActive: { backgroundColor: '#2c6f53' },
  modeText: { fontWeight: '600', color: '#333' },
  modeTextActive: { color: '#fff' },
  tableList: { paddingHorizontal: 12, maxHeight: 56 },
  tableChip: { paddingVertical: 10, paddingHorizontal: 16, borderRadius: 18, backgroundColor: '#f0f0f0', marginRight: 8 },
  tableChipActive: { backgroundColor: '#2c6f53' },
  tableChipText: { fontWeight: '600', color: '#333' },
  tableChipTextActive: { fontWeight: '600', color: '#fff' },
  body: { flex: 1, flexDirection: 'row' },
  menuColumn: { flex: 2, padding: 12 },
  menuItem: {
    flexDirection: 'row', justifyContent: 'space-between', padding: 16,
    borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  menuItemName: { fontSize: 16 },
  menuItemPrice: { fontSize: 16, color: '#555' },
  cartColumn: { flex: 1, padding: 12, borderLeftWidth: 1, borderLeftColor: '#eee' },
  cartTitle: { fontSize: 16, fontWeight: '700', marginBottom: 8 },
  cartLine: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 },
  cartLineText: { fontSize: 14 },
  empty: { color: '#999', fontSize: 13, padding: 8 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12, borderTopWidth: 1, borderTopColor: '#eee' },
  totalLabel: { fontSize: 16, fontWeight: '700' },
  totalValue: { fontSize: 16, fontWeight: '700' },
  error: { color: '#c0392b', marginBottom: 8 },
  sendButton: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 14, alignItems: 'center' },
  sendButtonDisabled: { opacity: 0.5 },
  sendButtonText: { color: '#fff', fontSize: 15, fontWeight: '700' },
});
