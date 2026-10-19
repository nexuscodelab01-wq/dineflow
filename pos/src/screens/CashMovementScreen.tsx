import { useState } from 'react';
import {
  ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { recordCashMovement } from '../api/pos';
import type { CashMovementKind } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'CashMovement'>;

export default function CashMovementScreen({ navigation }: Props) {
  const shift = usePosStore((s) => s.shift);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const [kind, setKind] = useState<CashMovementKind>('PAID_OUT');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    if (!posSessionToken || !shift || !amount.trim() || !reason.trim()) return;
    Keyboard.dismiss();
    setBusy(true);
    setError('');
    try {
      await recordCashMovement(posSessionToken, shift.shift_id, kind, amount.trim(), reason.trim());
      navigation.goBack();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not record the cash movement');
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.container}>
        <Text style={styles.title}>Cash in/out</Text>

        <View style={styles.toggle}>
          <TouchableOpacity
            style={[styles.toggleButton, kind === 'PAID_IN' && styles.toggleButtonActive]}
            onPress={() => setKind('PAID_IN')}
          >
            <Text style={[styles.toggleText, kind === 'PAID_IN' && styles.toggleTextActive]}>Paid in</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.toggleButton, kind === 'PAID_OUT' && styles.toggleButtonActive]}
            onPress={() => setKind('PAID_OUT')}
          >
            <Text style={[styles.toggleText, kind === 'PAID_OUT' && styles.toggleTextActive]}>Paid out</Text>
          </TouchableOpacity>
        </View>

        <TextInput
          style={styles.input}
          value={amount}
          onChangeText={setAmount}
          placeholder="Amount, e.g. 10.00"
          keyboardType="decimal-pad"
        />
        <TextInput
          style={styles.input}
          value={reason}
          onChangeText={setReason}
          placeholder="Reason, e.g. Driver's cash tip"
          returnKeyType="done"
          onSubmitEditing={submit}
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={submit} disabled={busy}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Save</Text>}
        </TouchableOpacity>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.cancel}>
          <Text style={styles.cancelText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 32, backgroundColor: '#fff' },
  title: { fontSize: 24, fontWeight: '700', marginBottom: 24 },
  toggle: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  toggleButton: { flex: 1, paddingVertical: 10, borderRadius: 20, backgroundColor: '#f0f0f0', alignItems: 'center' },
  toggleButtonActive: { backgroundColor: '#2c6f53' },
  toggleText: { fontWeight: '600', color: '#333' },
  toggleTextActive: { color: '#fff' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 14, fontSize: 15, marginBottom: 16 },
  error: { color: '#c0392b', marginBottom: 12 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 16, alignItems: 'center' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
  cancel: { marginTop: 16, alignItems: 'center' },
  cancelText: { color: '#999', fontSize: 13 },
});
