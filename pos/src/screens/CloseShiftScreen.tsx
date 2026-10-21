import { useState } from 'react';
import {
  ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text,
  TextInput, TouchableOpacity, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { useMoney } from '../utils/money';
import { closeShift } from '../api/pos';
import type { ShiftReportRead } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'CloseShift'>;

export default function CloseShiftScreen({ navigation }: Props) {
  const money = useMoney();
  const shift = usePosStore((s) => s.shift);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const setShift = usePosStore((s) => s.setShift);
  const tipsEnabled = usePosStore((s) => s.tipsEnabled);
  const [countedCash, setCountedCash] = useState('');
  const [cashTips, setCashTips] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<ShiftReportRead | null>(null);

  async function submit() {
    if (!posSessionToken || !shift || !countedCash.trim()) return;
    Keyboard.dismiss();
    setBusy(true);
    setError('');
    try {
      const result = await closeShift(posSessionToken, shift.shift_id, countedCash.trim(), cashTips.trim() || '0');
      setReport(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not close the shift');
    } finally {
      setBusy(false);
    }
  }

  function done() {
    setShift(null); // the navigator falls back to OpenShiftScreen automatically
  }

  if (report) {
    const variance = Number(report.variance ?? 0);
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Shift closed</Text>
        <View style={styles.row}><Text style={styles.label}>Expected cash</Text><Text style={styles.value}>{money(report.expected_cash)}</Text></View>
        <View style={styles.row}><Text style={styles.label}>Counted cash</Text><Text style={styles.value}>{money(report.counted_cash ?? 0)}</Text></View>
        <View style={styles.row}>
          <Text style={styles.label}>Variance</Text>
          <Text style={[styles.value, variance === 0 ? styles.ok : styles.variance]}>
            {variance > 0 ? '+' : ''}{money(variance)}
          </Text>
        </View>
        {Number(report.cash_tips) > 0 && (
          <View style={styles.row}><Text style={styles.label}>Cash tips declared</Text><Text style={styles.value}>{money(report.cash_tips)}</Text></View>
        )}
        {Number(report.card_tips) > 0 && (
          <View style={styles.row}><Text style={styles.label}>Card tips</Text><Text style={styles.value}>{money(report.card_tips)}</Text></View>
        )}
        <View style={styles.row}><Text style={styles.label}>Card total</Text><Text style={styles.value}>{money(report.card_total)}</Text></View>
        <View style={styles.row}><Text style={styles.label}>Orders</Text><Text style={styles.value}>{report.order_count}</Text></View>
        <TouchableOpacity style={styles.button} onPress={done}>
          <Text style={styles.buttonText}>Done</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Close the till</Text>
        <Text style={styles.subtitle}>Count the cash drawer and enter what&apos;s actually there.</Text>
        <TextInput
          style={styles.input}
          value={countedCash}
          onChangeText={setCountedCash}
          placeholder="Counted cash, e.g. 63.20"
          keyboardType="decimal-pad"
          returnKeyType="done"
          onSubmitEditing={submit}
          blurOnSubmit
        />
        {tipsEnabled && (
          <TextInput
            style={styles.input}
            value={cashTips}
            onChangeText={setCashTips}
            placeholder="Cash tips in the drawer (if any)"
            keyboardType="decimal-pad"
            returnKeyType="done"
          />
        )}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={submit} disabled={busy}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Close shift</Text>}
        </TouchableOpacity>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.cancel}>
          <Text style={styles.cancelText}>Cancel</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, justifyContent: 'center', padding: 32, backgroundColor: '#fff' },
  title: { fontSize: 24, fontWeight: '700', marginBottom: 8 },
  subtitle: { fontSize: 15, color: '#555', marginBottom: 24, lineHeight: 21 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 14, fontSize: 15, marginBottom: 16 },
  error: { color: '#c0392b', marginBottom: 12 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 16, alignItems: 'center', marginTop: 8 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
  cancel: { marginTop: 16, alignItems: 'center' },
  cancelText: { color: '#999', fontSize: 13 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  label: { fontSize: 15, color: '#555' },
  value: { fontSize: 17, fontWeight: '700' },
  ok: { color: '#2c6f53' },
  variance: { color: '#c0392b' },
});
