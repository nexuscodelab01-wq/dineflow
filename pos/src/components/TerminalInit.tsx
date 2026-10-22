import { useEffect } from 'react';
import { useStripeTerminal } from '@stripe/stripe-terminal-react-native';
import { usePosStore } from '../state/store';

/**
 * Starts the Stripe Terminal SDK. Rendering <StripeTerminalProvider> is not enough: every Terminal call fails with
 * "First initialize the Stripe Terminal SDK" until initialize() has run. It waits for a PIN login because the SDK
 * asks our server for a connection token, and that request needs the signed-in staff session.
 */
export default function TerminalInit() {
  const loggedIn = usePosStore((s) => s.posSessionToken !== null);
  const { initialize, isInitialized } = useStripeTerminal();

  useEffect(() => {
    if (!loggedIn || isInitialized) return;
    initialize().then(({ error }) => {
      if (error) console.warn('Stripe Terminal could not start:', error.message);
    });
  }, [loggedIn, isInitialized, initialize]);

  return null;
}
