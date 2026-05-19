<template>
  <div class="app-layout">
    <nav class="top-nav">
      <div class="nav-inner">
        <router-link to="/" class="nav-brand">Codex</router-link>
        <div class="nav-links">
          <router-link to="/" class="nav-link" :class="{ active: $route.path === '/' }">仪表盘</router-link>
          <router-link to="/projects" class="nav-link" :class="{ active: $route.path.startsWith('/projects') }">项目</router-link>
          <router-link to="/tasks" class="nav-link" :class="{ active: $route.path.startsWith('/tasks') }">任务</router-link>
          <router-link to="/agents" class="nav-link" :class="{ active: $route.path === '/agents' }">Agent</router-link>
          <router-link to="/approval-policies" class="nav-link" :class="{ active: $route.path === '/approval-policies' }">审批策略</router-link>
        </div>
      </div>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
.app-layout { min-height: 100vh; display: flex; flex-direction: column; }
.top-nav { background: var(--color-surface); border-bottom: 1px solid var(--color-border); position: sticky; top: 0; z-index: 50; }
.nav-inner { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; gap: 24px; padding: 0 24px; height: 48px; }
.nav-brand { font-weight: 700; font-size: 16px; color: var(--color-primary); text-decoration: none; }
.nav-links { display: flex; gap: 4px; }
.nav-link { padding: 6px 12px; border-radius: var(--radius); font-size: 14px; color: var(--color-text-secondary); text-decoration: none; transition: all 0.15s; }
.nav-link:hover { background: var(--color-bg); color: var(--color-text); }
.nav-link.active { background: var(--color-primary-light); color: var(--color-primary); font-weight: 500; }
.main-content { flex: 1; }
</style>
