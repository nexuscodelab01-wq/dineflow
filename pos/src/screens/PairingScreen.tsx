import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { usePosStore } from '../state/store';

// Milestone 1: plain text-entry pairing only (the admin's /admin/devices pairing response shows the
// device_token once; it's typed or pasted in here). QR-scan pairing is a trivial polish pass for later,
// deliberately not built now — see the plan's open-questions note.
export default function PairingScreen() {
  const pair = usePosStore((s) => s.pair);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    if (!code.trim()) return;
    setBusy(true);
    setError('');
    try {
      await pair(code.trim());
    } catch {
      setError('Could not save the pairing code. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Pair this iPad</Text>
      <Text style={styles.subtitle}>
        Ask a manager to pair this device from the admin dashboard (Settings → Devices), then enter the
        pairing code shown there.
      </Text>
      <TextInput
        style={styles.input}
        value={code}
        onChangeText={setCode}
        placeholder="Pairing code"
        autoCapitalize="none"
        autoCorrect={false}
        multiline
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={submit} disabled={busy}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Pair device</Text>}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 32, backgroundColor: '#fff' },
  title: { fontSize: 28, fontWeight: '700', marginBottom: 8 },
  subtitle: { fontSize: 15, color: '#555', marginBottom: 24, lineHeight: 21 },
  input: {
    borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 14, fontSize: 15,
    minHeight: 80, textAlignVertical: 'top', marginBottom: 16,
  },
  error: { color: '#c0392b', marginBottom: 12 },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 16, alignItems: 'center' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
});
