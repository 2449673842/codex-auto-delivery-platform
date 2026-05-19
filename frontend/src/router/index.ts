import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // MVP 页面路由（后续按需注册）
    // {
    //   path: '/',
    //   name: 'dashboard',
    //   component: () => import('../pages/DashboardPage.vue'),
    // },
  ],
})

export default router
