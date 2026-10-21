import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import PairingScreen from '../screens/PairingScreen';
import PinEntryScreen from '../screens/PinEntryScreen';
import ClockInScreen from '../screens/ClockInScreen';
import OpenShiftScreen from '../screens/OpenShiftScreen';
import OrderScreen from '../screens/OrderScreen';
import CashTenderScreen from '../screens/CashTenderScreen';
import CardTenderScreen from '../screens/CardTenderScreen';
import TableTenderScreen from '../screens/TableTenderScreen';
import TableCardTenderScreen from '../screens/TableCardTenderScreen';
import CloseShiftScreen from '../screens/CloseShiftScreen';
import ClockOutScreen from '../screens/ClockOutScreen';
import CashMovementScreen from '../screens/CashMovementScreen';
import { usePosStore } from '../state/store';

export type RootStackParamList = {
  Pairing: undefined;
  PinEntry: undefined;
  Loading: undefined;
  ClockIn: undefined;
  OpenShift: undefined;
  Order: undefined;
  CashTender: { orderId: number; orderNumber: string; total: string };
  CardTender: { orderId: number; orderNumber: string; total: string };
  TableTender: { sessionId: number; tableNumber: string; total: string };
  TableCardTender: { sessionId: number; tableNumber: string; total: string };
  CloseShift: undefined;
  ClockOut: undefined;
  CashMovement: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const deviceReady = usePosStore((s) => s.deviceReady);
  const deviceToken = usePosStore((s) => s.deviceToken);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const shift = usePosStore((s) => s.shift);
  const shiftChecked = usePosStore((s) => s.shiftChecked);
  const deviceKind = usePosStore((s) => s.deviceKind);
  const timeEntry = usePosStore((s) => s.timeEntry);
  const timeEntryChecked = usePosStore((s) => s.timeEntryChecked);
  const loadDevice = usePosStore((s) => s.loadDevice);
  const loadShift = usePosStore((s) => s.loadShift);
  const loadTimeEntry = usePosStore((s) => s.loadTimeEntry);

  useEffect(() => {
    loadDevice();
  }, [loadDevice]);

  useEffect(() => {
    if (deviceToken) loadShift();
  }, [deviceToken, loadShift]);

  useEffect(() => {
    if (posSessionToken) loadTimeEntry();
  }, [posSessionToken, loadTimeEntry]);

  if (!deviceReady) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  const orderStack = (
    <>
      <Stack.Screen name="Order" component={OrderScreen} />
      <Stack.Screen name="CashTender" component={CashTenderScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="CardTender" component={CardTenderScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="TableTender" component={TableTenderScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="TableCardTender" component={TableCardTenderScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="CloseShift" component={CloseShiftScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="ClockOut" component={ClockOutScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="CashMovement" component={CashMovementScreen} options={{ presentation: 'modal' }} />
    </>
  );

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!deviceToken ? (
          <Stack.Screen name="Pairing" component={PairingScreen} />
        ) : !posSessionToken ? (
          <Stack.Screen name="PinEntry" component={PinEntryScreen} />
        ) : !timeEntryChecked ? (
          <Stack.Screen name="Loading" component={Loading} />
        ) : !timeEntry ? (
          <Stack.Screen name="ClockIn" component={ClockInScreen} />
        ) : deviceKind === 'HANDHELD' ? (
          // A server's handheld has no cash drawer, so no float gate: straight to ordering.
          orderStack
        ) : !shiftChecked ? (
          <Stack.Screen name="Loading" component={Loading} />
        ) : !shift ? (
          <Stack.Screen name="OpenShift" component={OpenShiftScreen} />
        ) : (
          orderStack
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

function Loading() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <ActivityIndicator />
    </View>
  );
}
