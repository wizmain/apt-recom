import React, { type PropsWithChildren } from 'react';
import { Granite, type InitialProps } from '@granite-js/react-native';
import { TDSProvider } from '@toss/tds-react-native';
import { context } from '../require.context';
import { useTossAuth } from './hooks/useTossAuth';

function AppContainer({ children }: PropsWithChildren<InitialProps>) {
  // 백그라운드로 anon-key 초기화. 페이지 렌더링은 즉시 시작 (블로킹 없음).
  useTossAuth();
  return <TDSProvider>{children}</TDSProvider>;
}

export default Granite.registerApp(AppContainer, {
  appName: 'jiptori',
  context,
});
