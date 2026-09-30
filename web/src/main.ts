import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/main.css'

const app = createApp(App)

app.use(createPinia()) // client state: the conversation on screen
app.use(VueQueryPlugin) // server state: cached GET requests, like the schema list

app.mount('#app')
