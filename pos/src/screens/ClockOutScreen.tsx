import { useState } from 'react';
import {
  ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text,
  TextInput, TouchableOpacity, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { clockOut } from '../api/pos';
import type { TimeEntryRead } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'ClockOut'>;

/** A handheld server's cash-up: they have no drawer, so at clock-out they count what they're carrying. */
export default function ClockOutScreen({ navigation }: Props) {
  const money = useMoney();
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const setTimeEntry = usePosStore((s) => s.setTimeEntry);
  const tipsEnabled = usePosStore((s) => s.tipsEnabled);
  const [counted, setCounted] = useState('');
  const [tips, setTips] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<TimeEntryRead | null>(null);

  async function submit() {
    if (!posSessionToken || !counted.trim()) return;
    Keyboard.dismiss();
    setBusy(true);
    setError('');
    try {
      setResult(await clockOut(posSessionToken, { countedCash: counted.trim(), cashTips: tips.trim() || '0' }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not clock out');
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    const variance = Number(result.variance ?? 0);
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Clocked out</Text>
        <View style={styles.row}><Text style={styles.label}>Cash you took</Text><Text style={styles.value}>{money(result.expected_cash)}</Text></View>
        <View style={styles.row}><Text style={styles.label}>Cash counted</Text><Text style={styles.value}>{money(result.counted_cash ?? 0)}</Text></View>
        {Number(result.cash_tips) > 0 && (
          <View style={styles.row}><Text style={styles.label}>Cash tips</Text><Text style={styles.value}>{money(result.cash_tips)}</Text></View>
        )}
        <View style={styles.row}>
          <Text style={styles.label}>Variance</Text>
          <Text style={[styles.value, variance === 0 ? styles.ok : styles.bad]}>{variance > 0 ? '+' : ''}{money(variance)}</Text>
        </View>
        <TouchableOpacity style={styles.button} onPress={() => setTimeEntry(null)}>
          <Text style={styles.buttonText}>Done</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Cash up</Text>
        <Text style={styles.subtitle}>Count the cash you&apos;re carrying before you clock out.</Text>
        <TextInput style={styles.input} value={counted} onChangeText={setCounted} placeholder="Cash on hand, e.g. 63.20" keyboardType="decimal-pad" returnKeyType="done" />
        {tipsEnabled && (
          <TextInput style={styles.input} value={tips} onChangeText={setTips} placeholder="Cash tips among it (if any)" keyboardType="decimal-pad" returnKeyType="done" />
        )}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={submit} disabled={busy}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Clock out</Text>}
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
  bad: { color: '#c0392b' },
});
