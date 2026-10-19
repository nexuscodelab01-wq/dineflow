import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import PairingScreen from '../screens/PairingScreen';
import PinEntryScreen from '../screens/PinEntryScreen';
import OpenShiftScreen from '../screens/OpenShiftScreen';
import OrderScreen from '../screens/OrderScreen';
import CashTenderScreen from '../screens/CashTenderScreen';
import CardTenderScreen from '../screens/CardTenderScreen';
import CloseShiftScreen from '../screens/CloseShiftScreen';
import CashMovementScreen from '../screens/CashMovementScreen';
import { usePosStore } from '../state/store';

export type RootStackParamList = {
  Pairing: undefined;
  PinEntry: undefined;
  ShiftLoading: undefined;
  OpenShift: undefined;
  Order: undefined;
  CashTender: { orderId: number; orderNumber: string; total: string };
  CardTender: { orderId: number; orderNumber: string; total: string };
  CloseShift: undefined;
  CashMovement: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const deviceReady = usePosStore((s) => s.deviceReady);
  const deviceToken = usePosStore((s) => s.deviceToken);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const shift = usePosStore((s) => s.shift);
  const shiftChecked = usePosStore((s) => s.shiftChecked);
  const loadDevice = usePosStore((s) => s.loadDevice);
  const loadShift = usePosStore((s) => s.loadShift);

  useEffect(() => {
    loadDevice();
  }, [loadDevice]);

  useEffect(() => {
    if (deviceToken) loadShift();
  }, [deviceToken, loadShift]);

  if (!deviceReady) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!deviceToken ? (
          <Stack.Screen name="Pairing" component={PairingScreen} />
        ) : !posSessionToken ? (
          <Stack.Screen name="PinEntry" component={PinEntryScreen} />
        ) : !shiftChecked ? (
          <Stack.Screen name="ShiftLoading" component={LoadingShift} />
        ) : !shift ? (
          <Stack.Screen name="OpenShift" component={OpenShiftScreen} />
        ) : (
          <>
            <Stack.Screen name="Order" component={OrderScreen} />
            <Stack.Screen name="CashTender" component={CashTenderScreen} options={{ presentation: 'modal' }} />
            <Stack.Screen name="CardTender" component={CardTenderScreen} options={{ presentation: 'modal' }} />
            <Stack.Screen name="CloseShift" component={CloseShiftScreen} options={{ presentation: 'modal' }} />
            <Stack.Screen name="CashMovement" component={CashMovementScreen} options={{ presentation: 'modal' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

function LoadingShift() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <ActivityIndicator />
    </View>
  );
}
