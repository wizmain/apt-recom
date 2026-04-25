import path from 'node:path';
import { router } from '@granite-js/plugin-router';
import { hermes } from '@granite-js/plugin-hermes';
import { defineConfig } from '@granite-js/react-native/config';
import { appsInToss } from '@apps-in-toss/framework/plugins';

// Toss 콘솔 등록명: jiptori (Phase 0 에서 확정)
// scheme: intoss://jiptori/<page>
// icon: '' 은 개발 단계 임시값 — 출시 전 업로드 후 URL 로 교체
//
// monorepo: packages/shared 가 node_modules 에 symlink 되어 있어 watchman 이
// 추적하지 못하므로 metro.watchFolders 에 명시적으로 추가한다.
const sharedPkgRoot = path.resolve(__dirname, '../../packages/shared');

export default defineConfig({
  appName: 'jiptori',
  scheme: 'jiptori',
  metro: {
    watchFolders: [sharedPkgRoot],
    resolver: {
      // symlink 된 packages/shared 가 자체 node_modules 를 참조하지 않도록
      // miniapp 의 node_modules 만 사용하도록 강제.
      nodeModulesPaths: [path.resolve(__dirname, 'node_modules')],
    },
  },
  plugins: [
    router(),
    hermes(),
    ...appsInToss({
      target: '0.84.0',
      brand: {
        displayName: '집토리',
        primaryColor: '#3182F6',
        icon: '',
      },
      permissions: [],
    }),
  ],
});
