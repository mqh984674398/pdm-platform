import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'
import './theme/base.css'

document.documentElement.lang = i18n.global.locale.value
createApp(App).use(createPinia()).use(i18n).use(router).mount('#app')
