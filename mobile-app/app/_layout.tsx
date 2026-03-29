import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="detail/[pnu]" options={{ presentation: 'card', animation: 'slide_from_right' }} />
        <Stack.Screen name="compare" options={{ presentation: 'card', animation: 'slide_from_right' }} />
      </Stack>
    </SafeAreaProvider>
  );
}
