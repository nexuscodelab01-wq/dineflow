import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, FlatList, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../api/client';
import { useMoney } from '../utils/money';
import { decodeJwtPayload } from '../api/jwt';
import {
  clockOut, createCounterOrder, createTableOrder, fetchCategories, fetchMenu,
  fetchOpenTableSessions, fetchTables, seatTable,
} from '../api/pos';
import type { Category, MenuItem, OpenSession, RestaurantTableRow } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'Order'>;

export default function OrderScreen({ navigation }: Props) {
  const money = useMoney();
  const deviceToken = usePosStore((s) => s.deviceToken);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const staffName = usePosStore((s) => s.staffName);
  const logoutPin = usePosStore((s) => s.logoutPin);
  const cart = usePosStore((s) => s.cart);
  const addToCart = usePosStore((s) => s.addToCart);
  const removeFromCart = usePosStore((s) => s.removeFromCart);
  const decrementCartLine = usePosStore((s) => s.decrementCartLine);
  const setCartLineNote = usePosStore((s) => s.setCartLineNote);
  const clearCart = usePosStore((s) => s.clearCart);
  const setTimeEntry = usePosStore((s) => s.setTimeEntry);
  const isTill = usePosStore((s) => s.deviceKind) !== 'HANDHELD';

  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [loadingMenu, setLoadingMenu] = useState(true);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | undefined>(undefined);
  const [mode, setMode] = useState<'counter' | 'table'>('counter');
  const [openSessions, setOpenSessions] = useState<OpenSession[]>([]);
  const [tables, setTables] = useState<RestaurantTableRow[]>([]);
  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [seatingTableId, setSeatingTableId] = useState<number | null>(null);
  const [partySize, setPartySize] = useState('');
  const [seating, setSeating] = useState(false);
  const [noteLineId, setNoteLineId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const restaurantId = deviceToken ? decodeJwtPayload<{ tenant: number }>(deviceToken).tenant : null;

  useEffect(() => {
    if (!restaurantId) return;
    fetchMenu(restaurantId)
      .then((res) => setMenu(res.items.filter((i) => i.is_available)))
      .catch(() => setError('Could not load the menu'))
      .finally(() => setLoadingMenu(false));
    fetchCategories(restaurantId).then(setCategories).catch(() => {});
  }, [restaurantId]);

  const visibleMenu = useMemo(() => {
    const q = search.trim().toLowerCase();
    return menu.filter((item) => {
      const matchesSearch = !q || item.name.toLowerCase().includes(q) || (item.description ?? '').toLowerCase().includes(q);
      const matchesCategory = !selectedCategoryId || item.category_id === selectedCategoryId;
      return matchesSearch && matchesCategory;
    });
  }, [menu, search, selectedCategoryId]);

  const refreshOpenSessions = useCallback(() => {
    if (!deviceToken) return;
    fetchOpenTableSessions(deviceToken)
      .then((res) => setOpenSessions(res.sessions))
      .catch(() => setError('Could not load open tables'));
    fetchTables(deviceToken).then(setTables).catch(() => {});
  }, [deviceToken]);

  useEffect(() => {
    if (mode !== 'table') return;
    refreshOpenSessions();
  }, [mode, refreshOpenSessions]);

  // Catches a table being settled from TableTender/TableCardTender and coming back here — the list
  // (and the selected table's total) needs to reflect that the tab closed or a round was just sent.
  useFocusEffect(useCallback(() => {
    if (mode === 'table') refreshOpenSessions();
  }, [mode, refreshOpenSessions]));

  const total = cart.reduce((sum, line) => sum + line.price * line.quantity, 0);
  const selectedTable = mode === 'table' ? openSessions.find((s) => s.session_id === selectedSession) : undefined;
  const availableTables = tables.filter((t) => !openSessions.some((s) => s.table_id === t.table_id));

  async function handleSeat(tableId: number) {
    if (!posSessionToken || seating) return;
    setSeating(true);
    setError('');
    try {
      const parsed = partySize.trim() ? Number(partySize.trim()) : undefined;
      const session = await seatTable(posSessionToken, tableId, parsed);
      refreshOpenSessions();
      setSelectedSession(session.session_id);
      setSeatingTableId(null);
      setPartySize('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not seat that table');
    } finally {
      setSeating(false);
    }
  }

  async function send() {
    if (!posSessionToken || cart.length === 0) return;
    if (mode === 'table' && selectedSession == null) {
      setError('Pick a table first');
      return;
    }
    setSending(true);
    setError('');
    const items = cart.map((l) => ({
      menu_item_id: l.menuItemId, quantity: l.quantity, modifier_option_ids: [],
      special_instructions: l.note || null,
    }));
    try {
      if (mode === 'counter') {
        const order = await createCounterOrder(posSessionToken, items);
        clearCart();
        navigation.navigate('CashTender', { orderId: order.order_id, orderNumber: order.order_number, total: order.total });
      } else {
        await createTableOrder(posSessionToken, selectedSession as number, items);
        clearCart();
        refreshOpenSessions(); // updates the selected table's running total/round count
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the order');
    } finally {
      setSending(false);
    }
  }

  async function handleClockOut() {
    if (!posSessionToken) return;
    // A handheld has no drawer to close, so its clock-out is where the server counts their cash.
    if (!isTill) {
      navigation.navigate('ClockOut');
      return;
    }
    try {
      await clockOut(posSessionToken);
      setTimeEntry(null); // the navigator falls back to ClockInScreen automatically
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not clock out');
    }
  }

  function openNoteEditor(lineId: string, currentNote?: string) {
    setNoteLineId(lineId);
    setNoteDraft(currentNote ?? '');
  }

  function saveNote() {
    if (noteLineId) setCartLineNote(noteLineId, noteDraft.trim());
    setNoteLineId(null);
    setNoteDraft('');
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.staffName}>{staffName}</Text>
        <View style={styles.headerLinks}>
          {isTill && (
            <>
              <TouchableOpacity onPress={() => navigation.navigate('CashMovement')}>
                <Text style={styles.headerLink}>Cash in/out</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => navigation.navigate('CloseShift')}>
                <Text style={styles.headerLink}>End shift</Text>
              </TouchableOpacity>
            </>
          )}
          <TouchableOpacity onPress={handleClockOut}>
            <Text style={styles.headerLink}>Clock out</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={logoutPin}><Text style={styles.switchUser}>Switch user</Text></TouchableOpacity>
        </View>
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
        <>
          {openSessions.length > 0 && (
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
            />
          )}
          {availableTables.length > 0 && (
            <FlatList
              horizontal
              data={availableTables}
              keyExtractor={(t) => String(t.table_id)}
              style={styles.tableList}
              renderItem={({ item }) => (
                <TouchableOpacity style={styles.tableChipEmpty} onPress={() => setSeatingTableId(item.table_id)}>
                  <Text style={styles.tableChipEmptyText}>+ Table {item.table_number}</Text>
                </TouchableOpacity>
              )}
            />
          )}
          {openSessions.length === 0 && availableTables.length === 0 && (
            <Text style={styles.empty}>No tables set up yet</Text>
          )}
        </>
      )}

      {seatingTableId != null && (
        <View style={styles.seatBar}>
          <Text style={styles.seatBarText}>Seating this table — how many guests?</Text>
          <TextInput
            style={styles.seatInput}
            value={partySize}
            onChangeText={setPartySize}
            placeholder="Optional"
            keyboardType="number-pad"
          />
          <TouchableOpacity
            style={[styles.tabBarButton, seating && styles.tabBarButtonDisabled]}
            disabled={seating}
            onPress={() => handleSeat(seatingTableId)}
          >
            {seating ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.tabBarButtonText}>Seat</Text>}
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { setSeatingTableId(null); setPartySize(''); }}>
            <Text style={styles.seatCancel}>Cancel</Text>
          </TouchableOpacity>
        </View>
      )}

      {selectedTable && (
        <View style={styles.tabBar}>
          <Text style={styles.tabBarText}>
            Table {selectedTable.table_number} — {selectedTable.rounds} round{selectedTable.rounds === 1 ? '' : 's'} · {money(selectedTable.total)} on the tab
          </Text>
          <TouchableOpacity
            style={[styles.tabBarButton, Number(selectedTable.total) <= 0 && styles.tabBarButtonDisabled]}
            disabled={Number(selectedTable.total) <= 0}
            onPress={() => navigation.navigate('TableTender', {
              sessionId: selectedTable.session_id, tableNumber: selectedTable.table_number, total: selectedTable.total,
            })}
          >
            <Text style={styles.tabBarButtonText}>Settle bill</Text>
          </TouchableOpacity>
        </View>
      )}

      <View style={styles.body}>
        <View style={styles.menuColumn}>
          <TextInput
            style={styles.searchInput}
            value={search}
            onChangeText={setSearch}
            placeholder="Search menu…"
            autoCapitalize="none"
            autoCorrect={false}
          />
          {categories.length > 0 && (
            <FlatList
              horizontal
              data={categories}
              keyExtractor={(c) => String(c.id)}
              style={styles.categoryList}
              showsHorizontalScrollIndicator={false}
              ListHeaderComponent={
                <TouchableOpacity
                  style={[styles.categoryChip, !selectedCategoryId && styles.categoryChipActive]}
                  onPress={() => setSelectedCategoryId(undefined)}
                >
                  <Text style={!selectedCategoryId ? styles.categoryChipTextActive : styles.categoryChipText}>All</Text>
                </TouchableOpacity>
              }
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[styles.categoryChip, selectedCategoryId === item.id && styles.categoryChipActive]}
                  onPress={() => setSelectedCategoryId(item.id)}
                >
                  <Text style={selectedCategoryId === item.id ? styles.categoryChipTextActive : styles.categoryChipText}>{item.name}</Text>
                </TouchableOpacity>
              )}
            />
          )}
          {loadingMenu ? <ActivityIndicator /> : (
            <FlatList
              data={visibleMenu}
              keyExtractor={(i) => String(i.id)}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.menuItem}
                  onPress={() => addToCart({ menuItemId: item.id, name: item.name, price: Number(item.price) })}
                >
                  <Text style={styles.menuItemName}>{item.name}</Text>
                  <Text style={styles.menuItemPrice}>{money(item.price)}</Text>
                </TouchableOpacity>
              )}
              ListEmptyComponent={<Text style={styles.empty}>No items match</Text>}
            />
          )}
        </View>

        <View style={styles.cartColumn}>
          <View style={styles.cartHeader}>
            <Text style={styles.cartTitle}>Cart</Text>
            {cart.length > 0 && (
              <TouchableOpacity onPress={clearCart}>
                <Text style={styles.clearCart}>Clear</Text>
              </TouchableOpacity>
            )}
          </View>
          <FlatList
            data={cart}
            keyExtractor={(l) => l.lineId}
            renderItem={({ item }) => (
              <View style={styles.cartLine}>
                <View style={styles.cartLineInfo}>
                  <Text style={styles.cartLineText}>{item.name}</Text>
                  <Text style={styles.cartLineText}>{money(item.price * item.quantity)}</Text>
                </View>
                {item.note ? <Text style={styles.cartLineNote}>Note: {item.note}</Text> : null}
                <View style={styles.cartLineControls}>
                  <TouchableOpacity style={styles.qtyButton} onPress={() => decrementCartLine(item.lineId)}>
                    <Text style={styles.qtyButtonText}>−</Text>
                  </TouchableOpacity>
                  <Text style={styles.qtyText}>{item.quantity}</Text>
                  <TouchableOpacity
                    style={styles.qtyButton}
                    onPress={() => addToCart({ menuItemId: item.menuItemId, name: item.name, price: item.price, note: item.note })}
                  >
                    <Text style={styles.qtyButtonText}>+</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.noteButton} onPress={() => openNoteEditor(item.lineId, item.note)}>
                    <Text style={styles.noteButtonText}>{item.note ? 'Edit note' : '+ Note'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.removeButton} onPress={() => removeFromCart(item.lineId)}>
                    <Text style={styles.removeButtonText}>✕</Text>
                  </TouchableOpacity>
                </View>
                {noteLineId === item.lineId && (
                  <View style={styles.noteEditor}>
                    <TextInput
                      style={styles.noteInput}
                      value={noteDraft}
                      onChangeText={setNoteDraft}
                      placeholder="e.g. no onions"
                      autoFocus
                      returnKeyType="done"
                      onSubmitEditing={saveNote}
                    />
                    <TouchableOpacity onPress={saveNote}>
                      <Text style={styles.noteSave}>Save</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            )}
            ListEmptyComponent={<Text style={styles.empty}>Tap items to add them</Text>}
          />
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Total</Text>
            <Text style={styles.totalValue}>{money(total)}</Text>
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
  headerLinks: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  headerLink: { color: '#555', fontSize: 13, fontWeight: '600' },
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
  tableChipEmpty: {
    paddingVertical: 10, paddingHorizontal: 16, borderRadius: 18, marginRight: 8,
    borderWidth: 1, borderStyle: 'dashed', borderColor: '#2c6f53',
  },
  tableChipEmptyText: { fontWeight: '600', color: '#2c6f53' },
  seatBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 16, paddingVertical: 10, backgroundColor: '#f0f7f3', borderBottomWidth: 1, borderBottomColor: '#eee',
  },
  seatBarText: { fontSize: 13, color: '#444', flex: 1 },
  seatInput: { width: 70, borderWidth: 1, borderColor: '#ccc', borderRadius: 8, paddingVertical: 6, paddingHorizontal: 10, fontSize: 13 },
  seatCancel: { color: '#999', fontSize: 13 },
  tabBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 10, backgroundColor: '#f7f7f5', borderBottomWidth: 1, borderBottomColor: '#eee',
  },
  tabBarText: { fontSize: 13, color: '#444', flex: 1, marginRight: 12 },
  tabBarButton: { backgroundColor: '#2c6f53', borderRadius: 8, paddingVertical: 8, paddingHorizontal: 16 },
  tabBarButtonDisabled: { opacity: 0.4 },
  tabBarButtonText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  body: { flex: 1, flexDirection: 'row' },
  menuColumn: { flex: 2, padding: 12 },
  searchInput: {
    borderWidth: 1, borderColor: '#ccc', borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12,
    fontSize: 14, marginBottom: 8,
  },
  categoryList: { maxHeight: 40, marginBottom: 8 },
  categoryChip: { paddingVertical: 6, paddingHorizontal: 14, borderRadius: 16, backgroundColor: '#f0f0f0', marginRight: 8 },
  categoryChipActive: { backgroundColor: '#2c6f53' },
  categoryChipText: { fontSize: 13, fontWeight: '600', color: '#333' },
  categoryChipTextActive: { fontSize: 13, fontWeight: '600', color: '#fff' },
  menuItem: {
    flexDirection: 'row', justifyContent: 'space-between', padding: 16,
    borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  menuItemName: { fontSize: 16 },
  menuItemPrice: { fontSize: 16, color: '#555' },
  cartColumn: { flex: 1, padding: 12, borderLeftWidth: 1, borderLeftColor: '#eee' },
  cartHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  cartTitle: { fontSize: 16, fontWeight: '700' },
  clearCart: { color: '#c0392b', fontSize: 13, fontWeight: '600' },
  cartLine: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f5f5f5' },
  cartLineInfo: { flexDirection: 'row', justifyContent: 'space-between' },
  cartLineText: { fontSize: 14 },
  cartLineNote: { fontSize: 12, color: '#888', fontStyle: 'italic', marginTop: 2 },
  cartLineControls: { flexDirection: 'row', alignItems: 'center', marginTop: 6, gap: 8 },
  qtyButton: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: '#f0f0f0',
    alignItems: 'center', justifyContent: 'center',
  },
  qtyButtonText: { fontSize: 16, fontWeight: '700', color: '#333' },
  qtyText: { fontSize: 14, fontWeight: '600', minWidth: 20, textAlign: 'center' },
  noteButton: { paddingHorizontal: 6, paddingVertical: 4 },
  noteButtonText: { color: '#2c6f53', fontSize: 12, fontWeight: '600' },
  removeButton: { marginLeft: 'auto', paddingHorizontal: 8, paddingVertical: 4 },
  removeButtonText: { color: '#c0392b', fontSize: 14, fontWeight: '700' },
  noteEditor: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  noteInput: { flex: 1, borderWidth: 1, borderColor: '#ccc', borderRadius: 8, paddingVertical: 6, paddingHorizontal: 10, fontSize: 13 },
  noteSave: { color: '#2c6f53', fontSize: 13, fontWeight: '700' },
  empty: { color: '#999', fontSize: 13, padding: 8 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12, borderTopWidth: 1, borderTopColor: '#eee' },
  totalLabel: { fontSize: 16, fontWeight: '700' },
  totalValue: { fontSize: 16, fontWeight: '700' },
  error: { color: '#c0392b', marginBottom: 8 },
  sendButton: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 14, alignItems: 'center' },
  sendButtonDisabled: { opacity: 0.5 },
  sendButtonText: { color: '#fff', fontSize: 15, fontWeight: '700' },
});
