import pluginVue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'

export default defineConfigWithVueTs(
  { ignores: ['dist/**', 'node_modules/**', 'test-results/**', 'playwright-report/**'] },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  // Formatting is owned by Prettier.
  {
    rules: {
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/max-attributes-per-line': 'off',
    },
  },
)
