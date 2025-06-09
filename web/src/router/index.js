import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/Home.vue'
import WikiSpaces from '../views/WikiSpaces.vue'
import DocumentSubscribe from '../views/DocumentSubscribe.vue'
import Callbacks from '../views/Callbacks.vue'
import Apps from '../views/Apps.vue'
import LogViewer from '../views/LogViewer.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
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
      path: '/callbacks',
      name: 'callbacks',
      component: Callbacks
    },
    {
      path: '/apps',
      name: 'apps',
      component: Apps
    },
    {
      path: '/logs',
      name: 'logs',
      component: LogViewer
    }
  ]
})

export default router 