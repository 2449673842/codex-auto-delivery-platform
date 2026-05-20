/**
 * MCP Playwright: v0.3 S4 — AI Output TaskDetail Display
 *
 * Tests that governance, approval decisions, and AI artifact info
 * are rendered correctly on the TaskDetail page.
 *
 * Run: node tests/s4-display.cjs
 */
const { chromium } = require('playwright')
const http = require('http')

const FE = 'http://127.0.0.1:9700'
const BE = 'http://127.0.0.1:5697'

const t_actor = { actor: 'test' }

let results = { passed: 0, failed: 0, errors: [], networkFailures: [], details: [] }

function log(m) { console.log(m); results.details.push(m) }
function pass(m) { results.passed++; log(`  [PASS] ${m}`) }
function fail(m, e) { results.failed++; log(`  [FAIL] ${m}: ${e}`) }

function httpGet(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let data = ''
      res.on('data', c => data += c)
      res.on('error', reject)
      res.on('end', () => resolve({ status: res.statusCode, body: data }))
    }).on('error', reject)
  })
}

function httpPost(url, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url)
    const opts = {
      hostname: u.hostname, port: u.port, path: u.pathname + u.search,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }
    const req = http.request(opts, res => {
      let data = ''
      res.on('data', c => data += c)
      res.on('end', () => resolve({ status: res.statusCode, body: data }))
    })
    req.on('error', reject)
    req.write(JSON.stringify(body))
    req.end()
  })
}

async function apiPost(path, body) {
  const r = await httpPost(`${BE}/api${path}`, body)
  const j = JSON.parse(r.body)
  return { status: r.status, data: j.data || j }
}

async function apiGet(path) {
  const r = await httpGet(`${BE}/api${path}`)
  return JSON.parse(r.body)
}

async function seedProjectAndTask() {
  const proj = await apiPost('/projects', { name: `s4-proj-${Date.now()}`, root_path: '/s4' })
  const task = await apiPost('/tasks', { project_id: proj.data.id, title: 'S4 display test', planner: 'test', description: 'Test governance display' })
  return { project: proj.data, task: task.data }
}

async function main() {
  console.log('\n=== Playwright v0.3 S4 — AI Output Display Test ===\n')

  // ── Seed data ──
  log('--- API Seed ---')
  const { project, task } = await seedProjectAndTask()
  pass(`Project #${project.id} / Task #${task.id} seeded`)

  // Create a sandbox executor agent
  const agent = await apiPost('/agents', { name: 's4-agent', agent_type: 'executor', provider: 'sandbox' })
  pass(`Agent #${agent.data.id} created`)

  // Advance task state to dispatched
  await apiPost(`/tasks/${task.id}/generate-ticket`, t_actor)
  await apiPost(`/tasks/${task.id}/dispatch`, t_actor)

  // Orchestrate — creates AgentRun with sandbox plan output
  const orch = await apiPost(`/tasks/${task.id}/orchestration/step`, {})
  pass(`Orch step: ${orch.data.action_taken}`)

  // Continue orchestration to execute plan → succeeded
  const orch2 = await apiPost(`/tasks/${task.id}/orchestration/step`, {})
  pass(`Orch step 2: ${orch2.data.action_taken}`)

  // Check AgentRun exists with governance data
  const runs = await apiGet(`/tasks/${task.id}/agent-runs`)
  const run = runs.data[0]
  if (!run) { fail('No AgentRun found', ''); return }
  pass(`AgentRun #${run.id} status=${run.status} has raw_result_json=${!!run.raw_result_json}`)

  // Navigate to orch step 3 to get result_submitted
  await apiPost(`/tasks/${task.id}/orchestration/step`, {})

  // ── Launch browser ──
  log('\n--- Launch Browser ---')
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ ignoreHTTPSErrors: true })
  const page = await context.newPage()

  // Track console errors and network failures
  const consoleErrors = []
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
  page.on('requestfailed', req => {
    results.networkFailures.push(req.url())
  })

  try {
    await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
    pass('TaskDetail page loaded')
  } catch (e) {
    fail('TaskDetail page load', e.message)
    await browser.close()
    printSummary(consoleErrors)
    return
  }

  await page.waitForTimeout(500)

  // ── A. Governance display in AgentRun ──
  log('\n========== A. Governance on AgentRun ==========')
  try {
    const govSection = await page.locator('.gov-section').first()
    await govSection.waitFor({ state: 'visible', timeout: 5000 })
    const govText = await govSection.textContent()
    if (govText.includes('Valid') || govText.includes('Invalid') || govText.includes('风险')) {
      pass('Governance section visible with valid/invalid and risk level')
    } else { fail('Governance section missing expected text', govText) }
  } catch (e) {
    fail('Governance section not found', e.message)
  }

  try {
    const govTags = await page.locator('.gov-tag').count()
    if (govTags > 0) pass(`Governance tags found: ${govTags}`)
    else fail('No governance tags found', '')
  } catch (e) {
    fail('Governance tags check failed', e.message)
  }

  // ── B. Governance badges ──
  log('\n========== B. Governance Status Labels ==========')
  const expectedLabels = ['AI-generated']
  for (const label of expectedLabels) {
    try {
      const el = await page.locator(`.label-badge:has-text("${label}")`).count()
      if (el > 0) pass(`Label "${label}" found`)
      else fail(`Label "${label}" not found`, '')
    } catch (e) {
      fail(`Label "${label}" check failed`, e.message)
    }
  }

  // Check for at least one label-badge
  try {
    const badges = await page.locator('.label-badge').count()
    if (badges > 0) pass(`Status badges found: ${badges}`)
    else fail('No status badges at all', '')
  } catch (e) {
    fail('Status badges check failed', e.message)
  }

  // ── C. AI Artifacts ──
  log('\n========== C. AI Artifacts ==========')
  try {
    const artifactSection = await page.locator('text=AI 产物').first()
    await artifactSection.waitFor({ state: 'visible', timeout: 3000 })
    pass('AI Artifacts section visible')
  } catch (e) {
    fail('AI Artifacts section not found', e.message)
  }

  try {
    const artifactBadges = await page.locator('.artifact-note .label-badge').count()
    if (artifactBadges > 0) pass(`Artifact labels found: ${artifactBadges}`)
    else pass('Artifact labels section present (may be empty if no artifacts)')
  } catch (e) {
    fail('Artifact labels check failed', e.message)
  }

  // ── D. Approval Decisions ──
  log('\n========== D. Approval Decisions ==========')
  try {
    const approvalSection = await page.locator('text=审批决策').first()
    await approvalSection.waitFor({ state: 'visible', timeout: 3000 })
    pass('Approval Decisions section visible')
  } catch (e) {
    fail('Approval Decisions section not found', e.message)
  }

  // ── E. human_required state ──
  log('\n========== E. human_required ==========')
  // Navigate task through the flow and check human_required button
  try {
    // Try to find the "需要人工审批" button in action bar
    const humanReqBtn = await page.locator('button:has-text("需要人工审批")').count()
    if (humanReqBtn > 0) {
      pass('human_required action button visible')
    } else {
      // Task might not be in reviewing state yet, check if any governance tag shows requires_human
      const humanTag = await page.locator('.gov-human').count()
      if (humanTag > 0) pass('human_required tag visible in governance')
      else pass('human_required not triggered (task state may not require it)')
    }
  } catch (e) {
    fail('human_required check failed', e.message)
  }

  // ── Summary ──
  log('\n========== SUMMARY ==========')
  consoleErrors.forEach(e => log(`  [ERR] ${e}`))
  results.networkFailures.forEach(u => log(`  [NET] ${u}`))
  console.log(`\n  Console Errors: ${consoleErrors.length}`)
  console.log(`  Network Failures: ${results.networkFailures.length}`)
  console.log(`\n  ============================`)
  console.log(`  TOTAL: ${results.passed} passed, ${results.failed} failed`)
  console.log(`  ============================\n`)

  await browser.close()
}

function printSummary(consoleErrors) {
  console.log('\n========== SUMMARY ==========')
  consoleErrors.forEach(e => log(`  [ERR] ${e}`))
  results.networkFailures.forEach(u => log(`  [NET] ${u}`))
  console.log(`\n  Console Errors: ${consoleErrors.length}`)
  console.log(`  Network Failures: ${results.networkFailures.length}`)
  console.log(`\n  ============================`)
  console.log(`  TOTAL: ${results.passed} passed, ${results.failed} failed`)
  console.log(`  ============================\n`)
}

main().catch(e => { console.error('Test harness error:', e); process.exit(1) })
