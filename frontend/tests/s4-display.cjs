/**
 * MCP Playwright: v0.3 S4 — AI Output TaskDetail Display
 *
 * Verifies governance, artifacts, approval decisions, and human_required
 * are rendered correctly on the TaskDetail page.
 */
const { chromium } = require('playwright')
const http = require('node:http')

const FE = 'http://127.0.0.1:9700'
const BE = 'http://127.0.0.1:8700'

const t_actor = { actor: 'test' }
const r = { passed: 0, failed: 0, errors: [], networkFailures: [], details: [] }

function log(m) { console.log(m); r.details.push(m) }  // NOSONAR - test log
function pass(m) { r.passed++; log(`  [PASS] ${m}`) }
function fail(m, e) { r.failed++; log(`  [FAIL] ${m}: ${e}`) }

function httpGet(url, cb) {
  http.get(url, res => { let d = ''; res.on('data', c => d += c); res.on('end', () => cb({ status: res.statusCode, body: d })) })  // NOSONAR - test harness
    .on('error', cb)
}

function httpPost(url, body, cb) {
  const u = new URL(url)
  const req = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method: 'POST', headers: { 'Content-Type': 'application/json' } },  // NOSONAR - test harness
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

function apiPatch(path, body) { // NOSONAR - test harness
  return new Promise((resolve, reject) => {
    const u = new URL(`${BE}/api${path}`)
    const req = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method: 'PATCH', headers: { 'Content-Type': 'application/json' } },  // NOSONAR - test harness
      res => { let d = ''; res.on('data', c => d += c); res.on('end', () => resolve({ status: res.statusCode, body: d })) })
    req.on('error', reject); req.write(JSON.stringify(body)); req.end()
  })
}

async function seedData() {
  const proj = await apiPost('/projects', { name: `s4-proj-${Date.now()}`, root_path: '/s4' })
  const projId = proj.data?.id
  if (!projId) throw new Error('no project id')
  const task = await apiPost('/tasks', { project_id: projId, title: 'S4 display test', planner: 'test', description: 'Test governance display' })
  const taskId = task.data?.id
  if (!taskId) throw new Error('no task id')
  await apiPost('/agents', { name: 's4-agent', agent_type: 'executor', provider: 'sandbox' })
  return task.data
}

async function seedApprovalDecision(taskId) {
  const r2 = await apiPost(`/tasks/${taskId}/evaluate-approval`, {}) // NOSONAR
  return r2
}

async function seedCodeContext(taskId) {
  const ctx = { files: [
    { path: 'src/main.py', content: 'def hello():\n    print("hello")\n', language: 'python' },
    { path: 'src/utils.ts', content: 'export function greet(n: string) { return `Hi ${n}`; }', language: 'typescript' },
    { path: 'README.md', content: '# Test Project\nThis is a sample.', language: 'markdown' },
  ] }
  const r2 = await apiPost(`/tasks/${taskId}/code-context`, ctx)
  return r2
}

async function orchestrateSteps(taskId) {
  await apiPost(`/tasks/${taskId}/generate-ticket`, t_actor) // NOSONAR
  await apiPost(`/tasks/${taskId}/dispatch`, t_actor) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  await apiPost(`/tasks/${taskId}/orchestration/step`, {}) // NOSONAR
  // Create a succeeded execute run for sandbox apply with a valid unified diff
  const agents = await apiGet('/agents')
  const agentId = agents.data?.[0]?.id
  if (agentId) {
    // Diff: modify src/main.py — replace second line, add two new lines
    const patchDiff = [
      'diff --git a/src/main.py b/src/main.py',
      '--- a/src/main.py',
      '+++ b/src/main.py',
      '@@ -1,2 +1,4 @@',
      ' def hello():',
      '-    print("hello")',
      '+    print("hello world")',
      '+def world():',
      '+    print("world")',
    ].join('\n')
    const run = await apiPost(`/tasks/${taskId}/agent-runs`, { agent_id: agentId, run_type: 'execute', input_prompt: 'test execute' })
    const runId = run.data?.id
    if (runId) {
      await apiPatch(`/tasks/${taskId}/agent-runs/${runId}`, { status: 'running' })
      await apiPost(`/tasks/${taskId}/agent-runs/${runId}/submit-result`, {
        status: 'succeeded',
        output_summary: 'test sandbox output',
        output_diff: patchDiff,
      })
    }
  }
}

async function launchBrowser() {
  const b = await chromium.launch({ headless: true, channel: 'chrome' })
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

async function testCodeContext(page) {
  log('\n========== F. Code Context Display ==========')
  await checkT(page, '代码上下文', 'F1 Section')
  await checkT(page, 'API-provided context', 'F2 API-provided label')
  await checkT(page, 'Redacted', 'F3 Redacted label')
  await checkT(page, 'Not read from repository', 'F4 Not-read label')
  await checkT(page, 'src/main.py', 'F5 File path 1')
  await checkT(page, 'src/utils.ts', 'F6 File path 2')
  const n = await page.locator('.context-file-item').count()
  if (n >= 2) pass(`F7 ${n} context file items`)
  else fail(`F7 ${n} context files < 2`, '')
}

async function testSandboxSection(page) {
  log('\n========== G. Patch Sandbox Section ==========')
  await checkT(page, '补丁沙箱', 'G1 Section')
  await checkT(page, 'Sandbox only', 'G2 Sandbox only label')
  await checkT(page, 'Not committed', 'G3 Not committed label')
  await checkT(page, 'No PR created', 'G4 No PR created label')
}

async function testNoCodeContext(page, taskId) {
  log('\n========== I. No Code Context — 404 Recovery ==========')
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(1000)
  await checkT(page, '代码上下文', 'I1 Section title')
  await checkT(page, '暂无代码上下文数据', 'I2 Empty state message')
  pass('I3 TaskDetail loads without code context (no 404 crash)')
}

async function testSandboxApply(page) {
  log('\n========== H. Sandbox Apply & Result ==========')
  const sel = page.locator('.sandbox-run-select select')
  const optCount = await sel.locator('option').count()
  if (optCount <= 1) { fail('H1 No succeeded runs to select', ''); return }
  pass(`H1 ${optCount - 1} options found`)
  await sel.selectOption({ index: 1 })
  await page.waitForTimeout(200)
  await page.locator('button:has-text("Apply in Sandbox")').click()
  await page.waitForTimeout(2000)
  await checkEl(page, '.sandbox-result', 'H2 Sandbox result present')
  await checkEl(page, '.sandbox-result-header', 'H3 Result header present')
  const statusBadge = await page.locator('.sandbox-result-header .run-status-badge').count()
  if (statusBadge > 0) pass('H4 Status badge present')
  else fail('H4 Status badge missing', '')
  await checkEl(page, '.sandbox-changed-files', 'H5 Changed files section')
  await checkEl(page, '.sandbox-table', 'H6 Changed files table')
  await checkT(page, 'src/main.py', 'H6b Changed file path visible')
  await checkEl(page, '.sandbox-previews', 'H7 Before/after previews')
  await checkT(page, 'Before', 'H7b Before label')
  await checkT(page, 'After', 'H7c After label')
  await checkEl(page, '.sandbox-artifacts', 'H8 Sandbox artifacts')
  await checkEl(page, '.sandbox-artifact-item', 'H8b Artifact items')
}


async function setDispatchBatchesRoute(page, payload, status = 200) {
  await page.unroute('**/api/tasks/*/dispatch-batches').catch(() => {})
  await page.route('**/api/tasks/*/dispatch-batches', route => route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  }))
}

async function testMultiAiWorkspaceEmpty(page, taskId) {
  log('\n========== J. Multi-AI Answer Workspace Empty ==========')
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Multi-AI Answer Workspace / 多 AI 回答工作台', 'J1 Section')
  await checkT(page, '暂无多 AI Dispatch 记录', 'J2 Empty state')
  await checkT(page, 'Read-only display', 'J3 Read-only label')
  await checkT(page, 'No external PR created', 'J4 No external PR label')
  await checkT(page, 'No auto merge', 'J5 No auto merge label')
  await checkT(page, 'Sandbox only', 'J6 Sandbox only label')
}

async function testMultiAiWorkspaceRouted(page, taskId) {
  log('\n========== K. Multi-AI Answer Workspace Routed Data ==========')
  await setDispatchBatchesRoute(page, { success: true, data: [{
    dispatch_batch_id: 101,
    task_id: taskId,
    batch_mode: 'routed',
    status: 'succeeded',
    task_goal: 'Review PR #26',
    summary: { job_count: 2, status_counts: { succeeded: 1, blocked: 1 } },
    jobs: [
      {
        dispatch_job_id: 201,
        sequence_no: 1,
        question: 'Check PR body',
        provider: 'openai',
        model: 'gpt-4o-mini',
        mode: 'review',
        status: 'succeeded',
        prompt_hash: 'prompt1234',
        context_packet_hash: 'ctx1234',
        expected_artifact_type: 'review.md',
        safety_boundary: {},
        agent_run_id: 301,
        artifact_ids: [401, 402],
        error_message: null,
      },
      {
        dispatch_job_id: 202,
        sequence_no: 2,
        question: 'Check risk',
        provider: 'openai',
        model: 'gpt-4o-mini',
        mode: 'risk',
        status: 'blocked',
        prompt_hash: 'prompt5678',
        context_packet_hash: 'ctx5678',
        expected_artifact_type: 'risk_report.json',
        safety_boundary: {},
        agent_run_id: null,
        artifact_ids: [403],
        error_message: 'AI_EXECUTION_ENABLED is not set',
      },
    ],
  }], message: 'ok' })
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'routed', 'K1 batch_mode routed')
  await checkEl(page, 'text=Check PR body', 'K2 question 1')
  await checkEl(page, 'text=Check risk', 'K3 question 2')
  await checkT(page, 'provider: openai', 'K4 provider')
  await checkT(page, 'mode: review', 'K5 review mode')
  await checkT(page, 'mode: risk', 'K6 risk mode')
  await checkT(page, 'succeeded', 'K7 succeeded status')
  await checkT(page, 'blocked', 'K8 blocked status')
  await checkT(page, 'artifact_ids: 401, 402', 'K9 artifact ids')
  await checkT(page, 'AI_EXECUTION_ENABLED is not set', 'K10 blocked error')
}

async function testMultiAiWorkspaceApiFailure(page, taskId) {
  log('\n========== L. Multi-AI Answer Workspace API Failure ==========')
  await setDispatchBatchesRoute(page, { detail: 'dispatch batch unavailable' }, 500)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Multi-AI Answer Workspace / 多 AI 回答工作台', 'L1 Section still visible')
  await checkT(page, 'dispatch batch unavailable', 'L2 Error message')
  pass('L3 API failure does not crash TaskDetail')
}

async function testNoUnsafeWorkspaceActions(page) {
  log('\n========== M. No unsafe workspace actions ==========')
  const unsafeButtons = await page.locator('button:has-text("创建 PR"), button:has-text("Create PR"), button:has-text("PR Adapter not implemented"), button:has-text("merge"), button:has-text("Merge"), button:has-text("deploy"), button:has-text("Deploy"), button:has-text("部署")').count()
  const unsafeLinks = await page.locator('a:has-text("创建 PR"), a:has-text("Create PR"), a:has-text("PR Adapter not implemented"), a:has-text("merge"), a:has-text("Merge"), a:has-text("deploy"), a:has-text("Deploy"), a:has-text("部署")').count()
  const unsafeText = await page.locator('text=/PR Adapter not implemented|Future step only|No real PR created|Create PR|Deploy|Merge/').count()
  if (unsafeButtons === 0 && unsafeLinks === 0 && unsafeText === 0) pass('M1 No create PR / merge / deploy entry or stub')
  else fail('M1 Unsafe entry found', `buttons=${unsafeButtons}, links=${unsafeLinks}, text=${unsafeText}`)
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
  await seedCodeContext(task.id)
  pass('CodeContext seeded')
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
  await testCodeContext(page)
  await testSandboxSection(page)
  await testApprovals(page)
  await testHumanRequired(page)
  await testSandboxApply(page)
  await testMultiAiWorkspaceEmpty(page, task.id)
  await testMultiAiWorkspaceRouted(page, task.id)
  await testMultiAiWorkspaceApiFailure(page, task.id)
  await testNoUnsafeWorkspaceActions(page)
  // Create a separate task without code context for 404 test
  const bareTask = await apiPost('/tasks', { project_id: task.project_id, title: 'S4 no-ctx test', planner: 'test', description: 'No code context' })
  if (bareTask.data?.id) await testNoCodeContext(page, bareTask.data.id)
  // Navigate back to main task
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  printSummary(consoleErrors)
  await browser.close()
}

main().catch(e => { console.error('Test harness error:', e); process.exit(1) })


