<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>审批策略管理</h1>
        <router-link to="/" class="back-link">← 返回仪表盘</router-link>
      </div>
      <button class="btn btn-primary" @click="showForm = true">+ 新建策略</button>
    </header>

    <div v-if="showForm" class="form-overlay" @click.self="showForm = false">
      <div class="form-panel card">
        <h2>{{ editingId ? '编辑策略' : '新建策略' }}</h2>
        <form @submit.prevent="handleSubmit">
          <label>策略名称 *<input v-model="form.name" required /></label>
          <label>项目 ID（可选）<input v-model.number="form.project_id" type="number" placeholder="为空则全局策略" /></label>
          <label class="checkbox-label"><input type="checkbox" v-model="form.enabled" /> 启用</label>

          <h3 class="form-section">自动审批条件</h3>
          <label>
            最大自动审批风险等级
            <select v-model="form.max_risk_level_for_auto_approve">
              <option value="low">低 (Low)</option>
              <option value="medium">中 (Medium)</option>
              <option value="high">高 (High)</option>
              <option value="critical">严重 (Critical)</option>
            </select>
          </label>
          <label class="checkbox-label"><input type="checkbox" v-model="form.require_tests_passed" /> 要求测试通过</label>
          <label class="checkbox-label"><input type="checkbox" v-model="form.require_sonar_passed" /> 要求 Sonar 通过</label>
          <label class="checkbox-label"><input type="checkbox" v-model="form.require_no_security_issues" /> 要求无安全漏洞</label>

          <h3 class="form-section">自动审批豁免</h3>
          <label class="checkbox-label"><input type="checkbox" v-model="form.allow_auto_approve_docs_only" /> 纯文档变更可自动审批</label>
          <label class="checkbox-label"><input type="checkbox" v-model="form.allow_auto_approve_frontend_style_only" /> 纯前端样式变更可自动审批</label>

          <h3 class="form-section">安全限制</h3>
          <label class="checkbox-label"><input type="checkbox" v-model="form.forbid_auto_merge_main" /> 禁止自动合并到 main</label>
          <label class="checkbox-label"><input type="checkbox" v-model="form.forbid_auto_deploy_prod" /> 禁止自动部署到生产</label>

          <div class="form-actions">
            <button type="submit" class="btn btn-primary">{{ editingId ? '保存' : '创建' }}</button>
            <button type="button" class="btn" @click="showForm = false">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div class="policy-list" v-if="policies.length > 0">
      <div v-for="p in policies" :key="p.id" class="policy-card card">
        <div class="policy-header">
          <h3>{{ p.name }}</h3>
          <span class="risk-badge" :class="p.max_risk_level_for_auto_approve">风险≤{{ p.max_risk_level_for_auto_approve }}</span>
          <span v-if="p.project_id" class="scope-badge">项目 #{{ p.project_id }}</span>
          <span v-else class="scope-badge global">全局</span>
          <span class="status-dot" :class="{ active: p.enabled }" :title="p.enabled ? '已启用' : '已禁用'"></span>
        </div>
        <div class="policy-rules">
          <span class="rule" :class="{ pass: p.require_tests_passed }">测试{{ p.require_tests_passed ? '✅' : '❌' }}</span>
          <span class="rule" :class="{ pass: p.require_sonar_passed }">Sonar{{ p.require_sonar_passed ? '✅' : '❌' }}</span>
          <span class="rule" :class="{ pass: p.require_no_security_issues }">安全{{ p.require_no_security_issues ? '✅' : '❌' }}</span>
          <span class="rule-label" v-if="p.allow_auto_approve_docs_only">📄 文档豁免</span>
          <span class="rule-label" v-if="p.allow_auto_approve_frontend_style_only">🎨 样式豁免</span>
          <span class="rule-label restrict" v-if="p.forbid_auto_merge_main">🚫 禁合 main</span>
          <span class="rule-label restrict" v-if="p.forbid_auto_deploy_prod">🚫 禁部署生产</span>
        </div>
        <div class="card-actions">
          <button class="btn btn-sm" @click="editPolicy(p)">编辑</button>
          <button class="btn btn-sm btn-danger" @click="handleDelete(p.id)">删除</button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>暂无审批策略</p>
      <button class="btn btn-primary btn-sm" style="margin-top: 12px;" @click="showForm = true">创建第一个策略</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchApprovalPolicies, createApprovalPolicy, updateApprovalPolicy, deleteApprovalPolicy } from '../services/agentService'
import type { ApprovalPolicy, ApprovalPolicyCreate, ApprovalPolicyUpdate } from '../types/agent'

const policies = ref<ApprovalPolicy[]>([])
const showForm = ref(false)
const editingId = ref<number | null>(null)
const form = ref<ApprovalPolicyCreate>({
  name: '',
  project_id: null,
  enabled: true,
  max_risk_level_for_auto_approve: 'low',
  require_tests_passed: true,
  require_sonar_passed: false,
  require_no_security_issues: true,
  allow_auto_approve_docs_only: true,
  allow_auto_approve_frontend_style_only: true,
  forbid_auto_merge_main: true,
  forbid_auto_deploy_prod: true,
})

onMounted(load)

async function load() {
  policies.value = await fetchApprovalPolicies()
}

function resetForm() {
  form.value = {
    name: '',
    project_id: null,
    enabled: true,
    max_risk_level_for_auto_approve: 'low',
    require_tests_passed: true,
    require_sonar_passed: false,
    require_no_security_issues: true,
    allow_auto_approve_docs_only: true,
    allow_auto_approve_frontend_style_only: true,
    forbid_auto_merge_main: true,
    forbid_auto_deploy_prod: true,
  }
  editingId.value = null
}

function editPolicy(p: ApprovalPolicy) {
  editingId.value = p.id
  form.value = {
    name: p.name,
    project_id: p.project_id,
    enabled: p.enabled,
    max_risk_level_for_auto_approve: p.max_risk_level_for_auto_approve,
    require_tests_passed: p.require_tests_passed,
    require_sonar_passed: p.require_sonar_passed,
    require_no_security_issues: p.require_no_security_issues,
    allow_auto_approve_docs_only: p.allow_auto_approve_docs_only,
    allow_auto_approve_frontend_style_only: p.allow_auto_approve_frontend_style_only,
    forbid_auto_merge_main: p.forbid_auto_merge_main,
    forbid_auto_deploy_prod: p.forbid_auto_deploy_prod,
  }
  showForm.value = true
}

async function handleSubmit() {
  try {
    if (editingId.value) {
      const body: ApprovalPolicyUpdate = { ...form.value }
      await updateApprovalPolicy(editingId.value, body)
    } else {
      await createApprovalPolicy(form.value)
    }
    showForm.value = false
    resetForm()
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}

async function handleDelete(id: number) {
  if (!confirm('确定删除此策略？')) return
  try {
    await deleteApprovalPolicy(id)
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.form-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.form-panel { padding: 32px; width: 560px; max-width: 90vw; max-height: 90vh; overflow-y: auto; }
.form-panel h2 { font-size: 18px; margin-bottom: 16px; }
.form-section { font-size: 14px; font-weight: 600; margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--color-border); color: var(--color-text); }
.form-panel form { display: flex; flex-direction: column; gap: 10px; }
.form-actions { display: flex; gap: 8px; margin-top: 12px; }
.checkbox-label { display: flex; flex-direction: row; align-items: center; gap: 8px; font-size: 14px; }
.policy-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; }
.policy-card { display: flex; flex-direction: column; gap: 8px; }
.policy-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.policy-header h3 { font-size: 16px; font-weight: 600; }
.risk-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.risk-badge.low { background: #e8f5e9; color: #2e7d32; }
.risk-badge.medium { background: #fff3e0; color: #e65100; }
.risk-badge.high { background: #ffebee; color: #c62828; }
.risk-badge.critical { background: #fce4ec; color: #b71c1c; }
.scope-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; background: #e3f2fd; color: #1565c0; }
.scope-badge.global { background: #f3e5f5; color: #7b1fa2; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: #e0e0e0; margin-left: auto; }
.status-dot.active { background: #4caf50; }
.policy-rules { display: flex; gap: 6px; flex-wrap: wrap; }
.rule { padding: 2px 8px; border-radius: 8px; font-size: 12px; background: #f5f5f5; color: #9e9e9e; }
.rule.pass { background: #e8f5e9; color: #2e7d32; }
.rule-label { padding: 2px 8px; border-radius: 8px; font-size: 12px; background: #fff8e1; color: #f57f17; }
.rule-label.restrict { background: #ffebee; color: #c62828; }
.card-actions { display: flex; gap: 8px; margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--color-border); }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-danger { color: var(--color-danger); border-color: var(--color-danger); }
.btn-sm { padding: 4px 12px; font-size: 13px; }
</style>
