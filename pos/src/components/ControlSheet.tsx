import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { ApiError } from '../api/client';
import { authorizeAction, fetchReasons } from '../api/pos';
import type { ControlAction, ControlKind, Reason } from '../api/types';
import { usePosStore } from '../state/store';

export type ControlFields = { reason_code: string; note?: string; percent?: string; quantity?: number };

type Props = {
  visible: boolean;
  title: string;
  kind: ControlKind;
  /** Extra input: a percent/amount field for discounts, a quantity stepper for partial voids. */
  mode?: 'none' | 'percent' | 'quantity';
  maxQuantity?: number;
  onClose: () => void;
  /** Does the action. Receives a manager's override token when one was needed. Throw ApiError on failure. */
  onRun: (fields: ControlFields, override?: string) => Promise<void>;
};

/**
 * The one dialog behind every void / comp / discount / refund: pick a reason, add a note if the reason is "Other",
 * and — if the server says this person can't do it alone — ask a manager to type their PIN, then retry once.
 */
export default function ControlSheet({ visible, title, kind, mode = 'none', maxQuantity = 1, onClose, onRun }: Props) {
  const token = usePosStore((s) => s.posSessionToken);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [percent, setPercent] = useState('');
  const [quantity, setQuantity] = useState(maxQuantity);
  const [stage, setStage] = useState<'form' | 'approval'>('form');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!visible || !token) return;
    fetchReasons(token).then((r) => setReasons(r[kind])).catch(() => setError('Could not load the reasons'));
  }, [visible, token, kind]);

  const fields = (): ControlFields => ({
    reason_code: reason,
    note: note.trim() || undefined,
    percent: mode === 'percent' ? percent.trim() : undefined,
    quantity: mode === 'quantity' && quantity < maxQuantity ? quantity : undefined,
  });

  async function submit(override?: string) {
    if (!reason) { setError('Choose a reason'); return; }
    if (mode === 'percent' && !percent.trim()) { setError('Enter a discount percentage'); return; }
    setBusy(true);
    setError('');
    try {
      await onRun(fields(), override);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403 && /approval/i.test(err.message) && !override) {
        setStage('approval');
      } else {
        setError(err instanceof ApiError ? err.message : 'Something went wrong');
      }
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!token || pin.length < 4) return;
    setBusy(true);
    setError('');
    try {
      const action = kind.toLowerCase() as ControlAction;
      const { token: override } = await authorizeAction(token, pin, action);
      setBusy(false);
      await submit(override);
    } catch (err) {
      setBusy(false);
      setError(err instanceof ApiError ? err.message : 'Could not verify that PIN');
    }
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <Text style={styles.title}>{title}</Text>
          {stage === 'approval' ? (
            <>
              <Text style={styles.sub}>This needs a manager. Ask them to enter their PIN.</Text>
              <TextInput style={styles.input} value={pin} onChangeText={setPin} placeholder="Manager PIN" secureTextEntry keyboardType="number-pad" maxLength={8} autoFocus />
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <TouchableOpacity style={[styles.primary, busy && styles.disabled]} onPress={approve} disabled={busy}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Approve</Text>}
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { setStage('form'); setPin(''); setError(''); }} style={styles.cancel}><Text style={styles.cancelText}>Back</Text></TouchableOpacity>
            </>
          ) : (
            <ScrollView keyboardShouldPersistTaps="handled">
              {mode === 'quantity' && maxQuantity > 1 && (
                <View style={styles.qtyRow}>
                  <Text style={styles.sub}>How many?</Text>
                  <View style={styles.stepper}>
                    <TouchableOpacity onPress={() => setQuantity((q) => Math.max(1, q - 1))}><Text style={styles.stepBtn}>−</Text></TouchableOpacity>
                    <Text style={styles.qty}>{quantity}</Text>
                    <TouchableOpacity onPress={() => setQuantity((q) => Math.min(maxQuantity, q + 1))}><Text style={styles.stepBtn}>+</Text></TouchableOpacity>
                  </View>
                </View>
              )}
              {mode === 'percent' && (
                <TextInput style={styles.input} value={percent} onChangeText={setPercent} placeholder="Discount %, e.g. 10" keyboardType="decimal-pad" />
              )}
              <Text style={styles.sub}>Reason</Text>
              {reasons.map((r) => (
                <TouchableOpacity key={r.code} style={[styles.reason, reason === r.code && styles.reasonOn]} onPress={() => setReason(r.code)}>
                  <Text style={[styles.reasonText, reason === r.code && styles.reasonTextOn]}>{r.label}</Text>
                </TouchableOpacity>
              ))}
              <TextInput style={styles.input} value={note} onChangeText={setNote} placeholder={reason === 'OTHER' ? 'Note (required)' : 'Note (optional)'} maxLength={300} />
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <TouchableOpacity style={[styles.primary, busy && styles.disabled]} onPress={() => submit()} disabled={busy}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Confirm</Text>}
              </TouchableOpacity>
              <TouchableOpacity onPress={onClose} style={styles.cancel}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', padding: 24 },
  sheet: { backgroundColor: '#fff', borderRadius: 16, padding: 20, maxHeight: '90%' },
  title: { fontSize: 20, fontWeight: '700', marginBottom: 8 },
  sub: { fontSize: 14, color: '#555', marginVertical: 8 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 12, fontSize: 15, marginVertical: 8 },
  reason: { borderWidth: 1, borderColor: '#ddd', borderRadius: 10, padding: 12, marginBottom: 6 },
  reasonOn: { borderColor: '#2c6f53', backgroundColor: '#e8f3ee' },
  reasonText: { fontSize: 15, color: '#333' },
  reasonTextOn: { color: '#2c6f53', fontWeight: '600' },
  qtyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  stepBtn: { fontSize: 28, paddingHorizontal: 12, color: '#2c6f53' },
  qty: { fontSize: 18, fontWeight: '700' },
  error: { color: '#c0392b', marginVertical: 6 },
  primary: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 10 },
  primaryText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  disabled: { opacity: 0.6 },
  cancel: { alignItems: 'center', marginTop: 12 },
  cancelText: { color: '#888', fontSize: 14 },
});
