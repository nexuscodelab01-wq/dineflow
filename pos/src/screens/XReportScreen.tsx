import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import { fetchXReport } from '../api/pos';
import type { ShiftReportRead } from '../api/types';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'XReport'>;

/** Where the till stands right now — the Z-report's figures without closing anything. */
export default function XReportScreen({ navigation }: Props) {
  const money = useMoney();
  const token = usePosStore((s) => s.posSessionToken);
  const [report, setReport] = useState<ShiftReportRead | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    fetchXReport(token).then(setReport).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the report'));
  }, [token]);

  const rows: [string, string][] = report
    ? [
        ['Opened', `${new Date(report.opened_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}${report.opened_by ? ` by ${report.opened_by}` : ''}`],
        ['Starting float', money(report.starting_float)],
        ['Cash taken', money(report.cash_total)],
        ['Card taken', money(report.card_total)],
        ['Sales', String(report.order_count)],
        ['Card tips', money(report.card_tips)],
        ['Cash that should be in the drawer', money(report.expected_cash)],
      ]
    : [];

  return (
    <View style={styles.container}>
      <Text style={styles.title}>X-report</Text>
      <Text style={styles.sub}>A snapshot — nothing is closed or reset.</Text>
      {error ? <Text style={styles.error}>{error}</Text> : !report ? <ActivityIndicator /> : (
        <ScrollView>
          {rows.map(([label, value]) => (
            <View key={label} style={styles.row}><Text style={styles.label}>{label}</Text><Text style={styles.value}>{value}</Text></View>
          ))}
        </ScrollView>
      )}
      <TouchableOpacity style={styles.button} onPress={() => navigation.goBack()}><Text style={styles.buttonText}>Close</Text></TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff', padding: 28 },
  title: { fontSize: 24, fontWeight: '700' },
  sub: { color: '#888', marginBottom: 16 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  label: { fontSize: 15, color: '#555', flex: 1 },
  value: { fontSize: 17, fontWeight: '700' },
  error: { color: '#c0392b' },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, padding: 16, alignItems: 'center', marginTop: 16 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
});
