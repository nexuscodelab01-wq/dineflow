import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import PairingScreen from '../screens/PairingScreen';
import PinEntryScreen from '../screens/PinEntryScreen';
import OrderScreen from '../screens/OrderScreen';
import CashTenderScreen from '../screens/CashTenderScreen';
import { usePosStore } from '../state/store';

export type RootStackParamList = {
  Pairing: undefined;
  PinEntry: undefined;
  Order: undefined;
  CashTender: { orderId: number; orderNumber: string; total: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const deviceReady = usePosStore((s) => s.deviceReady);
  const deviceToken = usePosStore((s) => s.deviceToken);
  const posSessionToken = usePosStore((s) => s.posSessionToken);
  const loadDevice = usePosStore((s) => s.loadDevice);

  useEffect(() => {
    loadDevice();
  }, [loadDevice]);

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
        ) : (
          <>
            <Stack.Screen name="Order" component={OrderScreen} />
            <Stack.Screen name="CashTender" component={CashTenderScreen} options={{ presentation: 'modal' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
