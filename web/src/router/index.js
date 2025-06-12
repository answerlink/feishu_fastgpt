import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import WikiSpaces from '../views/WikiSpaces.vue'
import DocumentSubscribe from '../views/DocumentSubscribe.vue'
import Apps from '../views/Apps.vue'
import LogViewer from '../views/LogViewer.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home
    },
    {
      path: '/home',
      name: 'home-alt',
      component: Home
    },
    {
      path: '/app-status',
      name: 'app-status',
      component: Apps
    },
    {
      path: '/apps',
      name: 'apps',
      component: Apps
    },
    {
      path: '/wiki-spaces',
      name: 'wiki-spaces',
      component: WikiSpaces
    },
    {
      path: '/document-subscribe',
      name: 'document-subscribe',
      component: DocumentSubscribe
    },
    {
      path: '/log-viewer',
      name: 'log-viewer',
      component: LogViewer
    },
    {
      path: '/logs',
      name: 'logs',
      component: LogViewer
    }
  ]
})

export default router 