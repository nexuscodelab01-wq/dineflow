import { useRef, useState } from 'react';
import {
  ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput,
  TouchableOpacity, TouchableWithoutFeedback, View,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import type { BarcodeScanningResult } from 'expo-camera';
import { usePosStore } from '../state/store';

// QR-scan pairing (default) — the device_token is a long signed JWT, never meant to be typed or
// copy-pasted by a human; a QR code (shown on the admin's /admin/devices screen) is the right way to
// hand it to an iPad. Manual entry stays as a fallback for when the camera can't be used.
export default function PairingScreen() {
  const pair = usePosStore((s) => s.pair);
  const [mode, setMode] = useState<'scan' | 'manual'>('scan');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [permission, requestPermission] = useCameraPermissions();
  const scanned = useRef(false);

  async function submitCode(value: string) {
    if (!value.trim() || busy) return;
    Keyboard.dismiss();
    setBusy(true);
    setError('');
    try {
      await pair(value.trim());
    } catch {
      setError('Could not save the pairing code. Try again.');
      scanned.current = false;
    } finally {
      setBusy(false);
    }
  }

  function onScan(result: BarcodeScanningResult) {
    if (scanned.current) return;
    scanned.current = true;
    submitCode(result.data);
  }

  if (mode === 'scan') {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Pair this iPad</Text>
        <Text style={styles.subtitle}>
          Scan the pairing QR code shown on the admin dashboard (POS devices → Pair a device).
        </Text>

        {!permission ? (
          <ActivityIndicator style={{ marginTop: 24 }} />
        ) : !permission.granted ? (
          <View style={styles.permissionBox}>
            <Text style={styles.permissionText}>DineFlow POS needs camera access to scan the code.</Text>
            <TouchableOpacity style={styles.button} onPress={requestPermission}>
              <Text style={styles.buttonText}>Allow camera</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.cameraBox}>
            <CameraView
              style={styles.camera}
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
              onBarcodeScanned={busy ? undefined : onScan}
            />
            {busy && (
              <View style={[StyleSheet.absoluteFill, styles.cameraOverlay]}>
                <ActivityIndicator color="#fff" />
              </View>
            )}
          </View>
        )}

        {error ? <Text style={styles.error}>{error}</Text> : null}
        <TouchableOpacity onPress={() => { setMode('manual'); setError(''); }} style={styles.switchMode}>
          <Text style={styles.switchModeText}>Enter the code manually instead</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <View style={styles.container}>
          <Text style={styles.title}>Pair this iPad</Text>
          <Text style={styles.subtitle}>
            Ask a manager to pair this device from the admin dashboard (POS devices), then enter the
            pairing code shown there.
          </Text>
          <TextInput
            style={styles.input}
            value={code}
            onChangeText={setCode}
            placeholder="Pairing code"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="done"
            onSubmitEditing={() => submitCode(code)}
            blurOnSubmit
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <TouchableOpacity style={[styles.button, busy && styles.buttonDisabled]} onPress={() => submitCode(code)} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Pair device</Text>}
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { setMode('scan'); setError(''); }} style={styles.switchMode}>
            <Text style={styles.switchModeText}>Scan a QR code instead</Text>
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
  switchMode: { marginTop: 20, alignItems: 'center' },
  switchModeText: { color: '#2c6f53', fontSize: 14, fontWeight: '600' },
  permissionBox: { alignItems: 'center', marginTop: 16 },
  permissionText: { fontSize: 14, color: '#555', marginBottom: 16, textAlign: 'center' },
  cameraBox: {
    height: 280, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000', marginTop: 8,
  },
  camera: { flex: 1 },
  cameraOverlay: {
    backgroundColor: 'rgba(0,0,0,0.5)', alignItems: 'center', justifyContent: 'center',
  },
});
