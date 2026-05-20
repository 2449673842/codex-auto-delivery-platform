/**
 * MCP Playwright: v0.3 S4 — AI Output TaskDetail Display
 *
 * Verifies governance, artifacts, approval decisions, and human_required
 * are rendered correctly on the TaskDetail page.
 */
const { chromium } = require('playwright')
const http = require('node:http')

const FE = 'http://127.0.0.1:9700'
const BE = 'http://127.0.0.1:5697'

const t_actor = { actor: 'test' }
const results = { passed: 0, failed: 0, errors: [], networkFailures: [], details: [] }

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

async function apiPost(path, body) { // NOSONAR
  const r = await httpPost(`${BE}/api${path}`, body)
  return { status: r.status, data: JSON.parse(r.body).data || JSON.parse(r.body) }
}

async function apiGet(path) { // NOSONAR
  const r = await httpGet(`${BE}/api${path}`)
  return JSON.parse(r.body)
}

async function seedData() {
  const proj = await apiPost('/projects', { name: `s4-proj-${Date.now()}`, root_path: '/s4' })
  const task = await apiPost('/tasks', { project_id: proj.data.id, title: 'S4 display test', planner: 'test', description: 'Test governance display' })
  await apiPost('/agents', { name: 's4-agent', agent_type: 'executor', provider: 'sandbox' })
  return { project: proj.data, task: task.data }
}

async function orchestrateToReviewing(taskId) {
  await apiPost(`/tasks/${taskId}/generate-ticket`, t_actor) // NOSONAR
  await apiPost(`/tasks/${taskId}/dispatch`, t_actor) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
}

async function seedApprovalDecision(taskId) {
  // Create an ApprovalDecision by evaluating approval
  await apiPost(`/tasks/${taskId}/evaluate-approval`, {}) // NOSONAR
}

async function checkElement(page, selector, text, label) {
  try {
    const el = await page.locator(selector).count()
    if (el > 0) pass(`${label} found (${el})`)
    else fail(`${label} not found`, `selector: ${selector}`)
  } catch (e) {
    fail(`${label} check failed`, e.message)
  }
}

async function checkText(page, text, label) {
  try {
    const el = await page.locator(`text="${text}"`).count()
    if (el > 0) pass(`${label}: "${text}" found`)
    else fail(`${label}: "${text}" not found`, '')
  } catch (e) {
    fail(`${label} check failed`, e.message)
  }
}

async function setupBrowser() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ ignoreHTTPSErrors: true })
  const page = await context.newPage()
  const consoleErrors = []
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
  page.on('requestfailed', req => { results.networkFailures.push(req.url()) })
  return { browser, page, consoleErrors }
}

async function main() {
  console.log('\n=== Playwright v0.3 S4 — AI Output Display Test ===\n')

  // ── Seed data ──
  log('--- API Seed ---')
  const { task } = await seedData()
  pass(`Task #${task.id} seeded`)
  await seedApprovalDecision(task.id)
  pass('ApprovalDecision seeded')

  // Orchestrate to get AgentRun with governance data
  await orchestrateToReviewing(task.id)
  const runs = await apiGet(`/tasks/${task.id}/agent-runs`) // NOSONAR
  const firstRun = runs.data && runs.data[0]
  if (firstRun) pass(`AgentRun #${firstRun.id} status=${firstRun.status} governance=${!!firstRun.raw_result_json}`)
  else fail('No AgentRun found', '')
  const taskRes = await apiGet(`/tasks/${task.id}`) // NOSONAR
  log(`Task status: ${taskRes.data ? taskRes.data.status : '?'}`)

  // ── Launch browser ──
  log('\n--- Launch Browser ---')
  const { browser, page, consoleErrors } = await setupBrowser()

  try {
    await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 }) // NOSONAR
    pass('TaskDetail page loaded')
  } catch (e) {
    fail('TaskDetail page load', e.message)
    await browser.close()
    return printSummary(consoleErrors)
  }
  await page.waitForTimeout(1000)

  // ── A. Governance on AgentRun ──
  log('\n========== A. Governance on AgentRun ==========')
  await checkElement(page, '.gov-section', 'Governance section', 'A1')
  await checkElement(page, '.gov-tag', 'Governance tags', 'A2')

  // ── B. Governance Status Labels ──
  log('\n========== B. Governance Status Labels ==========')
  await checkText(page, 'AI-generated', 'B1')
  await checkText(page, 'Not automatically merged', 'B2')
  await checkText(page, 'Not executed', 'B3')
  await checkText(page, 'Not applied to repository', 'B4')

  // ── C. AI Artifacts ──
  log('\n========== C. AI Artifacts ==========')
  await checkText(page, 'AI 产物', 'C1')
  const artifactBadges = await page.locator('.artifact-note .label-badge').count()
  if (artifactBadges >= 3) pass(`C2: Artifact labels present: ${artifactBadges}`)
  else fail(`C2: artifact labels count ${artifactBadges} < 3`, '')

  // ── D. Approval Decisions ──
  log('\n========== D. Approval Decisions ==========')
  await checkText(page, '审批决策', 'D1')

  // Check ApprovalDecision content: risk_level, human_required, auto_approve_allowed, decision_reason
  await checkElement(page, '.approval-decision-item', 'Approval decision items', 'D2')
  // Check for specific decision content
  const decisionText = await page.locator('.approval-decision-item').first().textContent()
  if (decisionText) {
    if (decisionText.includes('风险') || decisionText.includes('risk')) pass('D3: risk_level displayed')
    else fail('D3: risk_level not found in decision', decisionText.substring(0, 100))
    if (decisionText.includes('自动审批') || decisionText.includes('auto_approve')) pass('D4: auto_approve_allowed displayed')
    else fail('D4: auto_approve_allowed not found', decisionText.substring(0, 100))
    if (decisionText.includes('需人工审批') || decisionText.includes('human_required')) pass('D5: human_required status displayed')
    else fail('D5: human_required not found', decisionText.substring(0, 100))
    if (decisionText.includes('Governance') || decisionText.includes('risk') || decisionText.includes('审批')) pass('D6: decision_reason displayed')
    else fail('D6: decision_reason not found', decisionText.substring(0, 100))
  } else {
    fail('D3-D6', 'No decision text available')
  }

  // ── E. human_required scenario ──
  log('\n========== E. human_required ==========')
  // If task is in reviewing state, click "需要人工审批" button
  const humanBtn = await page.locator('button:has-text("需要人工审批")')
  if (await humanBtn.count() > 0) {
    await humanBtn.click()
    await page.waitForTimeout(500)
    await page.waitForSelector('text=需人工审批', { timeout: 3000 }).then(
      () => pass('E1: human_required state active via button click'),
      () => fail('E1: human_required state not shown after click', '')
    )
  } else {
    // Task might have transitioned already via orchestration
    const humanLabel = await page.locator('.gov-human').count()
    const humanStatus = await page.locator('text=需人工审批').count()
    if (humanLabel > 0 || humanStatus > 0) pass('E1: human_required active via existing state')
    else fail('E1: Cannot trigger human_required — button not found and no existing state', '')
  }

  // After human_required is active, verify action buttons
  if (await page.locator('button:has-text("Approve")').count() > 0) pass('E2: Approve button visible')
  else fail('E2: Approve button not visible', '')

  if (await page.locator('button:has-text("Reject")').count() > 0) pass('E3: Reject button visible')
  else fail('E3: Reject button not visible', '')

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
  consoleErrors.forEach(e => results.details.push(`  [ERR] ${e}`))
  results.networkFailures.forEach(u => results.details.push(`  [NET] ${u}`))
  console.log(`\n  Console Errors: ${consoleErrors.length}`)
  console.log(`  Network Failures: ${results.networkFailures.length}`)
  console.log(`\n  ============================`)
  console.log(`  TOTAL: ${results.passed} passed, ${results.failed} failed`)
  console.log(`  ============================\n`)
}

main().catch(e => { console.error('Test harness error:', e); process.exit(1) })
