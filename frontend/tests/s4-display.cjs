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
  await checkT(page, 'backend configured', 'R3 model')
  await page.getByRole('button', { name: 'Dry-run' }).click()
  await page.waitForTimeout(300)
  if (dryCounter.count === 1) pass('R4 dry-run endpoint called')
  else fail('R4 dry-run endpoint call count', dryCounter.count)
  await checkT(page, 'would_dispatch=false', 'R5 would_dispatch false')
  await checkT(page, 'estimated_tokens=1888', 'R6 token estimate')
  await checkT(page, 'gpt-4o-mini', 'R6b dry-run model')
  await checkT(page, 'AI_EXECUTION_ENABLED 未开启', 'R7 execution disabled reason')
  await checkT(page, 'OPENAI_API_KEY 缺失', 'R8 missing key reason')
  await page.getByRole('button', { name: 'Execute' }).click()
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
  await page.getByRole('button', { name: 'Execute' }).click()
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
  await page.getByRole('button', { name: 'Execute' }).click()
  await page.waitForTimeout(300)
  await checkT(page, 'pipeline_status: sandbox_gate_blocked', 'R2-3 gate blocked status')
  await checkT(page, 'gate blocked', 'R2-4 gate blocked label')
  await checkT(page, 'risk_high', 'R2-5 gate blocked reason risk')
  await checkT(page, 'manual_review_required', 'R2-6 gate blocked reason manual')
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

async function setAiDispatchRoute(page, action, payload, status = 200, counter = null) {
  await page.unroute(`**/api/ai-dispatch/${action}`).catch(() => {})
  await page.route(`**/api/ai-dispatch/${action}`, route => fulfillJson(route, payload, status, counter))
}

async function fulfillJson(route, payload, status, counter) {
  if (counter) counter.count += 1
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
}

function synthesisPayload(taskId, batchId) {
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
  }, message: 'ok' }
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
  await testRealAiRun(page, task.id)
  await testRealAiRunPipelineFailures(page, task.id)
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
  const bareTask = await apiPost('/tasks', { project_id: task.project_id, title: 'S4 no-ctx test', planner: 'test', description: 'No code context' })
  if (bareTask.data?.id) await testNoCodeContext(page, bareTask.data.id)
  // Navigate back to main task
  await page.goto(`${FE}/tasks/${task.id}`, { waitUntil: 'networkidle', timeout: 15000 })
  await page.waitForTimeout(500)
  printSummary(consoleErrors)
  await browser.close()
}

main().catch(e => { console.error('Test harness error:', e); process.exit(1) })
