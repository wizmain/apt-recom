import pluginJs from '@eslint/js';
import tseslint from 'typescript-eslint';
import pluginReact from 'eslint-plugin-react';

/** @type {import('eslint').Linter.Config[]} */
export default [
  { ignores: ['**/node_modules/**', '**/dist/**', '*.{cjs,js}'] },
  { files: ['pages/**/*.{ts,jsx,tsx}', 'src/**/*.{ts,jsx,tsx}'] },
  pluginJs.configs.recommended,
  ...tseslint.configs.recommended,
  {
    settings: {
      react: {
        version: 'detect',
      },
    },
  },
  pluginReact.configs.flat.recommended,
  {
    rules: {
      // _ prefix 인자/변수는 의도된 미사용으로 간주.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // 새로운 RN 19 / TS 환경에서 React 임포트가 필요 없는 경우 다수.
      'react/react-in-jsx-scope': 'off',
    },
  },
];
