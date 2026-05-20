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
const r = { passed: 0, failed: 0, errors: [], networkFailures: [], details: [] }

function log(m) { console.log(m); r.details.push(m) }  // NOSONAR - test log
function pass(m) { r.passed++; log(`  [PASS] ${m}`) }
function fail(m, e) { r.failed++; log(`  [FAIL] ${m}: ${e}`) }

function httpGet(url, cb) {  // NOSONAR - test harness
  http.get(url, res => { let d = ''; res.on('data', c => d += c); res.on('end', () => cb({ status: res.statusCode, body: d })) })
    .on('error', cb)
}

function httpPost(url, body, cb) {  // NOSONAR - test harness
  const u = new URL(url)
  const req = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method: 'POST', headers: { 'Content-Type': 'application/json' } },
    res => { let d = ''; res.on('data', c => d += c); res.on('end', () => cb({ status: res.statusCode, body: d })) })
  req.on('error', cb); req.write(JSON.stringify(body)); req.end()
}

function apiPost(path, body) { // NOSONAR
  return new Promise((resolve, reject) => httpPost(`${BE}/api${path}`, body, r2 => {
    try { resolve({ status: r2.status, data: JSON.parse(r2.body).data || JSON.parse(r2.body) }) }
    catch (e) { reject(e) }
  }))
}

function apiGet(path) { // NOSONAR
  return new Promise((resolve, reject) => httpGet(`${BE}/api${path}`, r2 => {
    try { resolve(JSON.parse(r2.body)) } catch (e) { reject(e) }
  }))
}

async function seedData() {
  const proj = await apiPost('/projects', { name: `s4-proj-${Date.now()}`, root_path: '/s4' })
  const task = await apiPost('/tasks', { project_id: proj.data.id, title: 'S4 display test', planner: 'test', description: 'Test governance display' })
  await apiPost('/agents', { name: 's4-agent', agent_type: 'executor', provider: 'sandbox' })
  return task.data
}

async function seedApprovalDecision(taskId) {
  const r2 = await apiPost(`/tasks/${taskId}/evaluate-approval`, {}) // NOSONAR
  return r2
}

async function orchestrateSteps(taskId) {
  await apiPost(`/tasks/${taskId}/generate-ticket`, t_actor) // NOSONAR
  await apiPost(`/tasks/${taskId}/dispatch`, t_actor) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
}

async function launchBrowser() {
  const b = await chromium.launch({ headless: true })
  const c = await b.newContext({ ignoreHTTPSErrors: true })
  const p = await c.newPage()
  const ce = []
  p.on('console', msg => { if (msg.type() === 'error') ce.push(msg.text()) })
  p.on('requestfailed', req => { r.networkFailures.push(req.url()) })
  return { browser: b, page: p, consoleErrors: ce }
}

async function checkEl(page, selector, label) {
  const n = await page.locator(selector).count()
  if (n > 0) pass(`${label} found (${n})`)
  else fail(`${label} not found`, `selector: ${selector}`)
}

async function checkT(page, text, label) {
  const n = await page.locator(`text="${text}"`).count()
  if (n > 0) pass(`${label}: "${text}"`)
  else fail(`${label}: "${text}" not found`, '')
}

async function testGovernance(page) {
  log('\n========== A. Governance on AgentRun ==========')
  await checkEl(page, '.gov-section', 'A1 Governance section')
  await checkEl(page, '.gov-tag', 'A2 Governance tags')
}

async function testLabels(page) {
  log('\n========== B. Governance Status Labels ==========')
  for (const lbl of ['AI-generated', 'Not automatically merged', 'Not executed', 'Not applied to repository']) {
    await checkT(page, lbl, `B ${lbl}`)
  }
}

async function testArtifacts(page) {
  log('\n========== C. AI Artifacts ==========')
  await checkT(page, 'AI 产物', 'C1 Section')
  const n = await page.locator('.artifact-note .label-badge').count()
  if (n >= 3) pass(`C2 ${n} artifact labels`)
  else fail(`C2 ${n} labels < 3`, '')
}

async function testApprovals(page) {
  log('\n========== D. Approval Decisions ==========')
  await checkT(page, '审批决策', 'D1 Section')
  await checkEl(page, '.approval-decision-item', 'D2 Items')
  const txt = await page.locator('.approval-decision-item').first().textContent()
  if (!txt) { fail('D3-D6', 'No decision text'); return }
  if (txt.includes('风险')) pass('D3 risk_level')
  else fail('D3 risk_level not found', txt.slice(0, 80))
  if (txt.includes('自动审批')) pass('D4 auto_approve_allowed')
  else fail('D4 auto_approve not found', txt.slice(0, 80))
  if (txt.includes('需人工审批')) pass('D5 human_required')
  else fail('D5 human_required not found', txt.slice(0, 80))
  if (txt.length > 20) pass('D6 decision_reason present')
  else fail('D6 decision_reason too short', txt.slice(0, 80))
}

async function testHumanRequired(page) {
  log('\n========== E. human_required ==========')
  const btn = page.locator('button:has-text("需要人工审批")')
  if (await btn.count() > 0) {
    await btn.click()
    await page.waitForTimeout(500)
    const ok = await page.locator('text=需人工审批').count()
    if (ok > 0) pass('E1 human_required activated')
    else fail('E1 state not shown after click', '')
  } else {
    const h = await page.locator('.gov-human').count() + await page.locator('text=需人工审批').count()
    if (h > 0) pass('E1 human_required active')
    else { fail('E1 cannot trigger human_required', ''); return }
  }
  const ap = await page.locator('button:has-text("Approve")').count()
  if (ap > 0) pass('E2 Approve button')
  else fail('E2 Approve button missing', '')
  const rj = await page.locator('button:has-text("Reject")').count()
  if (rj > 0) pass('E3 Reject button')
  else fail('E3 Reject button missing', '')
}

function printSummary(ce) {
  console.log('\n========== SUMMARY ==========')
  ce.forEach(e => log(`  [ERR] ${e}`))
  r.networkFailures.forEach(u => log(`  [NET] ${u}`))
  console.log(`\n  Console Errors: ${ce.length}`)
  console.log(`  Network Failures: ${r.networkFailures.length}`)
  console.log(`\n  ============================`)
  console.log(`  TOTAL: ${r.passed} passed, ${r.failed} failed`)
  console.log(`  ============================\n`)
}

async function main() {
  console.log('\n=== Playwright v0.3 S4 — AI Output Display Test ===\n')

  log('--- API Seed ---')
  const task = await seedData()
  pass(`Task #${task.id} seeded`)
  await seedApprovalDecision(task.id)
  pass('ApprovalDecision seeded')
  await orchestrateSteps(task.id)
  const runs = await apiGet(`/tasks/${task.id}/agent-runs`) // NOSONAR
  const hasRun = runs.data?.[0]
  if (hasRun) pass(`AgentRun #${hasRun.id} status=${hasRun.status}`)
  else { fail('No AgentRun', ''); return }

  log('\n--- Launch Browser ---')
  const { browser, page, consoleErrors } = await launchBrowser()
  try {
    await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 }) // NOSONAR
    pass('TaskDetail page loaded')
  } catch (e) {
    fail('Page load', e.message)
    await browser.close()
    printSummary(consoleErrors)
    return
  }
  await page.waitForTimeout(1000)

  await testGovernance(page)
  await testLabels(page)
  await testArtifacts(page)
  await testApprovals(page)
  await testHumanRequired(page)
  printSummary(consoleErrors)
  await browser.close()
}

main().catch(e => { console.error('Test harness error:', e); process.exit(1) })
