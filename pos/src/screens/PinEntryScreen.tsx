import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
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
    if (busy || key === '') return;
    if (key === 'del') return setPin((p) => p.slice(0, -1));
    if (pin.length >= 8) return;
    const next = pin + key;
    setPin(next);
    if (next.length === 4) submit(next);
  }

  return (
    <ScrollView
      contentContainerStyle={styles.scrollContent}
      showsVerticalScrollIndicator={false}
    >
      <Text style={styles.title}>Enter your PIN</Text>
      <View style={styles.dots}>
        {[0, 1, 2, 3].map((i) => (
          <View key={i} style={[styles.dot, i < pin.length && styles.dotFilled]} />
        ))}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {busy && <ActivityIndicator style={{ marginBottom: 8 }} />}
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
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    flexGrow: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff',
    paddingVertical: 16, paddingHorizontal: 16,
  },
  title: { fontSize: 18, fontWeight: '700', marginBottom: 10 },
  dots: { flexDirection: 'row', gap: 10, marginBottom: 10 },
  dot: { width: 12, height: 12, borderRadius: 6, borderWidth: 1, borderColor: '#999' },
  dotFilled: { backgroundColor: '#2c6f53', borderColor: '#2c6f53' },
  error: { color: '#c0392b', marginBottom: 8, fontSize: 13 },
  // 3 columns, capped so this always fits a short landscape phone screen as well as an iPad.
  pad: { flexDirection: 'row', flexWrap: 'wrap', width: 198, justifyContent: 'center' },
  key: {
    width: 56, height: 56, margin: 5, borderRadius: 28, backgroundColor: '#f0f0f0',
    alignItems: 'center', justifyContent: 'center',
  },
  keyHidden: { backgroundColor: 'transparent' },
  keyText: { fontSize: 20, fontWeight: '600' },
  unpair: { marginTop: 14 },
  unpairText: { color: '#999', fontSize: 12 },
});
