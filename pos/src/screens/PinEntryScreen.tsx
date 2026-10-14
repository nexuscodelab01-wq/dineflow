import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { ApiError } from '../api/client';
import { pinLogin } from '../api/pos';
import { usePosStore } from '../state/store';

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'del'];

export default function PinEntryScreen() {
  const deviceToken = usePosStore((s) => s.deviceToken);
  const unpair = usePosStore((s) => s.unpair);
  const loginWithPin = usePosStore((s) => s.loginWithPin);
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function press(key: string) {
    if (busy) return;
    if (key === 'del') return setPin((p) => p.slice(0, -1));
    if (key === '') return;
    if (pin.length >= 8) return;
    setPin((p) => p + key);
  }

  async function submit(currentPin: string) {
    if (!deviceToken || currentPin.length < 4) return;
    setBusy(true);
    setError('');
    try {
      const result = await pinLogin(deviceToken, currentPin);
      loginWithPin(result.pos_session_token, result.staff_name);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not log in');
      setPin('');
    } finally {
      setBusy(false);
    }
  }

  function onPress(key: string) {
    press(key);
    const next = key === 'del' ? pin.slice(0, -1) : key === '' ? pin : pin + key;
    if (key !== 'del' && key !== '' && next.length === 4) submit(next);
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Enter your PIN</Text>
      <View style={styles.dots}>
        {[0, 1, 2, 3].map((i) => (
          <View key={i} style={[styles.dot, i < pin.length && styles.dotFilled]} />
        ))}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {busy && <ActivityIndicator style={{ marginBottom: 12 }} />}
      <View style={styles.pad}>
        {KEYS.map((key, i) => (
          <TouchableOpacity
            key={i}
            style={[styles.key, key === '' && styles.keyHidden]}
            onPress={() => onPress(key)}
            disabled={key === '' || busy}
          >
            <Text style={styles.keyText}>{key === 'del' ? '⌫' : key}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TouchableOpacity onPress={unpair} style={styles.unpair}>
        <Text style={styles.unpairText}>Unpair this device</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff' },
  title: { fontSize: 24, fontWeight: '700', marginBottom: 24 },
  dots: { flexDirection: 'row', gap: 16, marginBottom: 16 },
  dot: { width: 16, height: 16, borderRadius: 8, borderWidth: 1, borderColor: '#999' },
  dotFilled: { backgroundColor: '#2c6f53', borderColor: '#2c6f53' },
  error: { color: '#c0392b', marginBottom: 12 },
  pad: { flexDirection: 'row', flexWrap: 'wrap', width: 260, justifyContent: 'center' },
  key: {
    width: 76, height: 76, margin: 6, borderRadius: 38, backgroundColor: '#f0f0f0',
    alignItems: 'center', justifyContent: 'center',
  },
  keyHidden: { backgroundColor: 'transparent' },
  keyText: { fontSize: 26, fontWeight: '600' },
  unpair: { marginTop: 32 },
  unpairText: { color: '#999', fontSize: 13 },
});
