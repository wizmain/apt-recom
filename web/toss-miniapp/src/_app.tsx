import React, { type PropsWithChildren } from 'react';
import { Granite, type InitialProps } from '@granite-js/react-native';
import { TDSProvider } from '@toss/tds-react-native';
import { context } from '../require.context';

function AppContainer({ children }: PropsWithChildren<InitialProps>) {
  return <TDSProvider>{children}</TDSProvider>;
}

export default Granite.registerApp(AppContainer, {
  appName: 'jiptori',
  context,
});
