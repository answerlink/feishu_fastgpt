import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import axios from 'axios'

const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 配置axios - 不设置baseURL，让各个组件自己控制完整路径
// axios.defaults.baseURL = '/api'
app.config.globalProperties.$http = axios

app.use(ElementPlus)
app.use(router)
app.mount('#app') 