import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useStripeTerminal } from '@stripe/stripe-terminal-react-native';
import type { Reader } from '@stripe/stripe-terminal-react-native';
import { ApiError } from '../api/client';
import { createCardIntent } from '../api/pos';
import { usePosStore } from '../state/store';
import type { RootStackParamList } from '../navigation/RootNavigator';
import { useMoney } from '../utils/money';

type Props = NativeStackScreenProps<RootStackParamList, 'CardTender'>;

type Stage = 'connecting' | 'waiting_for_card' | 'processing' | 'paid' | 'error';

export default function CardTenderScreen({ route, navigation }: Props) {
  const money = useMoney();
  const { orderId, orderNumber, total } = route.params;
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const tipsEnabled = usePosStore((s) => s.tipsEnabled);
  const [stage, setStage] = useState<Stage>('connecting');
  const [error, setError] = useState('');
  const connectedReader = useRef<Reader.Type | null>(null);
  const started = useRef(false);

  const { discoverReaders, connectReader, retrievePaymentIntent, processPaymentIntent } = useStripeTerminal({
    onUpdateDiscoveredReaders: (readers) => {
      if (readers.length > 0 && !connectedReader.current) {
        handleConnect(readers[0]);
      }
    },
  });

  async function handleConnect(reader: Reader.Type) {
    if (!reader.locationId) {
      setError('The discovered reader has no location');
      setStage('error');
      return;
    }
    const { reader: connected, error: connectError } = await connectReader({
      discoveryMethod: 'bluetoothScan',
      reader,
      locationId: reader.locationId,
    });
    if (connectError || !connected) {
      setError(connectError?.message ?? 'Could not connect to the card reader');
      setStage('error');
      return;
    }
    connectedReader.current = connected;
    await chargeCard();
  }

  async function chargeCard() {
    if (!posSessionToken) return;
    setStage('waiting_for_card');
    setError('');
    try {
      const intentResult = await createCardIntent(posSessionToken, orderId);
      if (!intentResult.client_secret) {
        // The mock provider settled synchronously (backend tests / no reader attached) — nothing left
        // for the reader to do.
        setStage('paid');
        return;
      }
      const { paymentIntent, error: retrieveError } = await retrievePaymentIntent(intentResult.client_secret);
      if (retrieveError || !paymentIntent) {
        setError(retrieveError?.message ?? 'Could not start the card payment');
        setStage('error');
        return;
      }
      setStage('processing');
      const { error: processError } = await processPaymentIntent({ paymentIntent, skipTipping: !tipsEnabled });
      if (processError) {
        setError(processError.message ?? 'The card was declined');
        setStage('error');
        return;
      }
      setStage('paid');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not process the card payment');
      setStage('error');
    }
  }

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    discoverReaders({ discoveryMethod: 'bluetoothScan', simulated: true }).then(({ error: discoverError }) => {
      if (discoverError) {
        setError(discoverError.message ?? 'Could not find a card reader');
        setStage('error');
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function retry() {
    started.current = false;
    connectedReader.current = null;
    setStage('connecting');
    setError('');
    discoverReaders({ discoveryMethod: 'bluetoothScan', simulated: true });
  }

  const statusText: Record<Stage, string> = {
    connecting: 'Connecting to the card reader…',
    waiting_for_card: 'Starting the payment…',
    processing: 'Processing — please wait…',
    paid: 'Paid — card',
    error: 'Something went wrong',
  };

  return (
    <View style={styles.container}>
      <Text style={styles.orderNumber}>Order {orderNumber}</Text>
      <Text style={styles.total}>{money(total)}</Text>

      {stage === 'paid' ? (
        <>
          <Text style={styles.paidText}>{statusText.paid}</Text>
          <TouchableOpacity style={styles.button} onPress={() => navigation.popToTop()}>
            <Text style={styles.buttonText}>New order</Text>
          </TouchableOpacity>
        </>
      ) : stage === 'error' ? (
        <>
          <Text style={styles.error}>{error}</Text>
          <TouchableOpacity style={styles.button} onPress={retry}>
            <Text style={styles.buttonText}>Try again</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.secondaryButton}
            onPress={() => navigation.replace('CashTender', { orderId, orderNumber, total })}
          >
            <Text style={styles.secondaryButtonText}>Pay cash instead</Text>
          </TouchableOpacity>
        </>
      ) : (
        <>
          <ActivityIndicator style={{ marginBottom: 16 }} />
          <Text style={styles.statusText}>{statusText[stage]}</Text>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', padding: 32 },
  orderNumber: { fontSize: 18, color: '#555', marginBottom: 8 },
  total: { fontSize: 48, fontWeight: '800', marginBottom: 32 },
  statusText: { fontSize: 16, color: '#555' },
  paidText: { fontSize: 20, fontWeight: '700', color: '#2c6f53', marginBottom: 24 },
  error: { color: '#c0392b', marginBottom: 16, textAlign: 'center' },
  button: { backgroundColor: '#2c6f53', borderRadius: 10, paddingVertical: 18, paddingHorizontal: 40 },
  buttonText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  secondaryButton: { marginTop: 16, paddingVertical: 10, paddingHorizontal: 20 },
  secondaryButtonText: { color: '#2c6f53', fontSize: 15, fontWeight: '600' },
});
