import { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import { ApiError } from '../api/client';
import { fetchOpenTableSessions, fetchTab, fetchTables, fireCourse, mergeTab, moveTab, runControl } from '../api/pos';
import type { ControlKind, OpenSession, RestaurantTableRow, TabDetail, TabItem } from '../api/types';
import ControlSheet, { type ControlFields } from '../components/ControlSheet';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'TabDetail'>;

type Target = { kind: ControlKind; type: 'item' | 'tab'; id: number; title: string; mode: 'none' | 'percent' | 'quantity'; maxQuantity?: number };

/** The lines on a table's tab, where a server can void, comp or discount them — or discount the whole tab. */
export default function TabDetailScreen({ route, navigation }: Props) {
  const { sessionId } = route.params;
  const money = useMoney();
  const token = usePosStore((s) => s.posSessionToken);
  const controlsEnabled = usePosStore((s) => s.controlsEnabled);
  const [tab, setTab] = useState<TabDetail | null>(null);
  const [error, setError] = useState('');
  const [target, setTarget] = useState<Target | null>(null);
  const [picker, setPicker] = useState<'move' | 'merge' | null>(null);
  const [moveTargets, setMoveTargets] = useState<RestaurantTableRow[]>([]);
  const [mergeTargets, setMergeTargets] = useState<OpenSession[]>([]);

  const load = useCallback(() => {
    if (!token) return;
    fetchTab(token, sessionId).then(setTab).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the tab'));
  }, [token, sessionId]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function openPicker(kind: 'move' | 'merge') {
    if (!token) return;
    setError('');
    try {
      const [tables, open] = await Promise.all([fetchTables(token), fetchOpenTableSessions(token)]);
      const busy = new Set(open.sessions.map((s) => s.table_id));
      setMoveTargets(tables.filter((t) => !busy.has(t.table_id)));
      setMergeTargets(open.sessions.filter((s) => s.session_id !== sessionId));
      setPicker(kind);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load tables');
    }
  }

  async function doPick(action: () => Promise<unknown>, thenLeave: boolean) {
    try {
      await action();
      setPicker(null);
      if (thenLeave) navigation.goBack(); else load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not work');
    }
  }

  const heldCourses = Array.from(new Set((tab?.rounds ?? []).flatMap((r) => r.items).filter((i) => i.held).map((i) => i.course))).sort();

  async function run(fields: ControlFields, override?: string) {
    if (!token || !target) return;
    await runControl(token, target.kind, { type: target.type, id: target.id }, fields, override);
    load();
  }

  function open(kind: ControlKind, item: TabItem) {
    if (item.item_id == null) return;
    const verb = { VOID: 'Void', COMP: 'Comp', DISCOUNT: 'Discount', REFUND: 'Refund' }[kind];
    setTarget({
      kind, type: 'item', id: item.item_id, title: `${verb} ${item.name}`,
      mode: kind === 'VOID' ? 'quantity' : kind === 'DISCOUNT' ? 'percent' : 'none', maxQuantity: item.quantity,
    });
  }

  if (!tab) {
    return <View style={styles.center}>{error ? <Text style={styles.error}>{error}</Text> : <ActivityIndicator />}</View>;
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Table {tab.table_number}</Text>
        <Text style={styles.total}>{money(tab.total)}</Text>
      </View>
      <ScrollView>
        {tab.rounds.filter((r) => r.status !== 'CANCELLED').map((round) => (
          <View key={round.order_id} style={styles.round}>
            <Text style={styles.roundTitle}>Round {round.round_no ?? ''} · {round.order_number}</Text>
            {round.items.map((item, i) => (
              <View key={item.item_id ?? i} style={styles.line}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.lineName}>{item.quantity} × {item.name}</Text>
                  {item.options.length > 0 && <Text style={styles.meta}>{item.options.join(', ')}</Text>}
                  {Number(item.discount_amount) > 0 && <Text style={styles.meta}>−{money(item.discount_amount)} off</Text>}
                </View>
                <Text style={styles.lineTotal}>{money(item.line_total)}</Text>
                {controlsEnabled && (
                  <View style={styles.actions}>
                    <TouchableOpacity onPress={() => open('VOID', item)}><Text style={styles.action}>Void</Text></TouchableOpacity>
                    <TouchableOpacity onPress={() => open('COMP', item)}><Text style={styles.action}>Comp</Text></TouchableOpacity>
                    <TouchableOpacity onPress={() => open('DISCOUNT', item)}><Text style={styles.action}>Disc.</Text></TouchableOpacity>
                  </View>
                )}
              </View>
            ))}
          </View>
        ))}
        {tab.rounds.length === 0 && <Text style={styles.empty}>Nothing on this tab yet.</Text>}
      </ScrollView>
      {heldCourses.map((course) => (
        <TouchableOpacity key={course} style={styles.fire} onPress={() => doPick(() => fireCourse(token as string, sessionId, course), false)}>
          <Text style={styles.fireText}>Fire course {course}</Text>
        </TouchableOpacity>
      ))}
      <View style={styles.rowButtons}>
        <TouchableOpacity style={styles.smallBtn} onPress={() => openPicker('move')}><Text style={styles.smallBtnText}>Move table</Text></TouchableOpacity>
        <TouchableOpacity style={styles.smallBtn} onPress={() => openPicker('merge')}><Text style={styles.smallBtnText}>Merge into…</Text></TouchableOpacity>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {picker && (
        <View style={styles.picker}>
          <Text style={styles.pickerTitle}>{picker === 'move' ? 'Move this tab to' : 'Merge this tab into'}</Text>
          <ScrollView style={{ maxHeight: 160 }}>
            {picker === 'move'
              ? moveTargets.map((t) => (
                  <TouchableOpacity key={t.table_id} style={styles.pickerRow} onPress={() => doPick(() => moveTab(token as string, sessionId, t.table_id), true)}>
                    <Text>Table {t.table_number}</Text>
                  </TouchableOpacity>
                ))
              : mergeTargets.map((s) => (
                  <TouchableOpacity key={s.session_id} style={styles.pickerRow} onPress={() => doPick(() => mergeTab(token as string, sessionId, s.session_id), true)}>
                    <Text>Table {s.table_number}{s.tab_name ? ` · ${s.tab_name}` : ''}</Text>
                  </TouchableOpacity>
                ))}
            {(picker === 'move' ? moveTargets : mergeTargets).length === 0 && <Text style={styles.empty}>Nothing available</Text>}
          </ScrollView>
          <TouchableOpacity onPress={() => setPicker(null)}><Text style={styles.backText}>Cancel</Text></TouchableOpacity>
        </View>
      )}
      {controlsEnabled && <TouchableOpacity style={styles.discountTab} onPress={() => setTarget({ kind: 'DISCOUNT', type: 'tab', id: sessionId, title: 'Discount the whole tab', mode: 'percent' })}>
        <Text style={styles.discountTabText}>Discount whole tab</Text>
      </TouchableOpacity>}
      <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}><Text style={styles.backText}>Back</Text></TouchableOpacity>
      {target && (
        <ControlSheet
          visible
          title={target.title}
          kind={target.kind}
          mode={target.mode}
          maxQuantity={target.maxQuantity}
          onClose={() => setTarget(null)}
          onRun={run}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff', padding: 20 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 },
  title: { fontSize: 24, fontWeight: '700' },
  total: { fontSize: 22, fontWeight: '700', color: '#2c6f53' },
  round: { marginBottom: 16 },
  roundTitle: { fontSize: 13, color: '#888', textTransform: 'uppercase', marginBottom: 6 },
  line: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#f0f0f0', gap: 8 },
  lineName: { fontSize: 16, fontWeight: '600' },
  meta: { fontSize: 12, color: '#888' },
  lineTotal: { fontSize: 16, fontWeight: '600', minWidth: 64, textAlign: 'right' },
  actions: { flexDirection: 'row', gap: 12 },
  action: { color: '#2c6f53', fontSize: 14, fontWeight: '600' },
  empty: { color: '#888', textAlign: 'center', marginTop: 24 },
  discountTab: { borderWidth: 1, borderColor: '#2c6f53', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 8 },
  discountTabText: { color: '#2c6f53', fontWeight: '600', fontSize: 16 },
  back: { alignItems: 'center', marginTop: 12 },
  backText: { color: '#888' },
  error: { color: '#c0392b', marginTop: 6 },
  fire: { backgroundColor: '#e67e22', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 8 },
  fireText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  rowButtons: { flexDirection: 'row', gap: 8, marginTop: 8 },
  smallBtn: { flex: 1, borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 12, alignItems: 'center' },
  smallBtnText: { color: '#333', fontWeight: '600' },
  picker: { borderWidth: 1, borderColor: '#ddd', borderRadius: 12, padding: 12, marginTop: 8 },
  pickerTitle: { fontWeight: '700', marginBottom: 6 },
  pickerRow: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
});
