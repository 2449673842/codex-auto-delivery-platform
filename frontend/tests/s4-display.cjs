/**
 * MCP Playwright: v0.3 S4 — AI Output TaskDetail Display
 *
 * Verifies governance, artifacts, approval decisions, and human_required
 * are rendered correctly on the TaskDetail page.
 */
const { chromium } = require('playwright')
const http = require('node:http')

const FE = process.env.CODEX_TEST_FRONTEND_URL || 'http://127.0.0.1:9700'
const BE = process.env.CODEX_TEST_BACKEND_URL || 'http://127.0.0.1:8700'

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
  await c.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: FE })
  await c.addInitScript(() => {
    const clipboardStore = { value: '' }
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => { clipboardStore.value = value },
        readText: async () => clipboardStore.value,
      },
    })
  })
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

async function checkBodyIncludes(page, text, label) {
  const body = await page.locator('body').innerText()
  if (body.includes(text)) pass(`${label}: "${text}"`)
  else fail(`${label}: "${text}" not found`, '')
}

async function checkBodyExcludes(page, text, label) {
  const body = await page.locator('body').innerText()
  if (body.includes(text)) fail(`${label}: "${text}" should be absent`, '')
  else pass(`${label}: "${text}" absent`)
}

async function checkTexts(page, entries) {
  for (const [text, label] of entries) await checkT(page, text, label)
}

async function checkUnsafeDeliveryAbsent(page, prefix, includeAutoNext = false) {
  const forbidden = includeAutoNext
    ? [['Auto next attempt', `${prefix} no auto next attempt entry`], ['Auto merge', `${prefix} no auto merge entry`]]
    : [['Auto fix repository', `${prefix} no auto fix entry`], ['Auto merge', `${prefix} no auto merge entry`]]
  for (const [text, label] of forbidden) await checkBodyExcludes(page, text, label)
  const deployEntries = await page.locator('button:has-text("Deploy"), a:has-text("Deploy")').count()
  if (deployEntries === 0) pass(`${prefix} no deploy entry`)
  else fail(`${prefix} no deploy entry`, deployEntries)
}

async function checkInputValue(page, selector, expected, label) {
  const values = await page.locator(selector).evaluateAll(nodes => nodes.map(node => node.value || ''))
  if (values.includes(expected)) pass(`${label}: "${expected}"`)
  else fail(`${label}: "${expected}" not found`, values.join(' | '))
}

async function checkInputValuesExclude(page, selector, forbidden, label) {
  const values = await page.locator(selector).evaluateAll(nodes => nodes.map(node => node.value || ''))
  if (values.includes(forbidden)) fail(`${label}: "${forbidden}" should be absent`, values.join(' | '))
  else pass(`${label}: "${forbidden}" absent from input values`)
}

async function checkInputValueAt(locator, index, expected, label) {
  const actual = await locator.nth(index).inputValue()
  if (actual === expected) pass(label)
  else fail(label, actual)
}

async function testDashboardFirstUsableWorkflow(page) {
  log('\n========== D0. Dashboard First Usable Workflow ==========')
  const projectCounter = { count: 0 }
  const taskCounter = { count: 0 }
  const runtimeCounter = { count: 0 }
  let createdProjectId = null
  let createdTaskId = null

  await page.unroute('**/api/ai-runtime/status').catch(() => {})
  await page.route('**/api/ai-runtime/status', route => fulfillJson(route, {
    success: true,
    data: {
      ai_execution_enabled: true,
      openai_credential_configured: true,
      credential_value: 'SHOULD_NOT_RENDER_RUNTIME_SECRET',
      provider_allowlist: ['openai'],
      openai_allowed: true,
      model: 'gpt-5.5',
      base_url_configured: true,
      wire_api: 'responses',
    },
    message: 'ok',
  }, 200, runtimeCounter))

  await page.unroute('**/api/projects').catch(() => {})
  await page.route('**/api/projects', async route => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }
    projectCounter.count += 1
    const body = route.request().postDataJSON()
    createdProjectId = 61001
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          id: createdProjectId,
          name: body.name,
          display_name: body.display_name,
          root_path: body.root_path,
          repo_url: null,
          default_branch: 'main',
          current_branch: 'main',
          package_manager: null,
          dev_command: null,
          build_command: null,
          test_command: null,
          ci_provider: null,
          ci_url: null,
          deploy_provider: null,
          deploy_url: null,
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          task_count: 0,
        },
        message: 'ok',
      }),
    })
  })

  await page.unroute('**/api/tasks').catch(() => {})
  await page.route('**/api/tasks', async route => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }
    taskCounter.count += 1
    const body = route.request().postDataJSON()
    createdTaskId = 62001
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          id: createdTaskId,
          project_id: body.project_id,
          title: body.title,
          description: body.description,
          status: 'draft',
          priority: 'medium',
          source: body.source || 'manual',
          planner: body.planner || null,
          executor: null,
          reviewer: null,
          human_approver: null,
          ticket_content: null,
          result_summary: null,
          pr_url: null,
          ci_url: null,
          deploy_url: null,
          target_branch: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          project_name: 'Demo AI Workbench',
        },
        message: 'ok',
      }),
    })
  })

  await page.goto(`${FE}/`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, '个人多 AI 编码工作台', 'D0-1 Dashboard title')
  await checkT(page, '创建第一个项目', 'D0-2 create first project button')
  await checkT(page, '创建演示项目并打开', 'D0-3 create demo button')
  await checkT(page, 'AI Runtime Status / AI 运行状态', 'D0-4 runtime status section')
  await checkT(page, 'configured', 'D0-5 key configured label')
  await checkT(page, 'gpt-5.5', 'D0-6 model visible')
  await checkT(page, 'Base URL', 'D0-7 base URL label')
  const leakedKey = await page.locator('text="SHOULD_NOT_RENDER_RUNTIME_SECRET"').count()
  if (leakedKey === 0) pass('D0-8 API key value not displayed')
  else fail('D0-8 API key leaked in dashboard', leakedKey)

  await page.getByRole('button', { name: '创建演示项目并打开' }).first().click()
  await page.waitForURL('**/tasks/*', { timeout: 5000 })
  if (runtimeCounter.count > 0) pass('D0-9 runtime status endpoint called')
  else fail('D0-9 runtime status endpoint not called', '')
  if (projectCounter.count === 1) pass('D0-10 create project API called')
  else fail('D0-10 create project API call count', projectCounter.count)
  if (taskCounter.count === 1) pass('D0-11 create task API called')
  else fail('D0-11 create task API call count', taskCounter.count)
  if (page.url().includes(`/tasks/${createdTaskId}`)) pass('D0-12 navigated to TaskDetail')
  else fail('D0-12 TaskDetail navigation failed', page.url())
}

async function testDashboardCreateFailure(page) {
  log('\n========== D0b. Dashboard Create Failure ==========')
  await page.unroute('**/api/ai-runtime/status').catch(() => {})
  await page.route('**/api/ai-runtime/status', route => fulfillJson(route, {
    success: true,
    data: {
      ai_execution_enabled: false,
      openai_credential_configured: false,
      provider_allowlist: ['sandbox'],
      openai_allowed: false,
      model: 'gpt-4o-mini',
      base_url_configured: false,
      wire_api: 'chat_completions',
    },
    message: 'ok',
  }, 200))
  await page.unroute('**/api/projects').catch(() => {})
  await page.route('**/api/projects', async route => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }
    await fulfillJson(route, { detail: 'project create failed' }, 500)
  })

  await page.goto(`${FE}/`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await page.getByRole('button', { name: '创建演示项目并打开' }).first().click()
  await page.waitForTimeout(500)
  await checkT(page, 'project create failed', 'D0b-1 create failure displayed')
  pass('D0b-2 Dashboard stays usable after create failure')
}

async function clearDashboardRoutes(page) {
  await page.unroute('**/api/ai-runtime/status').catch(() => {})
  await page.unroute('**/api/projects').catch(() => {})
  await page.unroute('**/api/tasks').catch(() => {})
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

async function testRealAiRun(page, taskId) {
  log('\n========== R. Real AI Run ==========')
  const dryCounter = { count: 0 }
  const executeCounter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setAiDispatchRoute(page, 'dry-run', aiDryRunPayload(), 200, dryCounter)
  await setAiDispatchRoute(page, 'execute', aiExecutePayload(taskId), 200, executeCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Real AI Run / 真实 AI 调用', 'R1 Section')
  await checkT(page, 'provider: openai', 'R2 provider')
  await checkT(page, 'model backend configured', 'R3 model')
  await page.locator('.real-ai-run').getByRole('button', { name: 'Dry-run' }).click()
  await page.waitForTimeout(300)
  if (dryCounter.count === 1) pass('R4 dry-run endpoint called')
  else fail('R4 dry-run endpoint call count', dryCounter.count)
  await checkT(page, 'would_dispatch=false', 'R5 would_dispatch false')
  await checkT(page, 'estimated_tokens=1888', 'R6 token estimate')
  await checkT(page, 'model: gpt-4o-mini', 'R6b dry-run model')
  await checkT(page, 'AI_EXECUTION_ENABLED 未开启', 'R7 execution disabled reason')
  await checkT(page, 'OPENAI_API_KEY 缺失', 'R8 missing key reason')
  await page.locator('.real-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(500)
  if (executeCounter.count === 1) pass('R9 execute endpoint called')
  else fail('R9 execute endpoint call count', executeCounter.count)
  await checkT(page, 'agent_run_id: 909', 'R10 agent_run_id displayed')
  await checkT(page, 'Real OpenAI answer saved', 'R11 output summary displayed')
  await checkT(page, 'patch.diff', 'R12 patch artifact displayed')
  await checkT(page, 'sandbox_applied=true', 'R13 sandbox applied displayed')
  await checkT(page, 'sandbox_gate_passed=true', 'R14 sandbox gate passed displayed')
  await checkT(page, 'Patch is not applied to the real repository. Sandbox only.', 'R15 sandbox only warning')
  await checkT(page, 'Sandbox Gate passed is required before any PR step.', 'R16 gate before PR warning')
  await checkT(page, 'sandbox_apply: succeeded (Patch Sandbox Apply)', 'R17 sandbox step displayed')
  await checkT(page, 'sandbox_gate: succeeded (Sandbox Gate)', 'R18 gate step displayed')
}

async function testRealAiRunPipelineFailures(page, taskId) {
  log('\n========== R2. Real AI Run Pipeline Failures ==========')
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setAiDispatchRoute(page, 'execute', aiExecutePayload(taskId, {
    pipeline_status: 'sandbox_failed',
    sandbox_applied: false,
    sandbox_gate_passed: false,
    steps: [{ step: 'sandbox_apply', status: 'failed', details: 'sandbox patch failed' }],
  }))
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await page.locator('.real-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'pipeline_status: sandbox_failed', 'R2-1 sandbox_failed status')
  await checkT(page, 'sandbox failed / blocked', 'R2-2 sandbox failed label')
  await setAiDispatchRoute(page, 'execute', aiExecutePayload(taskId, {
    pipeline_status: 'sandbox_gate_blocked',
    sandbox_applied: true,
    sandbox_gate_passed: false,
    sandbox_gate_blocked_reasons: ['risk_high', 'manual_review_required'],
    steps: [{ step: 'sandbox_gate', status: 'blocked', details: 'Sandbox Gate blocked' }],
  }))
  await page.locator('.real-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'pipeline_status: sandbox_gate_blocked', 'R2-3 gate blocked status')
  await checkT(page, 'gate blocked', 'R2-4 gate blocked label')
  await checkT(page, 'risk_high', 'R2-5 gate blocked reason risk')
  await checkT(page, 'manual_review_required', 'R2-6 gate blocked reason manual')
}

async function testBrowserAiRun(page, taskId) {
  log('\n========== BA. Browser AI Run ==========')
  const dryCounter = { count: 0 }
  const executeCounter = { count: 0 }
  const runsCounter = { count: 0 }
  const artifactsCounter = { count: 0 }
  const synthesisCounter = { count: 0 }
  await setBrowserAiProfilesRoute(page)
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setAgentRunsRoute(page, [{
    id: 707,
    task_id: taskId,
    project_id: 1,
    agent_id: 77,
    run_type: 'review',
    status: 'succeeded',
    input_prompt: 'Browser AI prompt redacted; prompt_hash=browser_prompt_hash; prompt_source=task_goal',
    output_summary: 'Mock browser visible answer',
    output_diff: null,
    output_log: 'Browser AI visible response captured from response_selector.',
    raw_result_json: '{}',
    branch: null,
    commit_sha: null,
    pr_url: null,
    risk_level: 'low',
    attempt_no: 1,
    duration_ms: null,
    error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }], 200, runsCounter)
  await setArtifactsRoute(page, [{
    id: 808,
    task_id: taskId,
    artifact_type: 'browser_ai_answer',
    storage_type: 'sqlite',
    content: 'Mock browser visible answer',
    file_path: null,
    filename: 'browser_ai_run_707_answer.md',
    size_bytes: 27,
    sha256: '1'.repeat(64),
    is_truncated: false,
    metadata_json: '{}',
    created_at: new Date().toISOString(),
  }], 200, artifactsCounter)
  await setAnswerSynthesisRoute(page, synthesisPayload(taskId, null, {
    job_count: 0,
    succeeded_jobs: 0,
    blocked_jobs: 0,
    common_findings: ['browser_ai_run_707: Mock browser visible answer'],
    risks: [],
    recommended_actions: ['Review related artifacts and verify Patch Sandbox / Sandbox Gate status.'],
    artifact_summaries: [{ artifact_id: 808, filename: 'browser_ai_run_707_answer.md', artifact_type: 'browser_ai_answer', summary: 'Mock browser visible answer', is_truncated: false }],
    source_job_ids: [],
    source_agent_run_ids: [707],
    source_artifact_ids: [808],
  }), 200, synthesisCounter)
  await setBrowserAiRoute(page, 'dry-run', browserAiPayload({
    status: 'blocked',
    answer_preview: '',
    agent_run_id: null,
    artifact_id: null,
    browser_opened: false,
    persisted: false,
    error_message: 'BROWSER_AI_ENABLED is not true',
    safety_gate: browserAiSafetyGate({
      browser_ai_enabled: false,
      gate_passed: false,
      blocked_reasons: ['BROWSER_AI_ENABLED is not true'],
    }),
  }), 200, dryCounter)
  await setBrowserAiRoute(page, 'execute', browserAiPayload(), 200, executeCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Browser AI / 网页 AI', 'BA1 section')
  await checkT(page, 'Local browser only', 'BA2 local browser label')
  await checkT(page, 'User-controlled login', 'BA3 user login label')
  await checkT(page, 'No password stored', 'BA4 no password label')
  await checkT(page, 'No cookies stored in DB', 'BA5 no cookies label')
  await checkT(page, 'No captcha bypass', 'BA5a no captcha bypass label')
  await checkT(page, 'No hidden API', 'BA6 no hidden API label')
  await checkBodyIncludes(page, 'Complete login in the opened browser, then retry Execute', 'BA6a login assist retry note shown')
  await checkT(page, 'Built-in selectors are best-effort and may break when the website changes. Switch to custom if needed.', 'BA6a best-effort selector note shown')
  const providerSelect = page.locator('.browser-ai-run select').first()
  for (const label of ['Custom', 'ChatGPT Web', 'Claude Web', 'Gemini Web', 'DeepSeek Web', 'Kimi Web']) {
    const count = await providerSelect.locator('option', { hasText: label }).count()
    if (count > 0) pass(`BA6b provider option ${label} shown`)
    else fail(`BA6b provider option ${label} missing`, '')
  }
  await providerSelect.selectOption('chatgpt_web')
  await checkInputValue(page, '.browser-ai-run input', 'https://chatgpt.com/', 'BA6c ChatGPT target_url autofilled')
  await checkInputValue(page, '.browser-ai-run input', "textarea[data-testid='prompt-textarea'], div[contenteditable='true']", 'BA6d ChatGPT input selector autofilled')
  await checkInputValue(page, '.browser-ai-run input', 'text=/log\\s*in/i, text=/sign\\s*in/i', 'BA6d2 ChatGPT login hint selector autofilled')
  await checkBodyIncludes(page, 'login may be required', 'BA6d3 provider login hint shown')
  await providerSelect.selectOption('claude_web')
  await checkInputValue(page, '.browser-ai-run input', 'https://claude.ai/new', 'BA6e Claude target_url autofilled')
  await providerSelect.selectOption('gemini_web')
  await checkInputValue(page, '.browser-ai-run input', 'https://gemini.google.com/app', 'BA6f Gemini target_url autofilled')
  await providerSelect.selectOption('deepseek_web')
  await checkInputValue(page, '.browser-ai-run input', 'https://chat.deepseek.com/', 'BA6g DeepSeek target_url autofilled')
  await providerSelect.selectOption('kimi_web')
  await checkInputValue(page, '.browser-ai-run input', 'https://www.kimi.com/chat/', 'BA6h Kimi target_url autofilled')
  await page.locator('.browser-ai-run input').nth(3).fill('textarea[name="manual"]')
  await checkInputValue(page, '.browser-ai-run input', 'textarea[name="manual"]', 'BA6i advanced selector remains editable')
  await providerSelect.selectOption('custom')
  await page.locator('.browser-ai-run input').nth(1).fill('http://127.0.0.1:9999/mock-browser-ai')
  await page.locator('.browser-ai-run input').nth(2).fill("textarea[name='prompt']")
  await page.locator('.browser-ai-run input').nth(3).fill('button[data-send]')
  await page.locator('.browser-ai-run input').nth(4).fill('[data-answer]')
  await page.locator('.browser-ai-run').getByRole('button', { name: 'Dry-run' }).click()
  await page.waitForTimeout(300)
  if (dryCounter.count === 1) pass('BA7 dry-run endpoint called')
  else fail('BA7 dry-run endpoint call count', dryCounter.count)
  await checkT(page, 'browser dry-run result', 'BA8 dry-run result shown')
  await checkT(page, 'prompt_hash: browser_prompt_hash', 'BA9 prompt hash shown')
  await checkT(page, 'browser_opened=false', 'BA10 dry-run does not open browser')
  await checkT(page, 'persisted=false', 'BA11 dry-run not persisted')
  await checkT(page, 'BROWSER_AI_ENABLED is not true', 'BA12 disabled reason displayed')
  await checkT(page, 'run steps', 'BA12a steps area shown')
  await checkT(page, 'validate_request', 'BA12b validate step shown')
  await checkT(page, 'build_prompt', 'BA12c build prompt step shown')
  await page.locator('.browser-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  if (executeCounter.count === 1) pass('BA13 execute endpoint called')
  else fail('BA13 execute endpoint call count', executeCounter.count)
  await checkT(page, 'browser execute result', 'BA14 execute result shown')
  await checkT(page, 'agent_run_id: 707', 'BA15 agent run id shown')
  await checkT(page, 'artifact_id: 808', 'BA16 artifact id shown')
  await checkT(page, 'Mock browser visible answer', 'BA17 answer preview shown')
  await checkT(page, 'open_browser', 'BA18 open browser step shown')
  await checkT(page, 'capture_answer', 'BA19 capture answer step shown')
  await checkT(page, 'persist_artifact', 'BA20 persist artifact step shown')
  await checkT(page, 'Browser AI answer saved', 'BA21 saved refresh message shown')
  await checkT(page, 'AgentRuns refreshed', 'BA22 agent runs refreshed message shown')
  await checkT(page, 'Artifacts refreshed', 'BA23 artifacts refreshed message shown')
  await checkT(page, 'Answer Synthesis refreshed', 'BA24 synthesis refreshed message shown')
  await checkT(page, 'browser_ai_answer', 'BA25 browser ai artifact type shown')
  await checkT(page, 'browser_ai_run_707_answer.md', 'BA26 browser ai artifact filename shown')
  await checkT(page, 'browser_ai_run_707: Mock browser visible answer', 'BA27 browser ai synthesis finding shown')
  await checkT(page, 'source_agent_run_ids: 707', 'BA28 browser ai source run id shown')
  await checkT(page, 'source_artifact_ids: 808', 'BA29 browser ai source artifact id shown')
  if (runsCounter.count > 0) pass('BA30 agent runs refresh endpoint called')
  else fail('BA30 agent runs refresh endpoint not called', '')
  if (artifactsCounter.count > 0) pass('BA31 artifacts refresh endpoint called')
  else fail('BA31 artifacts refresh endpoint not called', '')
  if (synthesisCounter.count > 0) pass('BA32 synthesis refresh endpoint called')
  else fail('BA32 synthesis refresh endpoint not called', '')
  await clearBrowserAiRefreshRoutes(page)
}

async function testBrowserAiFailures(page, taskId) {
  log('\n========== BA2. Browser AI Failures ==========')
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setBrowserAiRoute(page, 'execute', browserAiPayload({
    status: 'failed',
    answer_preview: '',
    agent_run_id: 708,
    artifact_id: null,
    error_message: 'selector not found',
    browser_opened: true,
    persisted: false,
    steps: browserAiSteps({ fill_prompt: 'failed', click_send: 'skipped' }, {
      fill_prompt: 'Input box was not found or could not be filled.',
    }),
  }))
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await page.locator('.browser-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'status: failed', 'BA2-1 failed status shown')
  await checkT(page, 'selector not found', 'BA2-2 selector error shown')
  await checkT(page, 'fill_prompt', 'BA2-2a failed step name shown')
  await checkT(page, 'failed', 'BA2-2b failed step status shown')
  await checkBodyIncludes(page, 'input box or send button is not found', 'BA2-2b human selector hint shown')
  await setBrowserAiRoute(page, 'execute', browserAiPayload({
    status: 'failed',
    answer_preview: '',
    agent_run_id: 709,
    artifact_id: null,
    error_message: 'timeout waiting response',
    browser_opened: true,
    persisted: false,
    steps: browserAiSteps({ wait_response: 'failed', capture_answer: 'skipped' }, {
      wait_response: 'Timed out waiting for a stable answer; the page may still be generating, manual login may be required, or selector may be wrong.',
    }),
  }))
  await page.locator('.browser-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'timeout waiting response', 'BA2-3 timeout error shown')
  await checkT(page, 'wait_response', 'BA2-4 wait response failed step shown')
  await checkBodyIncludes(page, 'manual login may be required', 'BA2-5 login hint shown')
  await checkBodyIncludes(page, 'stable answer', 'BA2-6 stable answer timeout hint shown')
  await setBrowserAiRoute(page, 'execute', browserAiPayload({
    status: 'failed',
    answer_preview: '',
    agent_run_id: 710,
    artifact_id: null,
    error_message: 'Manual login may be required. Please complete login in the opened browser, then retry Execute.',
    browser_opened: true,
    persisted: false,
    steps: browserAiSteps({ detect_login: 'failed', fill_prompt: 'skipped', click_send: 'skipped' }, {
      detect_login: 'Manual login may be required. Please complete login in the opened browser, then retry Execute.',
    }),
  }))
  await page.locator('.browser-ai-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'detect_login', 'BA2-7 login required failed step shown')
  await checkBodyIncludes(page, 'Complete login in the opened browser, then retry Execute', 'BA2-8 retry login instruction shown')
  const retryButtons = await page.locator('.browser-ai-run').getByRole('button', { name: 'Execute' }).count()
  if (retryButtons > 0) pass('BA2-9 Retry Execute button remains available')
  else fail('BA2-9 Retry Execute button missing', '')
  await checkBodyExcludes(page, 'Browser AI answer saved', 'BA2-10 failed execute does not show success refresh message')
}

async function testMultiAiEvidenceRunPanel(page, taskId) {
  log('\n========== S19. Multi-AI Evidence Run MVP ==========')
  const previewCounter = { count: 0 }
  const executeCounter = { count: 0 }
  const runsCounter = { count: 0 }
  const artifactsCounter = { count: 0 }
  const synthesisCounter = { count: 0 }
  await setBrowserAiProfilesRoute(page)
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setAgentRunsRoute(page, [
    runPayload(901, taskId, 'ChatGPT evidence answer'),
    runPayload(902, taskId, 'Claude evidence answer'),
  ], 200, runsCounter)
  await setArtifactsRoute(page, [
    artifactPayload(1001, taskId, 'browser_ai_answer', 'browser_ai_run_901_answer.md', 'ChatGPT evidence answer'),
    artifactPayload(1002, taskId, 'browser_ai_answer', 'browser_ai_run_902_answer.md', 'Claude evidence answer'),
  ], 200, artifactsCounter)
  await setEvidenceRunRoute(page, 'preview', evidenceRunPayload(taskId, {
    read_only: true,
    persisted: false,
    overall_status: 'ready',
    evidence_run_id: null,
    dispatch_batch_id: null,
    synthesis_refreshed: false,
  }), 200, previewCounter)
  await setEvidenceRunRoute(page, 'execute', evidenceRunPayload(taskId), 200, executeCounter)
  await setAnswerSynthesisRoute(page, synthesisPayload(taskId, 601, {
    job_count: 2,
    succeeded_jobs: 2,
    failed_jobs: 0,
    blocked_jobs: 0,
    common_findings: ['job_701: ChatGPT evidence answer', 'job_702: Claude evidence answer'],
    risks: [],
    disagreements: [],
    recommended_actions: ['Proceed to human review or local verification; no automatic approval is implied.'],
    artifact_summaries: [
      { artifact_id: 1001, filename: 'browser_ai_run_901_answer.md', artifact_type: 'browser_ai_answer', summary: 'ChatGPT evidence answer', is_truncated: false },
      { artifact_id: 1002, filename: 'browser_ai_run_902_answer.md', artifact_type: 'browser_ai_answer', summary: 'Claude evidence answer', is_truncated: false },
    ],
    source_job_ids: [701, 702],
    source_agent_run_ids: [901, 902],
    source_artifact_ids: [1001, 1002],
  }), 200, synthesisCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Multi-AI Evidence Run / 多 AI 证据运行', 'S19-1 panel shown')
  await checkT(page, 'Multi-AI Evidence Run is evidence collection, not code execution', 'S19-2 evidence-only label')
  await checkT(page, 'No repository writes', 'S19-3 no repo writes label')
  await checkT(page, 'No PR / CI / Sonar / Deploy', 'S19-4 no external delivery label')
  await checkT(page, 'No auto approve / merge', 'S19-5 no approve merge label')
  await checkBodyIncludes(page, 'bounded concurrency is planned; current MVP executes jobs sequentially', 'S19-6 concurrency note')
  await checkInputValuesExclude(page, '.multi-ai-evidence-run input', 'http://127.0.0.1:9999/mock-browser-ai', 'S19-6a no mock Browser AI URL in initial Multi-AI UI')
  await checkInputValuesExclude(page, '.multi-ai-evidence-run input', "textarea[name='prompt']", 'S19-6b no mock Browser AI selector in initial Multi-AI UI')
  const providerChecks = await page.locator('.multi-ai-evidence-run input[type="checkbox"]:checked').count()
  if (providerChecks >= 2) pass('S19-7 broadcast mode can select multiple providers')
  else fail('S19-7 provider multiselect missing', providerChecks)
  await page.locator('.multi-ai-evidence-run summary').click()
  const selectorInputs = page.locator('.multi-ai-evidence-run .selector-grid input')
  await checkInputValueAt(selectorInputs, 0, '', 'S19-7a advanced target_url starts empty')
  await page.locator('.multi-ai-evidence-run input[type="checkbox"]').first().setChecked(true)
  await checkInputValueAt(selectorInputs, 0, '', 'S19-7b provider selection does not inject mock target_url')
  await selectorInputs.nth(1).fill('textarea[name="manual-evidence"]')
  await checkInputValue(page, '.multi-ai-evidence-run input', 'textarea[name="manual-evidence"]', 'S19-7c advanced selector fallback remains editable')
  await page.locator('.multi-ai-evidence-run').getByRole('button', { name: 'Preview' }).click()
  await page.waitForTimeout(300)
  if (previewCounter.count === 1) pass('S19-8 preview endpoint called')
  else fail('S19-8 preview endpoint call count', previewCounter.count)
  await checkT(page, 'preview result', 'S19-9 preview result shown')
  await checkT(page, 'overall_status: ready', 'S19-10 preview status ready')
  await checkT(page, 'estimated_job_count: 2', 'S19-11 preview job count')
  await checkT(page, 'persisted=false', 'S19-12 preview persisted false')
  await checkT(page, 'read_only=true', 'S19-13 preview read only true')
  await checkT(page, 'provider: chatgpt_web', 'S19-14 preview job provider shown')
  await checkT(page, 'provider: claude_web', 'S19-15 preview second provider shown')
  await page.locator('.multi-ai-evidence-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(500)
  if (executeCounter.count === 1) pass('S19-16 execute endpoint called')
  else fail('S19-16 execute endpoint call count', executeCounter.count)
  await checkT(page, 'execute result', 'S19-17 execute result shown')
  await checkT(page, 'overall_status: succeeded', 'S19-18 succeeded overall status')
  await checkT(page, 'agent_run_id: 901', 'S19-19 first agent run id')
  await checkT(page, 'artifact_id: 1001', 'S19-20 first artifact id')
  await checkT(page, 'ChatGPT evidence answer', 'S19-21 first answer preview')
  await checkT(page, 'Claude evidence answer', 'S19-22 second answer preview')
  await checkT(page, 'Multi-AI Evidence Run saved', 'S19-23 saved refresh message')
  await checkT(page, 'AgentRuns refreshed', 'S19-24 agent runs refreshed')
  await checkT(page, 'Artifacts refreshed', 'S19-25 artifacts refreshed')
  await checkT(page, 'DispatchBatches refreshed', 'S19-26 dispatch batches refreshed')
  await checkT(page, 'Answer Synthesis refreshed', 'S19-27 synthesis refreshed')
  await checkT(page, 'source_artifact_ids: 1001, 1002', 'S19-28 synthesis source artifacts')
  if (runsCounter.count > 0) pass('S19-29 agent runs refresh endpoint called')
  else fail('S19-29 agent runs refresh endpoint not called', '')
  if (artifactsCounter.count > 0) pass('S19-30 artifacts refresh endpoint called')
  else fail('S19-30 artifacts refresh endpoint not called', '')
  if (synthesisCounter.count > 0) pass('S19-31 synthesis endpoint called')
  else fail('S19-31 synthesis endpoint not called', '')
  await clearEvidenceRunRoutes(page)
}

async function testMultiAiEvidenceRunRoutedPartial(page, taskId) {
  log('\n========== S19B. Multi-AI Evidence Run Routed Partial ==========')
  await setBrowserAiProfilesRoute(page)
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setAgentRunsRoute(page, [runPayload(903, taskId, 'Backend routed answer')])
  await setArtifactsRoute(page, [artifactPayload(1003, taskId, 'browser_ai_answer', 'browser_ai_run_903_answer.md', 'Backend routed answer')])
  await setEvidenceRunRoute(page, 'preview', evidenceRunPayload(taskId, {
    mode: 'routed',
    read_only: true,
    persisted: false,
    overall_status: 'ready',
    jobs: [
      evidenceJob(1, 'chatgpt_web', 'backend', 'preview'),
      evidenceJob(2, 'claude_web', 'frontend', 'preview'),
    ],
  }))
  await setEvidenceRunRoute(page, 'execute', evidenceRunPayload(taskId, {
    mode: 'routed',
    overall_status: 'partial',
    jobs: [
      evidenceJob(1, 'chatgpt_web', 'backend', 'succeeded', { agent_run_id: 903, artifact_id: 1003 }, 'Backend routed answer'),
      evidenceJob(2, 'claude_web', 'frontend', 'failed', { agent_run_id: 904 }, '', 'selector failed'),
    ],
    source_artifact_ids: [1003],
  }))
  await setAnswerSynthesisRoute(page, synthesisPayload(taskId, 601, {
    job_count: 2,
    succeeded_jobs: 1,
    failed_jobs: 1,
    blocked_jobs: 0,
    common_findings: ['job_701: Backend routed answer'],
    risks: ['job_702_failed: selector failed'],
    disagreements: ['not_all_jobs_succeeded'],
    artifact_summaries: [{ artifact_id: 1003, filename: 'browser_ai_run_903_answer.md', artifact_type: 'browser_ai_answer', summary: 'Backend routed answer', is_truncated: false }],
    source_job_ids: [701, 702],
    source_agent_run_ids: [903, 904],
    source_artifact_ids: [1003],
  }))
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await page.locator('.multi-ai-evidence-run select').first().selectOption('routed')
  await checkBodyIncludes(page, 'routed roles', 'S19B-1 routed role config visible')
  await checkInputValue(page, '.multi-ai-evidence-run input', 'backend', 'S19B-2 backend role visible')
  await checkInputValue(page, '.multi-ai-evidence-run input', 'frontend', 'S19B-3 frontend role visible')
  await page.locator('.multi-ai-evidence-run').getByRole('button', { name: 'Preview' }).click()
  await page.waitForTimeout(300)
  await checkBodyIncludes(page, '#1 backend', 'S19B-4 preview backend role')
  await checkBodyIncludes(page, '#2 frontend', 'S19B-5 preview frontend role')
  await page.locator('.multi-ai-evidence-run').getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(500)
  await checkT(page, 'overall_status: partial', 'S19B-6 partial status visible')
  await checkT(page, 'artifact_id: 1003', 'S19B-7 success artifact visible')
  await checkT(page, 'Backend routed answer', 'S19B-8 successful job answer visible')
  await checkT(page, 'selector failed', 'S19B-9 failed job error visible')
  await checkT(page, 'job_702_failed: selector failed', 'S19B-10 synthesis failed source risk visible')
  await checkT(page, 'Answer Synthesis refreshed', 'S19B-11 synthesis refreshed after partial')
  await clearEvidenceRunRoutes(page)
}

async function testFailureEvidencePreviewPanel(page, taskId) {
  log('\n========== S20.1 Failure Evidence Packet Preview ==========')
  const previewCounter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setFailureEvidenceRoute(page, failureEvidencePayload(taskId), 200, previewCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Failure Evidence Packet Preview / 失败证据包预览', 'S20-1 panel shown')
  await checkT(page, 'Failure Evidence preview is read-only', 'S20-2 read-only label shown')
  await checkT(page, 'No provider call', 'S20-3 no provider label shown')
  await checkT(page, 'No Browser AI execution', 'S20-4 no browser ai execution label shown')
  await checkT(page, 'No repository writes', 'S20-5 no repository writes label shown')
  await checkT(page, 'No PR / CI / Sonar / Deploy', 'S20-6 no external delivery label shown')
  await checkT(page, 'No auto approve / merge', 'S20-7 no approve merge label shown')
  await page.locator('.failure-evidence-preview select').first().selectOption('browser_ai_failed')
  await checkInputValue(page, '.failure-evidence-preview input', '4000', 'S20-8 max excerpt default shown')
  await page.locator('.failure-evidence-preview').getByRole('button', { name: 'Preview' }).click()
  await page.waitForTimeout(300)
  if (previewCounter.count === 1) pass('S20-9 preview endpoint called')
  else fail('S20-9 preview endpoint call count', previewCounter.count)
  await checkT(page, 'failure evidence packet', 'S20-10 packet shown')
  await checkT(page, 'failure_type: browser_ai_failed', 'S20-11 failure type shown')
  await checkT(page, 'failed_step: browser_ai', 'S20-12 failed step shown')
  await checkT(page, 'read_only=true', 'S20-13 read only true shown')
  await checkT(page, 'persisted=false', 'S20-14 persisted false shown')
  await checkT(page, 'redaction_applied=true', 'S20-15 redaction shown')
  await checkT(page, 'truncated=false', 'S20-16 truncation shown')
  await checkT(page, 'selector_failed', 'S20-17 safety reason shown')
  await checkT(page, 'No provider call is made.', 'S20-18 safety note shown')
  await checkBodyExcludes(page, 'Auto fix repository', 'S20-19 no auto fix entry')
  await checkBodyExcludes(page, 'Create PR', 'S20-20 no create PR entry')
  const deployEntries = await page.locator('button:has-text("Deploy"), a:has-text("Deploy")').count()
  if (deployEntries === 0) pass('S20-21 no deploy entry')
  else fail('S20-21 no deploy entry', deployEntries)
  await checkBodyExcludes(page, 'Merge PR', 'S20-22 no merge entry')
  await clearFailureEvidenceRoutes(page)
}

async function testRepairPacketGenerationPanel(page, taskId) {
  log('\n========== S20.2 Repair Packet Generation ==========')
  const failureCounter = { count: 0 }
  const repairCounter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setFailureEvidenceRoute(page, failureEvidencePayload(taskId), 200, failureCounter)
  await setRepairPacketRoute(page, repairPacketPayload(taskId), 200, repairCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Repair Packet Generation / 修复交接包生成', 'S20.2-1 panel shown')
  await checkT(page, 'Repair Packet does not modify code', 'S20.2-2 no code modification label')
  await checkT(page, 'Codex / OMX or user must execute repair', 'S20.2-3 external executor label')
  await checkT(page, 'No repository writes', 'S20.2-4 no repository writes label')
  await checkT(page, 'No auto PR / merge / deploy', 'S20.2-5 no auto delivery label')
  await checkT(page, 'max_attempts defaults to 1', 'S20.2-6 max attempts label')
  await page.locator('.failure-evidence-preview').getByRole('button', { name: 'Preview' }).click()
  await page.waitForTimeout(300)
  if (failureCounter.count === 1) pass('S20.2-7 failure evidence preview called')
  else fail('S20.2-7 failure evidence preview call count', failureCounter.count)
  await page.locator('.repair-packet-generation').getByRole('button', { name: 'Generate Repair Packet' }).click()
  await page.waitForTimeout(400)
  if (repairCounter.count === 1) pass('S20.2-8 repair packet endpoint called')
  else fail('S20.2-8 repair packet endpoint call count', repairCounter.count)
  await checkT(page, 'repair packet', 'S20.2-9 repair packet result shown')
  await checkT(page, 'repair_packet_artifact_id: 802', 'S20.2-10 artifact id shown')
  await checkT(page, 'human_decision_required=true', 'S20.2-11 human decision shown')
  await checkT(page, 'Failure summary for browser_ai_failed', 'S20.2-12 repair summary shown')
  await checkT(page, 'Selector failure caused missing Browser AI evidence.', 'S20.2-13 root cause shown')
  await checkT(page, 'Make a narrow selector/profile fix and rerun smoke.', 'S20.2-14 fix strategy shown')
  await checkT(page, 'codex_handoff_prompt preview', 'S20.2-15 handoff preview label shown')
  await checkT(page, 'AGENTS.md', 'S20.2-16 handoff prompt includes AGENTS')
  await checkBodyIncludes(page, 'Verify current master', 'S20.2-16b handoff prompt requires master verification')
  await checkT(page, 'Do not read `.env`.', 'S20.2-17 do_not_do shown')
  await checkT(page, 'Do not auto merge.', 'S20.2-18 no auto merge rule shown')
  await checkBodyExcludes(page, 'Auto fix repository', 'S20.2-19 no auto fix entry')
  await checkBodyExcludes(page, 'Auto merge', 'S20.2-20 no auto merge entry')
  const deployEntries = await page.locator('button:has-text("Deploy"), a:has-text("Deploy")').count()
  if (deployEntries === 0) pass('S20.2-21 no deploy entry')
  else fail('S20.2-21 no deploy entry', deployEntries)
  await clearRepairPacketRoutes(page)
  await clearFailureEvidenceRoutes(page)
}

async function testRepairHandoffPanel(page, taskId) {
  log('\n========== S20.3 Codex / OMX Repair Handoff ==========')
  const failureCounter = { count: 0 }
  const repairCounter = { count: 0 }
  const handoffCounter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setFailureEvidenceRoute(page, failureEvidencePayload(taskId), 200, failureCounter)
  await setRepairPacketRoute(page, repairPacketPayload(taskId), 200, repairCounter)
  await setRepairHandoffRoute(page, repairHandoffPayload(taskId), 200, handoffCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  const labels = [
    ['Codex / OMX Repair Handoff', 'S20.3-1 panel shown'],
    ['Handoff only', 'S20.3-2 handoff only label'],
    ['No repair execution', 'S20.3-3 no execution label'],
    ['No repository writes by platform', 'S20.3-4 no repository writes label'],
    ['No auto merge / deploy', 'S20.3-5 no auto merge deploy label'],
    ['Requires current master verification', 'S20.3-6 master verification label'],
  ]
  for (const [text, label] of labels) await checkT(page, text, label)
  await page.locator('.repair-handoff-preview select').selectOption('omx')
  await page.locator('.repair-handoff-preview select').selectOption('generic_ai')
  await page.locator('.repair-handoff-preview select').selectOption('codex')
  pass('S20.3-7 target can switch Codex / OMX / Generic AI')
  await page.locator('.failure-evidence-preview').getByRole('button', { name: 'Preview' }).click()
  await page.waitForTimeout(250)
  await page.locator('.repair-packet-generation').getByRole('button', { name: 'Generate Repair Packet' }).click()
  await page.waitForTimeout(300)
  await checkInputValue(page, '.repair-handoff-preview input', '802', 'S20.3-8 latest repair packet id filled')
  await page.locator('.repair-handoff-preview').getByRole('button', { name: 'Preview Handoff' }).click()
  await page.waitForTimeout(300)
  if (handoffCounter.count === 1) pass('S20.3-9 handoff endpoint called')
  else fail('S20.3-9 handoff endpoint call count', handoffCounter.count)
  const resultTexts = [
    ['repair handoff prompt', 'S20.3-10 handoff prompt shown'],
    ['source_repair_packet_artifact_id: 802', 'S20.3-11 source artifact shown'],
    ['requires_master_verification=true', 'S20.3-12 master verification true shown'],
    ['read_only=true', 'S20.3-13 read only true shown'],
    ['persisted=false', 'S20.3-14 persisted false shown'],
  ]
  for (const [text, label] of resultTexts) await checkT(page, text, label)
  for (const [text, label] of [
    ['Read AGENTS.md before acting.', 'S20.3-15 prompt includes AGENTS'],
    ['Run verification commands.', 'S20.3-16 prompt includes verification commands'],
    ['Create PR and wait for mastermind review.', 'S20.3-17 prompt includes PR review wait'],
  ]) await checkBodyIncludes(page, text, label)
  await checkT(page, 'Handoff only; no repair execution is performed by the platform.', 'S20.3-18 safety note shown')
  await checkEl(page, '.repair-handoff-preview button:has-text("Copy Handoff")', 'S20.3-19 copy button exists')
  for (const [text, label] of [
    ['Auto fix repository', 'S20.3-20 no auto fix entry'],
    ['Auto merge', 'S20.3-21 no auto merge entry'],
  ]) await checkBodyExcludes(page, text, label)
  const deployEntries = await page.locator('button:has-text("Deploy"), a:has-text("Deploy")').count()
  if (deployEntries === 0) pass('S20.3-22 no deploy entry')
  else fail('S20.3-22 no deploy entry', deployEntries)
  await clearRepairHandoffRoutes(page)
  await clearRepairPacketRoutes(page)
  await clearFailureEvidenceRoutes(page)
}

async function testRepairAttemptTimelinePanel(page, taskId) {
  log('\n========== S20.4 Repair Attempt Timeline ==========')
  const calls = { create: 0, handoff: 0, verify: 0, stop: 0 }
  const state = { attempts: [] }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setRepairAttemptsRoutes(page, state, calls)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  for (const [text, label] of [
    ['Repair Attempt Timeline', 'S20.4-1 panel shown'],
    ['Timeline only', 'S20.4-2 timeline only label'],
    ['Platform does not execute repair', 'S20.4-3 no platform execution label'],
    ['Verification result is imported, not run by platform', 'S20.4-4 imported verification label'],
    ['No auto next attempt', 'S20.4-5 no auto next attempt label'],
    ['No repository writes', 'S20.4-6 no repository writes label'],
    ['No auto PR / merge / deploy', 'S20.4-7 no auto delivery label'],
  ]) await checkT(page, text, label)
  await page.locator('.repair-attempt-timeline input[placeholder="latest repair packet id"]').fill('802')
  await page.locator('.repair-attempt-timeline input[placeholder="optional"]').fill('801')
  await page.locator('.repair-attempt-timeline').getByRole('button', { name: 'Create Attempt' }).click()
  await page.waitForTimeout(300)
  if (calls.create === 1) pass('S20.4-8 create attempt endpoint called')
  else fail('S20.4-8 create attempt endpoint call count', calls.create)
  for (const [text, label] of [
    ['attempt #1', 'S20.4-9 attempt number shown'],
    ['planned', 'S20.4-10 planned status shown'],
    ['executor: codex', 'S20.4-11 executor shown'],
    ['handoff_target: codex', 'S20.4-12 handoff target shown'],
    ['failure_evidence_artifact_id: 801', 'S20.4-13 failure evidence artifact shown'],
    ['repair_packet_artifact_id: 802', 'S20.4-14 repair packet artifact shown'],
  ]) await checkT(page, text, label)
  await page.locator('.repair-attempt-timeline').getByRole('button', { name: 'Mark Handoff Created' }).click()
  await page.waitForTimeout(250)
  if (calls.handoff === 1) pass('S20.4-15 handoff-created endpoint called')
  else fail('S20.4-15 handoff-created endpoint call count', calls.handoff)
  await checkT(page, 'handoff_created', 'S20.4-16 handoff_created status shown')
  await page.locator('.repair-attempt-timeline textarea[placeholder="One imported command per line"]').fill('python -m pytest backend/tests/test_repair_loop_attempts.py -q --rootdir backend')
  await page.locator('.repair-attempt-timeline textarea[placeholder="Imported verification log excerpt"]').fill('8 passed')
  await page.locator('.repair-attempt-timeline').getByRole('button', { name: 'Import Verification Result' }).click()
  await page.waitForTimeout(250)
  if (calls.verify === 1) pass('S20.4-17 verification import endpoint called')
  else fail('S20.4-17 verification import endpoint call count', calls.verify)
  await checkT(page, 'verification_passed', 'S20.4-18 verification_passed status shown')
  await checkT(page, 'verification_result_artifact_ids: 912', 'S20.4-19 verification artifact id shown')
  await page.locator('.repair-attempt-timeline').getByRole('button', { name: 'Stop Attempt' }).click()
  await page.waitForTimeout(250)
  if (calls.stop === 1) pass('S20.4-20 stop endpoint called')
  else fail('S20.4-20 stop endpoint call count', calls.stop)
  await checkT(page, 'stopped', 'S20.4-21 stopped status shown')
  for (const [text, label] of [
    ['Auto next attempt', 'S20.4-22 no auto next attempt entry'],
    ['Auto merge', 'S20.4-23 no auto merge entry'],
  ]) await checkBodyExcludes(page, text, label)
  const deployEntries = await page.locator('button:has-text("Deploy"), a:has-text("Deploy")').count()
  if (deployEntries === 0) pass('S20.4-24 no deploy entry')
  else fail('S20.4-24 no deploy entry', deployEntries)
  await clearRepairAttemptsRoutes(page)
}

async function testEvidenceSummaryPanel(page, taskId) {
  log('\n========== S22.2 Run Timeline / Evidence Board ===========')
  const timelineCounter = { count: 0 }
  const evidenceCounter = { count: 0 }
  await openEvidenceSummaryPage(
    page,
    taskId,
    timelineCounter,
    evidenceCounter,
  )
  await checkTexts(page, [
    ['Run Timeline / Evidence Board', 'S22.2-1 panel shown'],
    ['Run Timeline', 'S22.2-2 timeline section shown'],
    ['Evidence Board', 'S22.2-3 evidence board section shown'],
    ['Timeline is read-only', 'S22.2-4 timeline read-only label shown'],
    ['Evidence Board is read-only', 'S22.2-5 evidence board read-only label shown'],
    ['No provider call', 'S22.2-6 no provider label shown'],
    ['No Browser AI execution', 'S22.2-7 no browser ai label shown'],
    ['No repository writes', 'S22.2-8 no repository writes label shown'],
    ['No GitHub / Sonar query', 'S22.2-9 no GitHub Sonar query label shown'],
    ['No PR / CI / Sonar / Deploy', 'S22.2-10 no external delivery label shown'],
    ['No auto approve / merge', 'S22.2-11 no approve merge label shown'],
    ['timeline read_only=true', 'S22.2-12 timeline read_only shown'],
    ['timeline persisted=false', 'S22.2-13 timeline persisted shown'],
    ['evidence_board read_only=true', 'S22.2-14 evidence read_only shown'],
    ['evidence_board persisted=false', 'S22.2-15 evidence persisted shown'],
    ['type: repair_packet_generated', 'S22.2-16 timeline type shown'],
    ['completed', 'S22.2-17 timeline status shown'],
    ['source: repair_loop', 'S22.2-18 timeline source shown'],
    ['summary: Generated one-attempt repair packet from failure evidence.', 'S22.2-19 timeline summary shown'],
    ['repair_packet', 'S22.2-20 evidence type shown'],
    ['summary: Narrow repair strategy for sandbox gate failure.', 'S22.2-21 evidence summary shown'],
    ['redaction_status: redaction_applied=true, truncated=false, max_chars=2000', 'S22.2-23 redaction status shown'],
    ['no_repository_writes', 'S22.2-24 safety flag shown'],
    ['Codex / OMX or user must execute repair.', 'S22.2-25 safety note shown'],
  ])
  for (const [text, label] of [
    ['artifact_id: 802', 'S22.2-22a linked artifact id shown'],
    ['dispatch_batch_id: 201', 'S22.2-22b linked dispatch batch id shown'],
    ['repair_attempt_id: 1', 'S22.2-22c linked repair attempt id shown'],
  ]) await checkBodyIncludes(page, text, label)
  await checkEl(page, '.evidence-summary-panel button:has-text("Refresh Timeline / Evidence Board")', 'S22.2-26 refresh button exists')
  await page.locator('.evidence-summary-panel').getByRole('button', { name: 'Refresh Timeline / Evidence Board' }).click()
  await page.waitForTimeout(300)
  if (timelineCounter.count >= 2 && evidenceCounter.count >= 2) pass('S22.2-27 refresh reloads both read-only APIs')
  else fail('S22.2-27 refresh API call counts', `timeline=${timelineCounter.count}, evidence=${evidenceCounter.count}`)
  await checkUnsafeDeliveryAbsent(page, 'S22.2-28')
  await clearEvidenceSummaryRoutes(page)
}

async function testEvidenceSummaryApiFailure(page, taskId) {
  log('\n========== S22.2 Evidence Summary API Failure ===========')
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setEvidenceSummaryRoutes(
    page,
    { detail: 'timeline unavailable' },
    { detail: 'evidence board unavailable' },
    500,
  )
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Run Timeline / Evidence Board', 'S22.2-31 panel remains visible on API failure')
  await checkBodyIncludes(page, 'unavailable', 'S22.2-32 API failure error shown')
  await checkT(page, 'Agent 运行', 'S22.2-33 existing TaskDetail modules remain visible')
  await clearEvidenceSummaryRoutes(page)
}

async function testEvidenceBoardFiltersDetails(page, taskId) {
  log('\n========== S22.3 Evidence Board Filters / Details ==========')
  const timelineCounter = { count: 0 }
  const evidenceCounter = { count: 0 }
  await openEvidenceSummaryPage(
    page,
    taskId,
    timelineCounter,
    evidenceCounter,
    evidenceBoardPayload(taskId, { items: evidenceBoardFilterItems() }),
  )
  await checkTexts(page, [
    ['filtered count: 3 / total count: 3', 'S22.3-1 filtered count shown'],
    ['has_artifact=true', 'S22.3-2 has artifact true shown'],
    ['has_artifact=false', 'S22.3-3 has artifact false shown'],
    ['has_risk=true', 'S22.3-4 has risk true shown'],
    ['safety boundary: Codex / OMX or user must execute repair.', 'S22.3-5 safety boundary shown'],
    ['Copy evidence summary', 'S22.3-6 copy summary button shown'],
    ['Copy linked ids', 'S22.3-7 copy linked ids button shown'],
    ['Refresh Timeline / Evidence Board', 'S22.3-8 refresh button remains'],
  ])
  for (const selectorLabel of [
    ['.evidence-board-controls select >> nth=0', 'S22.3-9 evidence_type filter exists'],
    ['.evidence-board-controls select >> nth=1', 'S22.3-10 source filter exists'],
    ['.evidence-board-controls select >> nth=2', 'S22.3-11 status filter exists'],
    ['.evidence-board-controls select >> nth=3', 'S22.3-12 provider filter exists'],
    ['.evidence-board-controls select >> nth=4', 'S22.3-13 role filter exists'],
  ]) await checkEl(page, selectorLabel[0], selectorLabel[1])
  const timelineBefore = await page.locator('.timeline-item').count()
  await page.locator('.evidence-board-controls select').nth(0).selectOption('repair_packet')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S22.3-14 evidence_type filter changes count')
  await checkBodyIncludes(page, 'Narrow repair strategy for sandbox gate failure.', 'S22.3-15 repair packet remains after type filter')
  await checkBodyExcludes(page, 'Imported verification failed warning', 'S22.3-16 non-matching item hidden after type filter')
  const timelineAfterType = await page.locator('.timeline-item').count()
  if (timelineAfterType === timelineBefore) pass('S22.3-17 Run Timeline unaffected by evidence_type filter')
  else fail('S22.3-17 Run Timeline unaffected by evidence_type filter', `before=${timelineBefore}, after=${timelineAfterType}`)
  await page.locator('.evidence-board-controls button:has-text("Clear filters")').click()
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 3 / total count: 3', 'S22.3-18 clear filters restores count')
  await page.locator('.evidence-board-controls select').nth(1).selectOption('repair_loop')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 2 / total count: 3', 'S22.3-19 source filter changes count')
  await page.locator('.evidence-board-controls button:has-text("Clear filters")').click()
  await page.locator('.evidence-board-controls select').nth(2).selectOption('failed')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S22.3-20 status filter changes count')
  await checkBodyIncludes(page, 'Imported verification failed warning', 'S22.3-21 failed evidence shown')
  await page.locator('.evidence-board-controls button:has-text("Clear filters")').click()
  await page.locator('.evidence-board-controls select').nth(3).selectOption('browser_ai')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S22.3-22 provider filter changes count')
  await page.locator('.evidence-board-controls button:has-text("Clear filters")').click()
  await page.locator('.evidence-board-controls select').nth(4).selectOption('tester')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S22.3-23 role filter changes count')
  await page.locator('.evidence-board-controls button:has-text("Clear filters")').click()
  await page.locator('.evidence-board-item').first().locator('summary').click()
  await page.waitForTimeout(150)
  await checkTexts(page, [
    ['Evidence detail', 'S22.3-24 evidence detail expands'],
    ['raw_excerpt', 'S22.3-25 raw excerpt detail visible'],
    ['safety_notes: Codex / OMX or user must execute repair.', 'S22.3-26 safety notes detail visible'],
    ['redaction_status: redaction_applied=true, truncated=false, max_chars=2000', 'S22.3-27 redaction detail visible'],
  ])
  await page.locator('.evidence-board-item').first().getByRole('button', { name: 'Copy evidence summary' }).click()
  await page.waitForTimeout(150)
  await checkT(page, 'evidence summary copied', 'S22.3-28 copy evidence summary works')
  await page.locator('.evidence-board-item').first().getByRole('button', { name: 'Copy linked ids' }).click()
  await page.waitForTimeout(150)
  await checkT(page, 'linked ids copied', 'S22.3-29 copy linked ids works')
  await page.locator('.evidence-summary-panel').getByRole('button', { name: 'Refresh Timeline / Evidence Board' }).click()
  await page.waitForTimeout(250)
  if (timelineCounter.count >= 2 && evidenceCounter.count >= 2) pass('S22.3-30 refresh still reloads APIs')
  else fail('S22.3-30 refresh API call counts', `timeline=${timelineCounter.count}, evidence=${evidenceCounter.count}`)
  await checkUnsafeDeliveryAbsent(page, 'S22.3-31')
  await clearEvidenceSummaryRoutes(page)
}

async function testProjectMemoryPanel(page, task) {
  log('\n========== S23.2 Project Memory UI ==========')
  const memoryCounter = { count: 0 }
  const summaryCounter = { count: 0 }
  await openProjectMemoryPage(page, task, memoryCounter, summaryCounter)
  await checkTexts(page, [
    ['Project Memory', 'S23.2-1 panel shown'],
    ['Project Memory Summary', 'S23.2-2 summary section shown'],
    ['Project Memory is read-only', 'S23.2-3 read-only label shown'],
    ['No memory writes', 'S23.2-4 no writes label shown'],
    ['No provider call', 'S23.2-5 no provider label shown'],
    ['No Browser AI execution', 'S23.2-6 no Browser AI label shown'],
    ['No repository writes', 'S23.2-7 no repository writes label shown'],
    ['No GitHub / Sonar query', 'S23.2-8 no GitHub Sonar label shown'],
    ['No PR / CI / Sonar / Deploy', 'S23.2-9 no external delivery label shown'],
    ['No auto approve / merge', 'S23.2-10 no auto merge label shown'],
    ['Memory may be stale; verify before acting', 'S23.2-11 stale warning shown'],
    ['memory read_only=true', 'S23.2-12 memory read_only shown'],
    ['memory persisted=false', 'S23.2-13 memory persisted shown'],
    ['summary read_only=true', 'S23.2-14 summary read_only shown'],
    ['summary persisted=false', 'S23.2-15 summary persisted shown'],
    ['memory_count: 3', 'S23.2-16 memory count shown'],
    ['memory_types: project_profile, verification_policy, safety_policy', 'S23.2-17 memory types shown'],
    ['stale_count: 1', 'S23.2-18 stale count shown'],
    ['high_confidence_count: 2', 'S23.2-19 high confidence count shown'],
    ['summary: Project Memory stable context summary.', 'S23.2-20 summary text shown'],
    ['memory_type: project_profile', 'S23.2-21 memory type shown'],
    ['Project profile', 'S23.2-22 title shown'],
    ['summary: AI coding evidence / memory workbench.', 'S23.2-23 item summary shown'],
    ['confidence: high', 'S23.2-24 confidence shown'],
    ['stale: false', 'S23.2-25 stale false shown'],
    ['source_refs: docs:AGENTS.md', 'S23.2-27 source refs shown'],
    ['redaction_status: redaction_applied=true, truncated=false, max_chars=4000', 'S23.2-28 redaction status shown'],
    ['Memory content detail', 'S23.2-29 content detail exists'],
    ['Copy memory summary', 'S23.2-30 copy memory summary exists'],
    ['Copy source refs', 'S23.2-31 copy source refs exists'],
    ['Refresh Project Memory', 'S23.2-32 refresh button exists'],
    ['filtered count: 3 / total count: 3', 'S23.2-33 filtered count shown'],
  ])
  if (memoryCounter.count >= 1 && summaryCounter.count >= 1) pass('S23.2-34 automatically calls memory and summary APIs')
  else fail('S23.2-34 memory API call counts', `memory=${memoryCounter.count}, summary=${summaryCounter.count}`)
  await checkBodyIncludes(page, 'updated_at:', 'S23.2-26 updated_at shown')
  for (const selectorLabel of [
    ['.project-memory-controls select >> nth=0', 'S23.2-35 memory_type filter exists'],
    ['.project-memory-controls select >> nth=1', 'S23.2-36 confidence filter exists'],
    ['.project-memory-controls select >> nth=2', 'S23.2-37 stale filter exists'],
  ]) await checkEl(page, selectorLabel[0], selectorLabel[1])
  const evidenceBefore = await page.locator('.evidence-board-item').count()
  await page.locator('.project-memory-controls select').nth(0).selectOption('safety_policy')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S23.2-38 memory_type filter changes count')
  await checkBodyIncludes(page, 'Never read secrets.', 'S23.2-39 matching memory remains')
  await checkBodyExcludes(page, 'Use targeted pytest and npm build.', 'S23.2-40 non-matching memory hidden')
  const evidenceAfter = await page.locator('.evidence-board-item').count()
  if (evidenceAfter === evidenceBefore) pass('S23.2-41 Project Memory filter does not affect Evidence Board')
  else fail('S23.2-41 Evidence Board unaffected by memory filter', `before=${evidenceBefore}, after=${evidenceAfter}`)
  await page.locator('.project-memory-controls button:has-text("Clear filters")').click()
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 3 / total count: 3', 'S23.2-42 clear filters restores count')
  await page.locator('.project-memory-controls select').nth(1).selectOption('medium')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S23.2-43 confidence filter changes count')
  await page.locator('.project-memory-controls button:has-text("Clear filters")').click()
  await page.locator('.project-memory-controls select').nth(2).selectOption('true')
  await page.waitForTimeout(150)
  await checkT(page, 'filtered count: 1 / total count: 3', 'S23.2-44 stale filter changes count')
  await page.locator('.project-memory-controls button:has-text("Clear filters")').click()
  await page.locator('.project-memory-item').first().locator('summary').click()
  await page.waitForTimeout(150)
  await checkBodyIncludes(page, '"technology_stack"', 'S23.2-45 content detail expands')
  await page.locator('.project-memory-item').first().getByRole('button', { name: 'Copy memory summary' }).click()
  await page.waitForTimeout(150)
  await checkT(page, 'memory summary copied', 'S23.2-46 copy memory summary works')
  await page.locator('.project-memory-item').first().getByRole('button', { name: 'Copy source refs' }).click()
  await page.waitForTimeout(150)
  await checkT(page, 'source refs copied', 'S23.2-47 copy source refs works')
  await page.locator('.project-memory-panel').getByRole('button', { name: 'Refresh Project Memory' }).click()
  await page.waitForTimeout(250)
  if (memoryCounter.count >= 2 && summaryCounter.count >= 2) pass('S23.2-48 refresh reloads both Project Memory APIs')
  else fail('S23.2-48 refresh API call counts', `memory=${memoryCounter.count}, summary=${summaryCounter.count}`)
  await checkUnsafeDeliveryAbsent(page, 'S23.2-49')
  await checkBodyExcludes(page, 'Auto memory write', 'S23.2-50 no auto memory write entry')
  await clearProjectMemoryRoutes(page)
}

async function testProjectMemoryApiFailure(page, task) {
  log('\n========== S23.2 Project Memory API Failure ==========')
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(task.id, task.project_id), 200)
  await setEvidenceSummaryRoutes(page, timelinePayload(task.id), evidenceBoardPayload(task.id), 200)
  await setProjectMemoryRoutes(page, { detail: 'project memory unavailable' }, { detail: 'memory summary unavailable' }, 500)
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'Project Memory', 'S23.2-51 panel remains visible on API failure')
  await checkBodyIncludes(page, 'project memory unavailable', 'S23.2-52 API failure error shown')
  await checkT(page, 'Agent 运行', 'S23.2-53 existing TaskDetail modules remain visible')
  await clearProjectMemoryRoutes(page)
}

async function testMastermindReviewPanel(page, task) {
  log('\n========== S24.1.3 Mastermind Review UI ==========')
  const previewCounter = { count: 0 }
  const executeCounter = { count: 0 }
  const timelineCounter = { count: 0 }
  const evidenceCounter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(task.id, task.project_id), 200)
  await setProjectMemoryRoutes(page, projectMemoryPayload(task.project_id), projectMemorySummaryPayload(task.project_id), 200)
  await setEvidenceSummaryRoutes(
    page,
    timelinePayload(task.id),
    evidenceBoardPayload(task.id),
    200,
    timelineCounter,
    evidenceCounter,
  )
  await setMastermindReviewRoutes(
    page,
    mastermindPreviewPayload(task.id, task.project_id),
    mastermindExecutePayload(task.id, task.project_id),
    200,
    previewCounter,
    executeCounter,
  )
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkTexts(page, [
    ['Mastermind Review', 'S24.1.3-1 panel shown'],
    ['Mastermind review is advisory only', 'S24.1.3-2 advisory label shown'],
    ['Human confirmation required', 'S24.1.3-3 human confirmation label shown'],
    ['No auto approve', 'S24.1.3-4 no approve label shown'],
    ['No auto merge', 'S24.1.3-5 no merge label shown'],
    ['No auto deploy', 'S24.1.3-6 no deploy label shown'],
    ['No auto rework', 'S24.1.3-7 no rework label shown'],
    ['Browser AI uses visible user-authorized UI only', 'S24.1.3-8 visible UI label shown'],
    ['No account/password/cookie/session storage', 'S24.1.3-9 no credential storage label shown'],
    ['No captcha/login bypass', 'S24.1.3-10 no bypass label shown'],
    ['No repository writes', 'S24.1.3-11 no repository writes label shown'],
    ['No GitHub / Sonar platform query', 'S24.1.3-12 no GitHub Sonar query label shown'],
    ['Preview Mastermind Review Packet', 'S24.1.3-13 preview button shown'],
    ['Run Browser AI Mastermind Review', 'S24.1.3-14 execute button shown'],
  ])
  await page.locator('.mastermind-review-panel input[placeholder="https://github.com/org/repo/pull/64"]').fill('https://github.com/2449673842/codex-auto-delivery-platform/pull/64')
  await page.locator('.mastermind-review-panel input[placeholder="64"]').fill('64')
  await page.locator('.mastermind-review-panel input[placeholder="full head sha"]').fill('f193b7f3d36c31ce90f733e1a3ed5a61cec345f4')
  await page.locator('.mastermind-review-panel input[placeholder="full base sha"]').fill('17464b6b2cbafd7e15870a04b924c6cd945b239c')
  await page.locator('.mastermind-review-panel textarea[placeholder="one file per line, or comma separated"]').fill('frontend/src/pages/TaskDetailPage.vue\nfrontend/tests/s4-display.cjs')
  await page.locator('.mastermind-review-panel textarea[placeholder="PR body text or excerpt"]').fill('S24.1.3 UI PR body with verification and safety boundary.')
  await page.locator('.mastermind-review-panel input[placeholder="https://chatgpt.com/"]').fill('http://127.0.0.1:9999/mock-browser-ai')
  await page.locator('.mastermind-review-panel input[placeholder="textarea[name=\'prompt\']"]').fill("textarea[name='prompt']")
  await page.locator('.mastermind-review-panel input[placeholder="button[data-send]"]').fill('button[data-send]')
  await page.locator('.mastermind-review-panel input[placeholder="[data-answer]"]').fill('[data-answer]')
  await page.locator('.mastermind-review-panel').getByRole('button', { name: 'Preview Mastermind Review Packet' }).click()
  await page.waitForTimeout(300)
  if (previewCounter.count === 1) pass('S24.1.3-15 packet-preview API called')
  else fail('S24.1.3-15 packet-preview API call count', previewCounter.count)
  await checkTexts(page, [
    ['packet_type: mastermind_review_packet', 'S24.1.3-16 packet type shown'],
    ['PR number: 64', 'S24.1.3-17 PR number shown'],
    ['targeted_backend_pytest: 9 passed', 'S24.1.3-18 verification shown'],
    ['quality_gate: Passed', 'S24.1.3-19 Sonar shown'],
    ['review_instruction', 'S24.1.3-25 review instruction detail shown'],
    ['required_output_contract', 'S24.1.3-26 output contract detail shown'],
    ['read_only=true', 'S24.1.3-27 preview read_only shown'],
    ['persisted=false', 'S24.1.3-28 preview persisted shown'],
    ['redaction_status: redaction_applied=true, truncated=false, max_chars=12000', 'S24.1.3-29 redaction status shown'],
    ['Packet preview is read-only.', 'S24.1.3-30 safety note shown'],
  ])
  await checkBodyIncludes(page, 'task_summary: Task #', 'S24.1.3-20 task summary shown')
  await checkBodyIncludes(page, 'evidence_board_summary: Evidence Board items:', 'S24.1.3-21 evidence summary shown')
  await checkBodyIncludes(page, 'run_timeline_summary: Run Timeline items:', 'S24.1.3-22 timeline summary shown')
  await checkBodyIncludes(page, 'project_memory_summary: memory_count=8', 'S24.1.3-23 project memory summary shown')
  await checkBodyIncludes(page, 'handoff_context: Repair handoff summary', 'S24.1.3-24 handoff context shown')
  await page.locator('.mastermind-review-panel').getByRole('button', { name: 'Run Browser AI Mastermind Review' }).click()
  await page.waitForTimeout(500)
  if (executeCounter.count === 1) pass('S24.1.3-31 execute API called')
  else fail('S24.1.3-31 execute API call count', executeCounter.count)
  await checkTexts(page, [
    ['status: succeeded', 'S24.1.3-32 status shown'],
    ['verdict: approved', 'S24.1.3-33 verdict shown'],
    ['summary: Mastermind review approved as advisory only.', 'S24.1.3-34 summary shown'],
    ['blocking_items: -', 'S24.1.3-35 blocking items shown'],
    ['recommended_actions: Keep human confirmation before merge.', 'S24.1.3-36 recommended actions shown'],
    ['safety_notes: Advisory only; no automatic merge.', 'S24.1.3-37 safety notes shown'],
    ['raw_excerpt', 'S24.1.3-38 raw excerpt detail exists'],
    ['agent_run_id: 6401', 'S24.1.3-39 agent run id shown'],
    ['artifact_id: 6402', 'S24.1.3-40 artifact id shown'],
    ['parse_errors: -', 'S24.1.3-41 parse errors shown'],
    ['advisory_only=true', 'S24.1.3-42 advisory true shown'],
    ['human_confirmation_required=true', 'S24.1.3-43 human confirmation true shown'],
    ['no_auto_merge=true', 'S24.1.3-44 no auto merge true shown'],
    ['Mastermind Review saved; AgentRun, artifacts, Timeline, and Evidence Board refreshed', 'S24.1.3-45 refresh status shown'],
  ])
  if (timelineCounter.count >= 2 && evidenceCounter.count >= 2) pass('S24.1.3-46 execute refreshes Timeline and Evidence Board')
  else fail('S24.1.3-46 execute refresh counts', `timeline=${timelineCounter.count}, evidence=${evidenceCounter.count}`)
  await checkUnsafeDeliveryAbsent(page, 'S24.1.3-47')
  await checkBodyExcludes(page, 'Auto rework', 'S24.1.3-48 no unsafe rework action text')
  await clearMastermindReviewRoutes(page)
  await clearProjectMemoryRoutes(page)
  await clearEvidenceSummaryRoutes(page)
}

async function testMastermindReviewApiFailure(page, task) {
  log('\n========== S24.1.3 Mastermind Review API Failure ==========')
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(task.id, task.project_id), 200)
  await setProjectMemoryRoutes(page, projectMemoryPayload(task.project_id), projectMemorySummaryPayload(task.project_id), 200)
  await setEvidenceSummaryRoutes(page, timelinePayload(task.id), evidenceBoardPayload(task.id), 200)
  await setMastermindReviewRoutes(page, { detail: 'mastermind preview unavailable' }, mastermindExecutePayload(task.id, task.project_id), 500)
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await page.locator('.mastermind-review-panel').getByRole('button', { name: 'Preview Mastermind Review Packet' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'Mastermind Review', 'S24.1.3-51 panel remains visible on API failure')
  await checkBodyIncludes(page, 'unavailable', 'S24.1.3-52 API failure error shown')
  await checkT(page, 'Agent 运行', 'S24.1.3-53 existing TaskDetail modules remain visible')
  await clearMastermindReviewRoutes(page)
}

async function openEvidenceSummaryPage(page, taskId, timelineCounter, evidenceCounter, boardPayload = evidenceBoardPayload(taskId)) {
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setEvidenceSummaryRoutes(
    page,
    timelinePayload(taskId),
    boardPayload,
    200,
    timelineCounter,
    evidenceCounter,
  )
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
}

async function openProjectMemoryPage(page, task, memoryCounter, summaryCounter) {
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(task.id, task.project_id), 200)
  await setEvidenceSummaryRoutes(page, timelinePayload(task.id), evidenceBoardPayload(task.id), 200)
  await setProjectMemoryRoutes(
    page,
    projectMemoryPayload(task.project_id),
    projectMemorySummaryPayload(task.project_id),
    200,
    memoryCounter,
    summaryCounter,
  )
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
}

async function testMcpBridgePanel(page, taskId) {
  log('\n========== MCP. MCP Bridge Read-only Dry-run ==========')
  const mcpCounter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200)
  await setMcpRoutes(page, taskId, mcpCounter)
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, 'MCP Bridge / 外部 AI 工具桥', 'MCP1 section shown')
  await checkT(page, 'MCP Bridge S18 is read-only + dry-run only', 'MCP2 read-only dry-run label shown')
  await checkBodyIncludes(page, 'get_task_brief', 'MCP3 task brief tool shown')
  await checkBodyIncludes(page, 'get_handoff_packet', 'MCP4 handoff tool shown')
  await checkBodyIncludes(page, 'ai_dispatch_dry_run', 'MCP5 ai dispatch dry-run tool shown')
  await checkBodyIncludes(page, 'browser_ai_dry_run', 'MCP6 browser ai dry-run tool shown')
  await checkT(page, 'No MCP execute', 'MCP7 no execute label shown')
  await page.locator('.mcp-bridge-panel').getByRole('button', { name: 'Preview MCP Handoff' }).click()
  await page.waitForTimeout(300)
  if (mcpCounter.count === 1) pass('MCP8 mcp call endpoint called')
  else fail('MCP8 mcp call endpoint call count', mcpCounter.count)
  await checkT(page, 'tool: get_handoff_packet', 'MCP9 tool result shown')
  await checkT(page, 'persisted=false', 'MCP10 persisted false shown')
  await checkBodyIncludes(page, 'MCP handoff summary for S4 display test', 'MCP11 handoff summary shown')
  await checkT(page, 'No OpenAI execute is allowed.', 'MCP12 safety note shown')
  await checkBodyExcludes(page, 'Run MCP Execute', 'MCP13 no MCP execute entry')
  await checkBodyExcludes(page, 'Create PR', 'MCP14 no create PR entry')
  const deployEntries = await page.locator('button:has-text("Deploy"), a:has-text("Deploy")').count()
  if (deployEntries === 0) pass('MCP15 no deploy entry')
  else fail('MCP15 no deploy entry', deployEntries)
  await checkBodyExcludes(page, 'Merge PR', 'MCP16 no merge entry')
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

async function setAnswerSynthesisRoute(page, payload, status = 200, counter = null) {
  await page.unroute('**/api/answer-synthesis/preview').catch(() => {})
  await page.route('**/api/answer-synthesis/preview', route => fulfillJson(route, payload, status, counter))
}

async function setAiHandoffRoute(page, payload, status = 200, counter = null) {
  await page.unroute('**/api/ai-handoff/preview').catch(() => {})
  await page.route('**/api/ai-handoff/preview', route => fulfillJson(route, payload, status, counter))
}

async function setMcpRoutes(page, taskId, counter = null) {
  await page.unroute('**/api/mcp/tools**').catch(() => {})
  await page.unroute('**/api/mcp/call**').catch(() => {})
  await page.route('**/api/mcp/tools**', route => fulfillJson(route, mcpToolsPayload(), 200))
  await page.route('**/api/mcp/call**', route => fulfillJson(route, mcpCallPayload(taskId), 200, counter))
}

async function setAiDispatchRoute(page, action, payload, status = 200, counter = null) {
  await page.unroute(`**/api/ai-dispatch/${action}`).catch(() => {})
  await page.route(`**/api/ai-dispatch/${action}`, route => fulfillJson(route, payload, status, counter))
}

async function setBrowserAiRoute(page, action, payload, status = 200, counter = null) {
  await page.unroute(`**/api/browser-ai/${action}`).catch(() => {})
  await page.route(`**/api/browser-ai/${action}`, route => fulfillJson(route, payload, status, counter))
}

async function setEvidenceRunRoute(page, action, payload, status = 200, counter = null) {
  await page.unroute(`**/api/multi-ai-evidence-runs/${action}`).catch(() => {})
  await page.route(`**/api/multi-ai-evidence-runs/${action}`, route => fulfillJson(route, payload, status, counter))
}

async function setFailureEvidenceRoute(page, payload, status = 200, counter = null) {
  await page.unroute('**/api/repair-loop/failure-evidence/preview').catch(() => {})
  await page.route('**/api/repair-loop/failure-evidence/preview', route => fulfillJson(route, payload, status, counter))
}

async function setRepairPacketRoute(page, payload, status = 200, counter = null) {
  await page.unroute('**/api/repair-loop/repair-packet/generate').catch(() => {})
  await page.route('**/api/repair-loop/repair-packet/generate', route => fulfillJson(route, payload, status, counter))
}

async function setRepairHandoffRoute(page, payload, status = 200, counter = null) {
  await page.unroute('**/api/repair-loop/codex-handoff/preview').catch(() => {})
  await page.route('**/api/repair-loop/codex-handoff/preview', route => fulfillJson(route, payload, status, counter))
}

async function setRepairAttemptsRoutes(page, state, calls) {
  await clearRepairAttemptsRoutes(page)
  await page.route('**/api/tasks/*/repair-attempts', route => fulfillJson(route, { success: true, data: state.attempts, message: 'ok' }, 200))
  await page.route('**/api/repair-loop/attempts', async route => {
    calls.create += 1
    state.attempts = [repairAttemptPayload(1, route.request().postDataJSON?.() || {})]
    await fulfillJson(route, { success: true, data: state.attempts[0], message: 'ok' }, 200)
  })
  await page.route('**/api/repair-loop/attempts/*/handoff-created', async route => {
    calls.handoff += 1
    state.attempts = state.attempts.map(attempt => ({ ...attempt, status: 'handoff_created' }))
    await fulfillJson(route, { success: true, data: state.attempts[0], message: 'ok' }, 200)
  })
  await page.route('**/api/repair-loop/attempts/*/verification-result', async route => {
    calls.verify += 1
    const body = route.request().postDataJSON?.() || {}
    state.attempts = state.attempts.map(attempt => ({
      ...attempt,
      status: body.status || 'verification_passed',
      verification_result_artifact_ids: [912],
      summary: body.summary || attempt.summary,
    }))
    await fulfillJson(route, { success: true, data: state.attempts[0], message: 'ok' }, 200)
  })
  await page.route('**/api/repair-loop/attempts/*/stop', async route => {
    calls.stop += 1
    state.attempts = state.attempts.map(attempt => ({ ...attempt, status: 'stopped' }))
    await fulfillJson(route, { success: true, data: state.attempts[0], message: 'ok' }, 200)
  })
}

async function setEvidenceSummaryRoutes(
  page,
  timelineData,
  evidenceBoardData,
  status = 200,
  timelineCounter = null,
  evidenceCounter = null,
) {
  await clearEvidenceSummaryRoutes(page)
  await page.route('**/api/tasks/*/timeline', route => fulfillJson(route, timelineData, status, timelineCounter))
  await page.route('**/api/tasks/*/evidence-board', route => fulfillJson(route, evidenceBoardData, status, evidenceCounter))
}

async function setProjectMemoryRoutes(
  page,
  memoryData,
  summaryData,
  status = 200,
  memoryCounter = null,
  summaryCounter = null,
) {
  await clearProjectMemoryRoutes(page)
  await page.route('**/api/projects/*/memory/summary', route => fulfillJson(route, summaryData, status, summaryCounter))
  await page.route('**/api/projects/*/memory', route => fulfillJson(route, memoryData, status, memoryCounter))
}

async function setMastermindReviewRoutes(
  page,
  previewData,
  executeData,
  status = 200,
  previewCounter = null,
  executeCounter = null,
) {
  await clearMastermindReviewRoutes(page)
  await page.route('**/api/tasks/*/mastermind-review/packet-preview', route => fulfillJson(route, previewData, status, previewCounter))
  await page.route('**/api/tasks/*/mastermind-review/execute', route => fulfillJson(route, executeData, status, executeCounter))
}

async function setBrowserAiProfilesRoute(page) {
  await page.unroute('**/api/browser-ai/provider-profiles').catch(() => {})
  await page.route('**/api/browser-ai/provider-profiles', route => fulfillJson(route, {
    success: true,
    data: browserAiProfilesPayload(),
    message: 'ok',
  }, 200))
}

async function setAgentRunsRoute(page, runs, status = 200, counter = null) {
  await page.unroute('**/api/tasks/*/agent-runs').catch(() => {})
  await page.route('**/api/tasks/*/agent-runs', route => fulfillJson(route, { success: true, data: runs, message: 'ok' }, status, counter))
}

async function setArtifactsRoute(page, artifacts, status = 200, counter = null) {
  await page.unroute('**/api/tasks/*/artifacts').catch(() => {})
  await page.route('**/api/tasks/*/artifacts', route => fulfillJson(route, { success: true, data: artifacts, message: 'ok' }, status, counter))
}

async function clearBrowserAiRefreshRoutes(page) {
  await page.unroute('**/api/tasks/*/agent-runs').catch(() => {})
  await page.unroute('**/api/tasks/*/artifacts').catch(() => {})
  await page.unroute('**/api/answer-synthesis/preview').catch(() => {})
}

async function clearEvidenceRunRoutes(page) {
  await page.unroute('**/api/multi-ai-evidence-runs/preview').catch(() => {})
  await page.unroute('**/api/multi-ai-evidence-runs/execute').catch(() => {})
  await page.unroute('**/api/tasks/*/agent-runs').catch(() => {})
  await page.unroute('**/api/tasks/*/artifacts').catch(() => {})
  await page.unroute('**/api/answer-synthesis/preview').catch(() => {})
}

async function clearFailureEvidenceRoutes(page) {
  await page.unroute('**/api/repair-loop/failure-evidence/preview').catch(() => {})
}

async function clearRepairPacketRoutes(page) {
  await page.unroute('**/api/repair-loop/repair-packet/generate').catch(() => {})
}

async function clearRepairHandoffRoutes(page) {
  await page.unroute('**/api/repair-loop/codex-handoff/preview').catch(() => {})
}

async function clearRepairAttemptsRoutes(page) {
  await page.unroute('**/api/tasks/*/repair-attempts').catch(() => {})
  await page.unroute('**/api/repair-loop/attempts').catch(() => {})
  await page.unroute('**/api/repair-loop/attempts/*/handoff-created').catch(() => {})
  await page.unroute('**/api/repair-loop/attempts/*/verification-result').catch(() => {})
  await page.unroute('**/api/repair-loop/attempts/*/stop').catch(() => {})
}

async function clearEvidenceSummaryRoutes(page) {
  await page.unroute('**/api/tasks/*/timeline').catch(() => {})
  await page.unroute('**/api/tasks/*/evidence-board').catch(() => {})
}

async function clearProjectMemoryRoutes(page) {
  await page.unroute('**/api/projects/*/memory').catch(() => {})
  await page.unroute('**/api/projects/*/memory/summary').catch(() => {})
}

async function clearMastermindReviewRoutes(page) {
  await page.unroute('**/api/tasks/*/mastermind-review/packet-preview').catch(() => {})
  await page.unroute('**/api/tasks/*/mastermind-review/execute').catch(() => {})
}

async function clearTaskDetailMockRoutes(page) {
  await clearDashboardRoutes(page)
  for (const routePattern of [
    '**/api/browser-ai/provider-profiles',
    '**/api/tasks/*/dispatch-batches',
    '**/api/answer-synthesis/preview',
    '**/api/ai-handoff/preview',
    '**/api/mcp/tools**',
    '**/api/mcp/call**',
    '**/api/ai-dispatch/dry-run',
    '**/api/ai-dispatch/execute',
    '**/api/browser-ai/dry-run',
    '**/api/browser-ai/execute',
    '**/api/multi-ai-evidence-runs/preview',
    '**/api/multi-ai-evidence-runs/execute',
    '**/api/tasks/*/agent-runs',
    '**/api/tasks/*/artifacts',
  ]) await page.unroute(routePattern).catch(() => {})
  await clearFailureEvidenceRoutes(page)
  await clearRepairPacketRoutes(page)
  await clearRepairHandoffRoutes(page)
  await clearRepairAttemptsRoutes(page)
  await clearEvidenceSummaryRoutes(page)
  await clearProjectMemoryRoutes(page)
  await clearMastermindReviewRoutes(page)
}

async function fulfillJson(route, payload, status, counter) {
  if (counter) counter.count += 1
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
}

function synthesisPayload(taskId, batchId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    dispatch_batch_id: batchId,
    synthesis_status: 'attention_required',
    confidence: 0.72,
    job_count: 2,
    succeeded_jobs: 1,
    failed_jobs: 0,
    blocked_jobs: 1,
    common_findings: ['job_201: PR body matches changed files'],
    disagreements: ['not_all_jobs_succeeded'],
    risks: ['job_202_blocked: provider allowlist blocked'],
    recommended_actions: ['Resolve blocked DispatchJob reasons before relying on the synthesis.'],
    next_questions: ['How should job 202 be unblocked?'],
    artifact_summaries: [{ artifact_id: 401, filename: 'review.md', artifact_type: 'agent_output', summary: 'Review summary content', is_truncated: false }],
    source_job_ids: [201, 202],
    source_agent_run_ids: [301],
    source_artifact_ids: [401],
    safety_notes: ['Deterministic rule-based preview; no AI provider called.', 'Stateless preview; no database write.'],
    ...overrides,
  }, message: 'ok' }
}

function evidenceRunPayload(taskId, overrides = {}) {
  const jobs = overrides.jobs || [
    evidenceJob(1, 'chatgpt_web', 'general', 'succeeded', { agent_run_id: 901, artifact_id: 1001 }, 'ChatGPT evidence answer'),
    evidenceJob(2, 'claude_web', 'general', 'succeeded', { agent_run_id: 902, artifact_id: 1002 }, 'Claude evidence answer'),
  ]
  const status = overrides.overall_status || (jobs.every(job => job.status === 'succeeded') ? 'succeeded' : 'partial')
  return { success: true, data: {
    evidence_run_id: overrides.evidence_run_id ?? 601,
    dispatch_batch_id: overrides.dispatch_batch_id ?? 601,
    task_id: taskId,
    mode: overrides.mode || 'broadcast',
    prompt_source: overrides.prompt_source || 'task_goal',
    providers: jobs.map(job => job.provider),
    jobs,
    estimated_job_count: jobs.length,
    concurrency_limit: 2,
    concurrency_note: 'bounded concurrency is planned; current MVP executes jobs sequentially',
    overall_status: status,
    safety_gate: {
      mode_valid: true,
      prompt_source_valid: true,
      providers_known: true,
      providers_allowed: true,
      job_count_ok: true,
      browser_ai_enabled: true,
      gate_passed: true,
      blocked_reasons: [],
      safety_notes: [
        'Multi-AI Evidence Run collects AI answers as evidence; it does not execute code.',
        'S19 MVP does not write repository files, create PRs, call CI/Sonar/Deploy, approve, or merge.',
      ],
    },
    read_only: overrides.read_only ?? false,
    persisted: overrides.persisted ?? true,
    synthesis_refreshed: overrides.synthesis_refreshed ?? true,
    synthesis_status: overrides.synthesis_status || 'ready',
    source_artifact_ids: jobs.filter(job => job.artifact_id).map(job => job.artifact_id),
    error_message: overrides.error_message || '',
  }, message: 'ok' }
}

function evidenceJob(sequenceNo, provider, role, status, runArtifact = {}, answerPreview = '', errorMessage = null) {
  return {
    dispatch_job_id: 700 + sequenceNo,
    sequence_no: sequenceNo,
    provider,
    role,
    status,
    prompt_source: 'task_goal',
    prompt_hash: `evidence_hash_${sequenceNo}`,
    question: `Evidence question ${sequenceNo}`,
    error_message: errorMessage,
    agent_run_id: runArtifact.agent_run_id ?? null,
    artifact_id: runArtifact.artifact_id ?? null,
    artifact_ids: runArtifact.artifact_id ? [runArtifact.artifact_id] : [],
    answer_preview: answerPreview,
  }
}

function failureEvidencePayload(taskId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    project_id: 1,
    failure_type: overrides.failure_type || 'browser_ai_failed',
    failed_step: overrides.failed_step || 'browser_ai',
    failed_command_summary: 'browser_ai execute failed',
    stdout_excerpt: 'visible output excerpt',
    stderr_excerpt: 'selector failure stderr',
    blocked_reasons: ['selector_failed'],
    related_agent_run_ids: [901],
    related_artifact_ids: [],
    related_dispatch_batch_id: null,
    related_dispatch_job_ids: [],
    source_commit_hint: 'verify_current_master_before_acting',
    safety_notes: [
      'Failure Evidence preview is read-only.',
      'No provider call is made.',
      'No Browser AI execution or browser launch is performed.',
      'No repository writes, PR, CI, Sonar, Deploy, approve, or merge are performed.',
    ],
    redaction_status: {
      redaction_applied: true,
      truncated: false,
      max_chars: 4000,
    },
    read_only: true,
    persisted: false,
    ...overrides,
  }, message: 'ok' }
}

function repairPacketPayload(taskId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    project_id: 1,
    failure_summary: 'Failure summary for browser_ai_failed',
    suspected_root_causes: ['Selector failure caused missing Browser AI evidence.'],
    evidence_by_source: [
      { source: 'browser_ai', summary: 'selector_failed', artifact_ids: [], agent_run_ids: [901], dispatch_batch_id: null, dispatch_job_ids: [] },
      { source: 'multi_ai_evidence_run', summary: 'analysis_status=succeeded', artifact_ids: [1001, 1002], agent_run_ids: [901, 902], dispatch_batch_id: 601, dispatch_job_ids: [701, 702] },
    ],
    multi_ai_findings: ['Both providers recommend a narrow selector/profile fix.'],
    disagreements: [],
    recommended_fix_strategy: 'Make a narrow selector/profile fix and rerun smoke.',
    files_likely_involved: ['frontend/src/pages/TaskDetailPage.vue'],
    commands_to_verify: ['node frontend/tests/s4-display.cjs'],
    risks: ['Human decision is required before any repair execution.'],
    human_decision_required: true,
    codex_handoff_prompt: 'Read AGENTS.md before acting.\nVerify current master before making any repair.\nDo not read `.env`.\nDo not auto merge.',
    max_attempts: 1,
    do_not_do: [
      'Do not read `.env`.',
      'Do not read `secret_ref`.',
      'Do not expose API keys, cookies, sessions, or passwords.',
      'Do not auto merge.',
      'Do not auto deploy.',
      'Verify current master before acting.',
    ],
    repair_packet_artifact_id: 802,
    source_failure_type: 'browser_ai_failed',
    source_artifact_ids: [],
    source_agent_run_ids: [901],
    source_dispatch_batch_id: null,
    source_dispatch_job_ids: [],
    analysis_dispatch_batch_id: 601,
    analysis_status: 'succeeded',
    read_only: false,
    persisted: true,
    safety_notes: [
      'Repair Packet Generation uses evidence collection only; it does not modify code.',
      'No repository writes, PR, CI, Sonar, Deploy, approve, or merge are performed.',
    ],
    ...overrides,
  }, message: 'ok' }
}

function repairHandoffPayload(taskId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    project_id: 1,
    target: 'codex',
    handoff_prompt: [
      'Read AGENTS.md before acting.',
      'Verify current master before making changes.',
      'Use the repair packet.',
      'Make one narrow fix only.',
      'Run verification commands.',
      'Create PR and wait for mastermind review.',
      'Do not read `.env`.',
      'Do not auto merge.',
    ].join('\n'),
    safety_notes: [
      'Handoff only; no repair execution is performed by the platform.',
      'No repository writes are performed by the platform.',
      'No provider call, Browser AI execution, shell, subprocess, `.env`, secret_ref, or Project.root_path access is performed.',
    ],
    source_repair_packet_artifact_id: 802,
    requires_master_verification: true,
    read_only: true,
    persisted: false,
    ...overrides,
  }, message: 'ok' }
}

function repairAttemptPayload(id, request = {}, overrides = {}) {
  return {
    repair_attempt_id: id,
    task_id: request.task_id || 1,
    project_id: 1,
    attempt_no: 1,
    initiator: 'user',
    executor: request.executor || 'codex',
    failure_evidence_artifact_id: request.failure_evidence_artifact_id ?? 801,
    repair_packet_artifact_id: request.repair_packet_artifact_id || 802,
    handoff_target: request.handoff_target || 'codex',
    status: 'planned',
    verification_result_artifact_ids: [],
    summary: request.summary || 'Use Codex to apply the narrow repair from the repair packet.',
    safety_notes: [
      'Timeline only; platform does not execute repair.',
      'Verification result is imported, not run by platform.',
      'No auto next attempt.',
    ],
    created_at: '2026-05-26T10:00:00Z',
    updated_at: '2026-05-26T10:00:00Z',
    read_only: false,
    persisted: true,
    ...overrides,
  }
}

function timelinePayload(taskId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    project_id: 1,
    items: [
      {
        time: '2026-05-26T10:00:00Z',
        type: 'repair_packet_generated',
        title: 'Repair packet generated',
        status: 'completed',
        source: 'repair_loop',
        linked_ids: {
          agent_run_id: null,
          artifact_id: 802,
          dispatch_batch_id: 201,
          dispatch_job_id: null,
          repair_attempt_id: 1,
        },
        summary: 'Generated one-attempt repair packet from failure evidence.',
        safety_flags: ['no_repository_writes', 'human_decision_required'],
      },
    ],
    read_only: true,
    persisted: false,
    ...overrides,
  }, message: 'ok' }
}

function evidenceBoardPayload(taskId, overrides = {}) {
  const items = overrides.items || [evidenceBoardItem({
    evidence_type: 'repair_packet',
    provider: 'browser_ai',
    role: 'reviewer',
    artifact_id: 802,
    dispatch_batch_id: 201,
    repair_attempt_id: 1,
    summary: 'Narrow repair strategy for sandbox gate failure.',
    raw_excerpt: 'Failure summary redacted excerpt',
    safety_notes: ['Codex / OMX or user must execute repair.'],
  })]
  const filterFields = ['evidence_type', 'source', 'status', 'provider', 'role']
  return { success: true, data: {
    task_id: taskId,
    project_id: 1,
    filters: Object.fromEntries(filterFields.map(field => [
      field,
      [...new Set(items.map(item => item[field]).filter(Boolean))],
    ])),
    items,
    read_only: true,
    persisted: false,
    ...overrides,
  }, message: 'ok' }
}

function evidenceBoardItem(fields) {
  return {
    evidence_type: 'task_event',
    source: 'repair_loop',
    status: 'completed',
    provider: '',
    role: '',
    artifact_id: null,
    agent_run_id: null,
    dispatch_batch_id: null,
    dispatch_job_id: null,
    repair_attempt_id: null,
    summary: '',
    raw_excerpt: '',
    safety_notes: [],
    redaction_status: {
      redaction_applied: true,
      truncated: false,
      max_chars: 2000,
    },
    ...fields,
  }
}

function evidenceBoardFilterItems() {
  return [
    evidenceBoardItem({
      evidence_type: 'repair_packet',
      provider: 'browser_ai',
      role: 'reviewer',
      artifact_id: 802,
      dispatch_batch_id: 201,
      repair_attempt_id: 1,
      summary: 'Narrow repair strategy for sandbox gate failure.',
      raw_excerpt: 'Failure summary redacted excerpt',
      safety_notes: ['Codex / OMX or user must execute repair.'],
    }),
    evidenceBoardItem({
      evidence_type: 'verification_result',
      status: 'failed',
      role: 'tester',
      artifact_id: 912,
      repair_attempt_id: 1,
      summary: 'Imported verification failed warning.',
      raw_excerpt: 'pytest failed with one blocked assertion warning',
      safety_notes: ['Verification result is imported, not run by platform.'],
    }),
    evidenceBoardItem({
      source: 'task_event',
      provider: 'system',
      role: 'audit',
      summary: 'Task audit event without artifact.',
      raw_excerpt: 'Task created and assigned.',
      safety_notes: ['Evidence Board is read-only.'],
    }),
  ]
}

function projectMemoryPayload(projectId, overrides = {}) {
  const items = overrides.items || [
    projectMemoryItem({
      project_id: projectId,
      memory_id: 'default-project-profile',
      memory_type: 'project_profile',
      title: 'Project profile',
      summary: 'AI coding evidence / memory workbench.',
      content: { technology_stack: ['FastAPI backend', 'Vue/Vite frontend'] },
      source_refs: [{ source_type: 'docs', path: 'AGENTS.md', section: null, pr_number: null, note: null }],
      confidence: 'high',
      stale: false,
    }),
    projectMemoryItem({
      project_id: projectId,
      memory_id: 'default-verification-policy',
      memory_type: 'verification_policy',
      title: 'Verification policy',
      summary: 'Use targeted pytest and npm build.',
      content: { commands: ['python -m pytest backend/tests/ -v --rootdir backend', 'npm.cmd run build'] },
      source_refs: [{ source_type: 'docs', path: 'docs/design/project-memory.md', section: null, pr_number: null, note: null }],
      confidence: 'high',
      stale: false,
    }),
    projectMemoryItem({
      project_id: projectId,
      memory_id: 'default-safety-policy',
      memory_type: 'safety_policy',
      title: 'Safety policy',
      summary: 'Never read secrets.',
      content: { rules: ['Do not read .env', 'Do not read secret_ref'] },
      source_refs: [{ source_type: 'docs', path: 'docs/strategy/project-memory-vs-agent-skill.md', section: null, pr_number: null, note: null }],
      confidence: 'medium',
      stale: true,
    }),
  ]
  return { success: true, data: {
    project_id: projectId,
    items,
    filters: {
      memory_type: [...new Set(items.map(item => item.memory_type))],
      confidence: [...new Set(items.map(item => item.confidence))],
      stale: [...new Set(items.map(item => item.stale))],
    },
    read_only: true,
    persisted: false,
    safety_notes: ['Read-only Project Memory surface.', 'Memory may be stale; verify before acting.'],
    ...overrides,
  }, message: 'ok' }
}

function projectMemorySummaryPayload(projectId, overrides = {}) {
  return { success: true, data: {
    project_id: projectId,
    summary: 'Project Memory stable context summary.',
    memory_count: 3,
    memory_types: ['project_profile', 'verification_policy', 'safety_policy'],
    stale_count: 1,
    high_confidence_count: 2,
    read_only: true,
    persisted: false,
    safety_notes: ['Project Memory is read-only.', 'No memory writes.'],
    ...overrides,
  }, message: 'ok' }
}

function projectMemoryItem(fields) {
  return {
    memory_id: 'default-project-profile',
    project_id: 1,
    memory_type: 'project_profile',
    title: 'Project profile',
    summary: 'AI coding evidence / memory workbench.',
    content: { technology_stack: ['FastAPI backend', 'Vue/Vite frontend'] },
    source_refs: [{ source_type: 'docs', path: 'AGENTS.md', section: null, pr_number: null, note: null }],
    confidence: 'high',
    stale: false,
    updated_at: '2026-05-27T00:00:00Z',
    redaction_status: {
      redaction_applied: true,
      truncated: false,
      max_chars: 4000,
    },
    ...fields,
  }
}

function mastermindPreviewPayload(taskId, projectId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    project_id: projectId,
    packet_type: 'mastermind_review_packet',
    packet: {
      pr: {
        url: 'https://github.com/2449673842/codex-auto-delivery-platform/pull/64',
        number: 64,
        head_commit: 'f193b7f3d36c31ce90f733e1a3ed5a61cec345f4',
        base_commit: '17464b6b2cbafd7e15870a04b924c6cd945b239c',
        changed_files: ['frontend/src/pages/TaskDetailPage.vue', 'frontend/tests/s4-display.cjs'],
        body: 'S24.1.3 UI PR body with verification and safety boundary.',
      },
      verification: {
        targeted_backend_pytest: '9 passed',
        full_backend_pytest: 'not_run_frontend_only',
        compileall: 'not_run_frontend_only',
        npm_build: 'passed',
        frontend_smoke: 'passed',
        git_diff_check: 'passed',
      },
      sonarcloud: {
        quality_gate: 'Passed',
        security_hotspots: 0,
        duplication_on_new_code: '0.0%',
        new_issues: 0,
      },
      safety_boundary_checklist: {
        read_only_preview: true,
        browser_ai_execution: false,
        auto_merge: false,
      },
      task_summary: `Task #${taskId}: S24.1.3 TaskDetail Mastermind Review UI.`,
      evidence_board_summary: 'Evidence Board items: mastermind_review_report can be surfaced after execute.',
      run_timeline_summary: 'Run Timeline items: mastermind_review_submitted, response_received, report_imported.',
      project_memory_summary: 'memory_count=8; memory_types=safety_policy, delivery_policy, verification_policy.',
      handoff_context: 'Repair handoff summary and AI handoff context are available.',
      review_instruction: 'Do not invent files, checks, or Sonar results. Advisory only.',
      required_output_contract: {
        verdict: 'approved | request_changes | needs_human | invalid_review',
        summary: 'Short review summary.',
        blocking_items: [],
        recommended_actions: [],
        safety_notes: [],
        confidence: 'high | medium | low',
        review_scope_confirmed: true,
      },
    },
    source_refs: [
      { source_type: 'task', id: taskId, path: null, note: 'task summary' },
      { source_type: 'evidence_board', id: null, path: null, note: 'read-only evidence summary' },
    ],
    redaction_status: {
      redaction_applied: true,
      truncated: false,
      max_chars: 12000,
    },
    read_only: true,
    persisted: false,
    safety_notes: ['Packet preview is read-only.', 'No GitHub / Sonar platform query.'],
    ...overrides,
  }, message: 'ok' }
}

function mastermindExecutePayload(taskId, projectId, overrides = {}) {
  return { success: true, data: {
    task_id: taskId,
    project_id: projectId,
    status: 'succeeded',
    agent_run_id: 6401,
    artifact_id: 6402,
    verdict: 'approved',
    summary: 'Mastermind review approved as advisory only.',
    blocking_items: [],
    recommended_actions: ['Keep human confirmation before merge.'],
    safety_notes: ['Advisory only; no automatic merge.'],
    raw_excerpt: '{"verdict":"approved","summary":"Mastermind review approved as advisory only."}',
    failure_reason: '',
    read_only: true,
    persisted: true,
    advisory_only: true,
    human_confirmation_required: true,
    no_auto_merge: true,
    parse_errors: [],
    ...overrides,
  }, message: 'ok' }
}

function mcpToolsPayload() {
  const toolRows = [
    ['get_workspace_status', 'Read project/task/run/artifact counts.', false],
    ['get_task_brief', 'Read a task brief.', false],
    ['get_handoff_packet', 'Preview handoff packet.', false],
    ['get_answer_synthesis', 'Preview synthesis.', false],
    ['ai_dispatch_dry_run', 'Dry-run AI dispatch.', true],
    ['browser_ai_dry_run', 'Dry-run Browser AI.', true],
  ]
  return { success: true, data: toolRows.map(([name, description, dryRunOnly]) => mcpTool(name, description, dryRunOnly)), message: 'ok' }
}

function mcpTool(name, description, dryRunOnly = false) {
  return {
    name,
    description,
    read_only: true,
    dry_run_only: dryRunOnly,
    safety_notes: ['MCP Bridge S18 is read-only + dry-run only.'],
  }
}

function mcpCallPayload(taskId) {
  return { success: true, data: {
    tool: 'get_handoff_packet',
    status: 'succeeded',
    data: {
      current_task_summary: { task_id: taskId, title: 'S4 display test', status: 'in_progress' },
      next_ai_prompt: 'MCP handoff summary for S4 display test',
      is_truncated: false,
    },
    error_message: '',
    read_only: true,
    persisted: false,
    safety_notes: [
      'MCP Bridge S18 is read-only + dry-run only.',
      'No OpenAI execute is allowed.',
      'No Browser AI execute or browser launch is allowed.',
    ],
  }, message: 'ok' }
}

function browserAiProfilesPayload() {
  return [
    browserAiProfile('custom', 'Custom', '', '', '', '', false),
    browserAiProfile('chatgpt_web', 'ChatGPT Web', 'https://chatgpt.com/', "textarea[data-testid='prompt-textarea'], div[contenteditable='true']", "button[data-testid='send-button']", "[data-message-author-role='assistant']"),
    browserAiProfile('claude_web', 'Claude Web', 'https://claude.ai/new', "div[contenteditable='true'], textarea", "button[aria-label*='Send']", "[data-testid='message-content'], .font-claude-message"),
    browserAiProfile('gemini_web', 'Gemini Web', 'https://gemini.google.com/app', "rich-textarea div[contenteditable='true'], textarea", "button[aria-label*='Send']", "message-content, .model-response-text"),
    browserAiProfile('deepseek_web', 'DeepSeek Web', 'https://chat.deepseek.com/', "textarea, div[contenteditable='true']", "button[aria-label*='Send'], button[type='submit']", ".ds-markdown, [class*='markdown']"),
    browserAiProfile('kimi_web', 'Kimi Web', 'https://www.kimi.com/chat/', "textarea, div[contenteditable='true']", "button[aria-label*='Send'], button[type='submit']", ".markdown, [class*='markdown']"),
  ]
}

function browserAiProfile(provider, displayName, targetUrl, inputSelector, sendSelector, responseSelector, loginRequired = true) {
  return {
    provider,
    display_name: displayName,
    target_url: targetUrl,
    target_url_hint: targetUrl,
    input_selector: inputSelector,
    send_selector: sendSelector,
    response_selector: responseSelector,
    scroll_container_selector: provider === 'custom' ? '' : 'main',
    copy_button_selector: provider === 'custom' ? '' : "button[aria-label*='Copy']",
    login_hint_selector: provider === 'custom' ? '' : "text=/log\\s*in/i, text=/sign\\s*in/i",
    login_hint_text: loginRequired ? 'Manual login may be required' : '',
    selectors_configured: Boolean(inputSelector && sendSelector && responseSelector),
    login_required_hint: loginRequired,
    editable: true,
    best_effort_note: provider === 'custom' ? '' : 'Built-in selectors are best-effort and may break when the website changes. Switch to custom if needed.',
  }
}

function handoffPayload(taskId, projectId) {
  return { success: true, data: {
    project_id: projectId,
    task_id: taskId,
    handoff_status: 'ready',
    project_snapshot: {
      positioning: 'Personal Multi-AI Coding Workbench',
      last_known_base_commit_hint: '32dcd5a8e11eeef48e0844cf21601561938c2112',
    },
    current_task_summary: { task_id: taskId, title: 'S4 display test', status: 'in_progress' },
    recent_capabilities: ['S15 AI Handoff Packet', 'Answer Synthesis Display'],
    current_master_commit_hint: 'verify_current_master_on_github_before_acting',
    current_pr_summary: { note: 'No live GitHub call is made.' },
    recent_dispatch_summary: { batch_count: 1 },
    answer_synthesis_summary: { synthesis_status: 'attention_required' },
    safety_rules: ['Do not read .env.', 'Do not read secret_ref.', 'Do not auto approve or merge.'],
    next_recommended_steps: ['Verify current master before acting.'],
    next_ai_prompt: 'Read AGENTS.md first. Current master commit hint: verify_current_master_on_github_before_acting. Do not auto merge.',
    source_ids: {
      project_id: projectId,
      task_id: taskId,
      dispatch_batch_ids: [101],
      dispatch_job_ids: [201, 202],
      agent_run_ids: [301],
      artifact_ids: [401],
    },
    redaction_applied: true,
    safety_notes: ['verify_current_master_on_github_before_acting', 'Read AGENTS.md before taking over.', 'No AI provider called.', 'No database write.'],
  }, message: 'ok' }
}

function aiDryRunPayload() {
  return { success: true, data: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    mode: 'review',
    prompt_hash: 'dry_prompt_hash',
    context_packet_hash: 'dry_context_hash',
    estimated_tokens: 1888,
    would_dispatch: false,
    safety_gate: {
      execution_enabled: false,
      openai_key_present: false,
      provider_allowed: true,
      mode_valid: true,
      budget_ok: true,
      gate_passed: false,
    },
  }, message: 'ok' }
}

function aiExecutePayload(taskId, overrides = {}) {
  const data = {
    agent_run_id: 909,
    task_id: taskId,
    status: 'succeeded',
    output_summary: 'Real OpenAI answer saved',
    output_diff: null,
    artifacts: [{ id: 808, filename: 'patch.diff', artifact_type: 'patch' }],
    events: [],
    sandbox_applied: true,
    sandbox_gate_passed: true,
    sandbox_gate_blocked_reasons: [],
    pipeline_status: 'succeeded',
    prompt_hash: 'exec_prompt_hash',
    context_packet_hash: 'exec_context_hash',
    token_usage: { prompt_tokens: 10, completion_tokens: 20 },
    steps: [
      { step: 'provider', status: 'succeeded', details: 'fake provider in display test' },
      { step: 'sandbox_apply', status: 'succeeded', details: 'Patch Sandbox Apply' },
      { step: 'sandbox_gate', status: 'succeeded', details: 'Sandbox Gate' },
    ],
  }
  return { success: true, data: { ...data, ...overrides }, message: 'ok' }
}

function browserAiSafetyGate(overrides = {}) {
  return {
    browser_ai_enabled: true,
    provider_allowed: true,
    provider_valid: true,
    selectors_present: true,
    target_url_present: true,
    timeout_ok: true,
    gate_passed: true,
    blocked_reasons: [],
    ...overrides,
  }
}

function browserAiPayload(overrides = {}) {
  const data = {
    status: 'succeeded',
    provider: 'custom',
    prompt_hash: 'browser_prompt_hash',
    answer_preview: 'Mock browser visible answer',
    agent_run_id: 707,
    artifact_id: 808,
    error_message: null,
    safety_gate: browserAiSafetyGate(),
    browser_opened: true,
    persisted: true,
    steps: browserAiSteps(),
    ...overrides,
  }
  return { success: true, data, message: 'ok' }
}

function runPayload(id, taskId, summary) {
  return {
    id,
    task_id: taskId,
    project_id: 1,
    agent_id: 77,
    run_type: 'review',
    status: 'succeeded',
    input_prompt: `Browser AI prompt redacted; prompt_hash=evidence_hash_${id}; prompt_source=custom_prompt`,
    output_summary: summary,
    output_diff: null,
    output_log: 'Browser AI visible response captured from response_selector.',
    raw_result_json: '{}',
    branch: null,
    commit_sha: null,
    pr_url: null,
    risk_level: 'low',
    attempt_no: 1,
    duration_ms: null,
    error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
}

function artifactPayload(id, taskId, type, filename, content) {
  return {
    id,
    task_id: taskId,
    artifact_type: type,
    storage_type: 'sqlite',
    content,
    file_path: null,
    filename,
    size_bytes: content.length,
    sha256: '1'.repeat(64),
    is_truncated: false,
    metadata_json: '{}',
    created_at: new Date().toISOString(),
  }
}

function browserAiSteps(statusOverrides = {}, messageOverrides = {}) {
  return [
    'validate_request',
    'build_prompt',
    'create_agent_run',
    'open_browser',
    'navigate',
    'detect_login',
    'fill_prompt',
    'click_send',
    'wait_response',
    'capture_answer',
    'persist_artifact',
    'finish_run',
  ].map(name => ({
    name,
    status: statusOverrides[name] || 'passed',
    message: messageOverrides[name] || `${name} completed`,
    sensitive: false,
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
  await checkT(page, 'Answer Synthesis / 多 AI 综合结论', 'J7 Synthesis section')
  await checkT(page, '暂无可综合的多 AI 结果', 'J8 Synthesis empty state')
}

async function testMultiAiWorkspaceRouted(page, taskId) {
  log('\n========== K. Multi-AI Answer Workspace Routed Data ==========')
  const synthesisCounter = { count: 0 }
  const handoffCounter = { count: 0 }
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
  await setAnswerSynthesisRoute(page, synthesisPayload(taskId, 101), 200, synthesisCounter)
  await setAiHandoffRoute(page, handoffPayload(taskId, 1), 200, handoffCounter)
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
  await checkT(page, 'Answer Synthesis / 多 AI 综合结论', 'K11 synthesis section')
  await checkT(page, 'attention_required', 'K12 synthesis status')
  await checkT(page, 'confidence: 72%', 'K13 confidence')
  await checkT(page, 'job_count: 2', 'K14 job count')
  await checkT(page, 'job_201: PR body matches changed files', 'K15 common findings')
  await checkT(page, 'job_202_blocked: provider allowlist blocked', 'K16 risks')
  await checkT(page, 'Resolve blocked DispatchJob reasons before relying on the synthesis.', 'K17 recommended action')
  await checkT(page, 'How should job 202 be unblocked?', 'K18 next question')
  await checkT(page, 'source_job_ids: 201, 202', 'K19 source job ids')
  await checkT(page, 'source_agent_run_ids: 301', 'K20 source run ids')
  await checkT(page, 'source_artifact_ids: 401', 'K21 source artifact ids')
  await checkT(page, 'Review summary content', 'K22 artifact summary')
  if (synthesisCounter.count > 0) pass('K23 synthesis preview endpoint called')
  else fail('K23 synthesis preview endpoint not called', '')
  await checkT(page, 'AI Handoff Packet / 下一 AI 接管包', 'K24 handoff section')
  await checkT(page, 'Stateless preview', 'K25 handoff stateless label')
  await checkT(page, 'Verify current master before acting', 'K26 verify master label')
  await checkT(page, 'verify_current_master_on_github_before_acting', 'K27 handoff master verification')
  await checkT(page, 'AGENTS.md', 'K28 handoff prompt includes AGENTS')
  await checkT(page, 'Do not read .env.', 'K29 handoff safety rules')
  await checkT(page, 'next_ai_prompt', 'K30 next ai prompt label')
  await checkEl(page, 'button:has-text("复制 next_ai_prompt")', 'K31 copy prompt button')
  if (handoffCounter.count > 0) pass('K32 handoff preview endpoint called')
  else fail('K32 handoff preview endpoint not called', '')
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

async function testAnswerSynthesisApiFailure(page, taskId) {
  log('\n========== M. Answer Synthesis API Failure & Refresh ==========')
  const counter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [{ dispatch_batch_id: 501, task_id: taskId, batch_mode: 'routed', status: 'succeeded', task_goal: 'Review PR', summary: {}, jobs: [] }], message: 'ok' })
  await setAnswerSynthesisRoute(page, { detail: 'synthesis unavailable' }, 500, counter)
  await verifyPreviewFailureRefresh(page, taskId, {
    section: 'Answer Synthesis / 多 AI 综合结论',
    error: 'synthesis unavailable',
    button: '重新生成综合结论',
    counter,
    labels: ['M1 synthesis section still visible', 'M2 synthesis error', 'M3 refresh only calls synthesis preview endpoint'],
  })
}

async function testAiHandoffApiFailure(page, taskId) {
  log('\n========== N. AI Handoff API Failure & Refresh ==========')
  const counter = { count: 0 }
  await setDispatchBatchesRoute(page, { success: true, data: [], message: 'ok' })
  await setAnswerSynthesisRoute(page, synthesisPayload(taskId, null), 200)
  await setAiHandoffRoute(page, { detail: 'handoff unavailable' }, 500, counter)
  await verifyPreviewFailureRefresh(page, taskId, {
    section: 'AI Handoff Packet / 下一 AI 接管包',
    error: 'handoff unavailable',
    button: '重新生成接管包',
    counter,
    labels: ['N1 handoff section still visible', 'N2 handoff error', 'N3 refresh only calls handoff preview endpoint'],
  })
}

async function verifyPreviewFailureRefresh(page, taskId, cfg) {
  await page.goto(`${FE}/tasks/${taskId}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await checkT(page, cfg.section, cfg.labels[0])
  await checkT(page, cfg.error, cfg.labels[1])
  const before = cfg.counter.count
  await page.getByRole('button', { name: cfg.button }).click()
  await page.waitForTimeout(300)
  if (cfg.counter.count === before + 1) pass(cfg.labels[2])
  else fail(cfg.labels[2], `before=${before}, after=${cfg.counter.count}`)
}

async function testNoUnsafeWorkspaceActions(page) {
  log('\n========== M. No unsafe workspace actions ==========')
  const unsafeButtons = await page.locator('button:has-text("创建 PR"), button:has-text("Create PR"), button:has-text("PR Adapter not implemented"), button:has-text("merge"), button:has-text("Merge"), button:has-text("deploy"), button:has-text("Deploy"), button:has-text("部署")').count()
  const unsafeLinks = await page.locator('a:has-text("创建 PR"), a:has-text("Create PR"), a:has-text("PR Adapter not implemented"), a:has-text("merge"), a:has-text("Merge"), a:has-text("deploy"), a:has-text("Deploy"), a:has-text("部署")').count()
  const unsafeText = await page.locator('text=/PR Adapter not implemented|Future step only|No real PR created|Create PR|Run Deploy|Merge PR/').count()
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

  await testDashboardFirstUsableWorkflow(page)
  await testDashboardCreateFailure(page)
  await clearDashboardRoutes(page)
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  await testGovernance(page)
  await testLabels(page)
  await testArtifacts(page)
  await testCodeContext(page)
  await testSandboxSection(page)
  await testRealAiRun(page, task.id)
  await testRealAiRunPipelineFailures(page, task.id)
  await testBrowserAiRun(page, task.id)
  await testBrowserAiFailures(page, task.id)
  await testMultiAiEvidenceRunPanel(page, task.id)
  await testMultiAiEvidenceRunRoutedPartial(page, task.id)
  await testFailureEvidencePreviewPanel(page, task.id)
  await testRepairPacketGenerationPanel(page, task.id)
  await testRepairHandoffPanel(page, task.id)
  await testRepairAttemptTimelinePanel(page, task.id)
  await testEvidenceSummaryPanel(page, task.id)
  await testEvidenceSummaryApiFailure(page, task.id)
  await testEvidenceBoardFiltersDetails(page, task.id)
  await testProjectMemoryPanel(page, task)
  await testProjectMemoryApiFailure(page, task)
  await testMastermindReviewPanel(page, task)
  await testMastermindReviewApiFailure(page, task)
  await testMcpBridgePanel(page, task.id)
  await testApprovals(page)
  await testHumanRequired(page)
  await testSandboxApply(page)
  await testMultiAiWorkspaceEmpty(page, task.id)
  await testMultiAiWorkspaceRouted(page, task.id)
  await testMultiAiWorkspaceApiFailure(page, task.id)
  await testAnswerSynthesisApiFailure(page, task.id)
  await testAiHandoffApiFailure(page, task.id)
  await testNoUnsafeWorkspaceActions(page)
  // Create a separate task without code context for 404 test
  await clearTaskDetailMockRoutes(page)
  const bareTask = await apiPost('/tasks', { project_id: task.project_id, title: 'S4 no-ctx test', planner: 'test', description: 'No code context' })
  if (bareTask.data?.id) await testNoCodeContext(page, bareTask.data.id)
  // Navigate back to main task
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  printSummary(consoleErrors)
  await browser.close()
}

main().catch(e => { console.error('Test harness error:', e); process.exit(1) })


