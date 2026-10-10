import pluginVue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

export default defineConfigWithVueTs(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'test-results/**',
      'playwright-report/**',
      'src/api/generated.ts',
    ],
  },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  // Formatting is owned by Prettier.
  skipFormatting,
)
