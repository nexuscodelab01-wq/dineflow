import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { fetchItemDetail } from '../api/pos';
import type { MenuItem, MenuItemDetail } from '../api/types';
import { useMoney } from '../utils/money';

type Props = {
  item: MenuItem;
  restaurantId: number;
  onClose: () => void;
  onAdd: (line: { price: number; modifierOptionIds: number[]; modifierLabels: string[] }) => void;
};

/** "No onions, extra cheese": pick the dish's options before it goes in the cart. Mounted fresh per dish. */
export default function ModifierSheet({ item, restaurantId, onClose, onAdd }: Props) {
  const money = useMoney();
  const [detail, setDetail] = useState<MenuItemDetail | null>(null);
  const [picked, setPicked] = useState<Record<number, number[]>>({}); // modifier id -> option ids
  const [error, setError] = useState('');

  useEffect(() => {
    fetchItemDetail(restaurantId, item.id).then(setDetail).catch(() => setError('Could not load the options'));
  }, [restaurantId, item.id]);

  function toggle(modifierId: number, optionId: number, max: number) {
    setPicked((cur) => {
      const chosen = cur[modifierId] ?? [];
      if (chosen.includes(optionId)) return { ...cur, [modifierId]: chosen.filter((id) => id !== optionId) };
      // A single-choice modifier swaps; a multi-choice one stops at its maximum.
      if (max === 1) return { ...cur, [modifierId]: [optionId] };
      return chosen.length >= max ? cur : { ...cur, [modifierId]: [...chosen, optionId] };
    });
  }

  const chosenOptions = useMemo(() => {
    if (!detail) return [];
    return detail.modifiers.flatMap((m) => m.options.filter((o) => (picked[m.id] ?? []).includes(o.id)));
  }, [detail, picked]);
  const price = Number(item.price) + chosenOptions.reduce((sum, o) => sum + Number(o.price_adjustment), 0);

  function add() {
    if (!detail) return;
    const missing = detail.modifiers.find((m) => (picked[m.id] ?? []).length < Math.max(m.is_required ? 1 : 0, m.min_selections));
    if (missing) { setError(`Choose ${missing.name}`); return; }
    onAdd({ price, modifierOptionIds: chosenOptions.map((o) => o.id), modifierLabels: chosenOptions.map((o) => o.name) });
    onClose();
  }

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <Text style={styles.title}>{item.name}</Text>
          {!detail && !error ? <ActivityIndicator /> : null}
          <ScrollView>
            {detail?.modifiers.map((m) => (
              <View key={m.id} style={styles.group}>
                <Text style={styles.groupTitle}>{m.name}{m.is_required ? ' (required)' : ''}</Text>
                {m.options.map((o) => {
                  const on = (picked[m.id] ?? []).includes(o.id);
                  return (
                    <TouchableOpacity key={o.id} style={[styles.option, on && styles.optionOn]} onPress={() => toggle(m.id, o.id, m.max_selections)}>
                      <Text style={[styles.optionText, on && styles.optionTextOn]}>{o.name}</Text>
                      {Number(o.price_adjustment) !== 0 && <Text style={styles.optionText}>+{money(o.price_adjustment)}</Text>}
                    </TouchableOpacity>
                  );
                })}
              </View>
            ))}
          </ScrollView>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <TouchableOpacity style={styles.add} onPress={add} disabled={!detail}>
            <Text style={styles.addText}>Add — {money(price)}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', padding: 24 },
  sheet: { backgroundColor: '#fff', borderRadius: 16, padding: 20, maxHeight: '90%' },
  title: { fontSize: 22, fontWeight: '700', marginBottom: 8 },
  group: { marginTop: 12 },
  groupTitle: { fontSize: 14, fontWeight: '700', color: '#555', marginBottom: 6, textTransform: 'uppercase' },
  option: { flexDirection: 'row', justifyContent: 'space-between', borderWidth: 1, borderColor: '#ddd', borderRadius: 10, padding: 12, marginBottom: 6 },
  optionOn: { borderColor: '#2c6f53', backgroundColor: '#e8f3ee' },
  optionText: { fontSize: 15, color: '#333' },
  optionTextOn: { color: '#2c6f53', fontWeight: '600' },
  error: { color: '#c0392b', marginTop: 8 },
  add: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 12 },
  addText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  cancel: { alignItems: 'center', marginTop: 12 },
  cancelText: { color: '#888' },
});
