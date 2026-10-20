import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { ApiError } from '../api/client';
import { clockIn } from '../api/pos';
import { usePosStore } from '../state/store';

export default function ClockInScreen() {
  const staffName = usePosStore((s) => s.staffName);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const setTimeEntry = usePosStore((s) => s.setTimeEntry);
  const logoutPin = usePosStore((s) => s.logoutPin);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    if (!posSessionToken) return;
    setBusy(true);
    setError('');
    try {
      const entry = await clockIn(posSessionToken);
      setTimeEntry(entry);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not clock in');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Hi, {staffName}</Text>
      <Text style={styles.subtitle}>Clock in to start your shift.</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={submit} disabled={busy}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Clock in</Text>}
      </TouchableOpacity>
      <TouchableOpacity onPress={logoutPin} style={styles.switchUser}>
        <Text style={styles.switchUserText}>Switch user</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 32, backgroundColor: '#fff' },
  title: { fontSize: 28, fontWeight: '700', marginBottom: 8 },
  subtitle: { fontSize: 15, color: '#555', marginBottom: 24, lineHeight: 21 },
  error: { color: '#c0392b', marginBottom: 12 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 16, alignItems: 'center' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
  switchUser: { marginTop: 16, alignItems: 'center' },
  switchUserText: { color: '#999', fontSize: 13 },
});
