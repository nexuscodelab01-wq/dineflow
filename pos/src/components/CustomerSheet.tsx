import { useEffect, useState } from 'react';
import { FlatList, Modal, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { searchCustomers } from '../api/pos';
import type { PosCustomer } from '../api/types';
import { usePosStore } from '../state/store';

type Props = { onClose: () => void; onPick: (customer: PosCustomer) => void };

/** Find a regular by name, email or phone so the sale (and its loyalty points) goes on their account. */
export default function CustomerSheet({ onClose, onPick }: Props) {
  const token = usePosStore((s) => s.posSessionToken);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PosCustomer[]>([]);

  useEffect(() => {
    if (!token || query.trim().length < 2) return;
    const timer = setTimeout(() => {
      searchCustomers(token, query.trim()).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [token, query]);

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <Text style={styles.title}>Find a customer</Text>
          <TextInput style={styles.input} value={query} onChangeText={setQuery} placeholder="Name, email or phone" autoFocus autoCapitalize="none" autoCorrect={false} />
          <FlatList
            data={query.trim().length < 2 ? [] : results}
            keyExtractor={(c) => String(c.id)}
            ListEmptyComponent={<Text style={styles.empty}>{query.trim().length < 2 ? 'Type at least two letters' : 'No one found'}</Text>}
            renderItem={({ item }) => (
              <TouchableOpacity style={styles.row} onPress={() => { onPick(item); onClose(); }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{item.name}{item.is_vip ? ' ★' : ''}</Text>
                  <Text style={styles.meta}>{item.phone || item.email}</Text>
                </View>
                <Text style={styles.points}>{item.points} pts</Text>
              </TouchableOpacity>
            )}
          />
          <TouchableOpacity onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', padding: 24 },
  sheet: { backgroundColor: '#fff', borderRadius: 16, padding: 20, maxHeight: '80%' },
  title: { fontSize: 20, fontWeight: '700', marginBottom: 8 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 12, fontSize: 15, marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  name: { fontSize: 16, fontWeight: '600' },
  meta: { fontSize: 12, color: '#888' },
  points: { color: '#2c6f53', fontWeight: '600' },
  empty: { color: '#888', textAlign: 'center', marginVertical: 16 },
  cancel: { alignItems: 'center', marginTop: 12 },
  cancelText: { color: '#888' },
});
