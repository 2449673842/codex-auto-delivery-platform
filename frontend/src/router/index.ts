import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../pages/DashboardPage.vue'),
    },
    {
      path: '/projects',
      name: 'project-list',
      component: () => import('../pages/ProjectListPage.vue'),
    },
    {
      path: '/projects/:id',
      name: 'project-config',
      component: () => import('../pages/ProjectConfigPage.vue'),
    },
    {
      path: '/tasks',
      name: 'task-list',
      component: () => import('../pages/TaskListPage.vue'),
    },
    {
      path: '/tasks/new',
      name: 'task-create',
      component: () => import('../pages/TaskCreatePage.vue'),
    },
    {
      path: '/tasks/:id',
      name: 'task-detail',
      component: () => import('../pages/TaskDetailPage.vue'),
    },
  ],
})

export default router
