import { useState } from 'react';
import {
  ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput,
  TouchableOpacity, TouchableWithoutFeedback, View,
} from 'react-native';
import { ApiError } from '../api/client';
import { openShift } from '../api/pos';
import { usePosStore } from '../state/store';

export default function OpenShiftScreen() {
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const setShift = usePosStore((s) => s.setShift);
  const logoutPin = usePosStore((s) => s.logoutPin);
  const [startingFloat, setStartingFloat] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    if (!posSessionToken || !startingFloat.trim()) return;
    Keyboard.dismiss();
    setBusy(true);
    setError('');
    try {
      const shift = await openShift(posSessionToken, startingFloat.trim());
      setShift(shift);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not open the shift');
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <View style={styles.container}>
          <Text style={styles.title}>Open the till</Text>
          <Text style={styles.subtitle}>
            Count the cash drawer and enter the starting float before taking any orders.
          </Text>
          <TextInput
            style={styles.input}
            value={startingFloat}
            onChangeText={setStartingFloat}
            placeholder="Starting float, e.g. 50.00"
            keyboardType="decimal-pad"
            returnKeyType="done"
            onSubmitEditing={submit}
            blurOnSubmit
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={submit} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Start shift</Text>}
          </TouchableOpacity>
          <TouchableOpacity onPress={logoutPin} style={styles.switchUser}>
            <Text style={styles.switchUserText}>Switch user</Text>
          </TouchableOpacity>
        </View>
      </TouchableWithoutFeedback>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 32, backgroundColor: '#fff' },
  title: { fontSize: 28, fontWeight: '700', marginBottom: 8 },
  subtitle: { fontSize: 15, color: '#555', marginBottom: 24, lineHeight: 21 },
  input: {
    borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 14, fontSize: 15, marginBottom: 16,
  },
  error: { color: '#c0392b', marginBottom: 12 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 16, alignItems: 'center' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
  switchUser: { marginTop: 16, alignItems: 'center' },
  switchUserText: { color: '#999', fontSize: 13 },
});
