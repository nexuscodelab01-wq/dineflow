import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StripeTerminalProvider } from '@stripe/stripe-terminal-react-native';
import RootNavigator from './src/navigation/RootNavigator';
import { fetchTerminalConnectionToken } from './src/api/pos';
import { usePosStore } from './src/state/store';

// Read via getState(), not a hook value — this function is created once at module load and must not
// close over a stale posSessionToken if staff switches PIN mid-session.
async function fetchTokenProvider() {
  const token = usePosStore.getState().posSessionToken;
  if (!token) throw new Error('Not logged in');
  const { secret } = await fetchTerminalConnectionToken(token);
  return secret;
}

export default function App() {
  return (
    <SafeAreaProvider>
      <StripeTerminalProvider logLevel="verbose" tokenProvider={fetchTokenProvider}>
        <RootNavigator />
      </StripeTerminalProvider>
      <StatusBar style="auto" />
    </SafeAreaProvider>
  );
}
