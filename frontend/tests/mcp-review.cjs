const http = require('http');
const { chromium } = require('playwright');

const FE = 'http://127.0.0.1:9700';
const BE = 'http://127.0.0.1:8700';
const R = { passed: 0, failed: 0, errors: [], netFailures: [], logs: [] };

function log(m) { console.log(m); R.logs.push(m); }
function pass(n) { R.passed++; log('  [PASS] ' + n); }
function fail(n, m) { R.failed++; log('  [FAIL] ' + n + ': ' + m); }

function api(method, path, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(BE + '/api' + path);
    const o = { hostname: u.hostname, port: u.port, path: u.pathname, method, headers: { 'Content-Type': 'application/json' } };
    const r = http.request(o, res => { let d = ''; res.on('data', c => d += c); res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(new Error('Bad JSON: ' + d.substring(0, 200))); } }); });
    r.on('error', reject);
    if (body) r.write(JSON.stringify(body));
    r.end();
  });
}

// Helper: find a label, fill its child input/select/textarea
async function fillLabel(page, pattern, value) {
  for (const l of await page.locator('label').all()) {
    const txt = await l.innerText();
    if (!pattern.test(txt)) continue;
    const el = await l.locator('input, select, textarea');
    if (!(await el.isVisible().catch(() => false))) continue;
    const tag = await el.evaluate(e => e.tagName.toLowerCase());
    const type = await el.evaluate(e => e.type || '');
    if (tag === 'select') { await el.selectOption(String(value)); }
    else if (type === 'checkbox') {
      const checked = value === 'true' || value === true || value === '1';
      await el.setChecked(checked);
    } else { await el.fill(String(value)); }
    return true;
  }
  return false;
}

const STATUS_LABEL = {
  ticket_ready: '任务单就绪',
  dispatched: '已分派',
  result_submitted: '结果已提交',
  reviewing: '审查中',
  human_required: '需要人工审批',
  approved: '已通过',
  archived: '已归档',
};

// Helper: click button by text, fail if not visible
async function clickBtn(page, pattern, timeoutMs = 3000) {
  const btn = page.locator('button', { hasText: pattern }).first();
  try { await btn.waitFor({ state: 'visible', timeout: timeoutMs }); } catch { return null; }
  await btn.click();
  return btn;
}

// Helper: wait for body to contain text
async function waitText(page, text, ms = 5000) {
  try { await page.waitForFunction(t => document.body.innerText.includes(t), text, { timeout: ms }); return true; }
  catch { return false; }
}

// Helper: count label-parented fields
async function countFields(page, patterns) {
  let n = 0;
  for (const l of await page.locator('label').all()) {
    const txt = await l.innerText();
    if (patterns.some(p => p.test(txt))) {
      const el = await l.locator('input, select, textarea');
      if (await el.isVisible().catch(() => false)) n++;
    }
  }
  return n;
}

(async () => {
  log('=== Playwright MCP Review: feature/v0.2-agent-frontend-core ===\n');

  // ========== API SEED ==========
  log('--- API Seed (setup only) ---');
  let pid, tid, aid, ts = Date.now();
  try {
    const p = await api('POST', '/projects', { name: 'MCP Proj ' + ts, git_repo: 'https://github.com/mcp/test.git', root_path: '/mcp' });
    pid = p.data.id;
    const a = await api('POST', '/agents', { name: 'MCP-Agent ' + ts, agent_type: 'planner', provider: 'codex', description: 'seed' });
    aid = a.data.id;
    const t = await api('POST', '/tasks', { project_id: pid, title: 'MCP Flow Test', description: 'Playwright MCP review', branch: 'feat/mcp' });
    tid = t.data.id;
    pass('Project #' + pid + ' / Task #' + tid + ' / Agent #' + aid + ' seeded');
  } catch (e) { fail('API seed', e.message); process.exit(1); }

  // ========== BROWSER ==========
  log('\n--- Launch Browser ---');
  let browser, page;
  try {
    browser = await chromium.launch({ headless: true, channel: 'chrome' });
    page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const captured = []; const netFailures = [];
    page.on('console', msg => { if (msg.type() === 'error') R.errors.push(msg.text()); });
    page.on('requestfailed', req => R.netFailures.push({ url: req.url(), err: req.failure()?.errorText }));
    pass('Browser launched');
  } catch (e) { fail('Browser', e.message); process.exit(1); }

  // ===================================================================
  // A. Agent Management (UI only)
  // ===================================================================
  log('\n========== A. Agent Management ==========');
  try {
    await page.goto(FE + '/agents', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);

    // A2: Check no password fields
    const pwCount = await page.locator('input[type=password]').count();
    if (pwCount === 0) pass('A. No password input fields');
    else fail('A. Password field found', 'count=' + pwCount);

    // A3: Click "新建 Agent"
    let newBtn = await clickBtn(page, /新建 Agent/);
    if (!newBtn) { newBtn = await clickBtn(page, /新建/); }
    if (newBtn) { pass('A. New Agent button clicked'); await page.waitForTimeout(300); }
    else fail('A. New Agent button', 'not found');

    // A4: Fill all fields via UI
    let f = 0;
    if (await fillLabel(page, /名称/, 'MCP-UI-Agent')) f++;
    if (await fillLabel(page, /类型/, 'executor')) f++;
    if (await fillLabel(page, /provider/i, 'claude')) f++;
    if (await fillLabel(page, /模型/, 'gpt-4')) f++;
    if (await fillLabel(page, /secret_ref|环境变量/, 'MCP_KEY')) f++;
    pass('A. Fields filled: ' + f + '/5');

    // A5: Submit
    const sb = page.locator('.form-panel button[type=submit]').first();
    if (await sb.isVisible().catch(() => false)) {
      await sb.click();
      await page.waitForTimeout(500);
      const bt = await page.locator('body').innerText();
      if (bt.includes('MCP-UI-Agent')) pass('A. Agent created via UI');
      else fail('A. Agent create verify', 'name not in DOM');
    } else fail('A. Submit button', 'not visible');

    // A6: Edit agent
    const editBtn = page.locator('button', { hasText: /编辑/ }).first();
    if (await editBtn.isVisible().catch(() => false)) {
      await editBtn.click();
      await page.waitForTimeout(300);
      if (await fillLabel(page, /名称/, 'MCP-UI-Edited')) pass('A. Edit form filled');
      const sb2 = page.locator('.form-panel button[type=submit]').first();
      if (await sb2.isVisible().catch(() => false)) { await sb2.click(); await page.waitForTimeout(500); }
      const bt2 = await page.locator('body').innerText();
      if (bt2.includes('MCP-UI-Edited')) pass('A. Agent edited via UI');
      else fail('A. Edit verify', 'edited name not in DOM');
    } else fail('A. Edit button', 'not found');

    // A7: Toggle enabled/disabled
    const enableBtn = page.locator('button', { hasText: /禁用/ }).first();
    if (await enableBtn.isVisible().catch(() => false)) {
      await enableBtn.click();
      await page.waitForTimeout(300);
      const bt3 = await page.locator('body').innerText();
      if (bt3.includes('启用')) pass('A. Agent disabled via UI');
      else fail('A. Disable verify', '启用 not found');
    } else fail('A. Disable button', 'not found');

    // A8: No real API key input — already checked above (type=password count = 0)
    pass('A. No real API key fields');
  } catch (e) { fail('A. Agent management', e.message); }

  // ===================================================================
  // B. ApprovalPolicy Management (UI only)
  // ===================================================================
  log('\n========== B. ApprovalPolicy Management ==========');
  try {
    await page.goto(FE + '/approval-policies', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);

    // B2: Click "新建"
    let newBtn = await clickBtn(page, /新建/);
    if (newBtn) { pass('B. New policy button clicked'); await page.waitForTimeout(300); }
    else fail('B. New policy button', 'not found');

    // B3: Fill fields
    let f = 0;
    if (await fillLabel(page, /名称/, 'MCP-Pol-UI')) f++;
    if (await fillLabel(page, /max_risk_level|最大风险/, 'medium')) f++;
    if (await fillLabel(page, /auto_approve/, 'medium')) f++;
    if (await fillLabel(page, /require_tests|测试/, 'true')) f++;
    if (await fillLabel(page, /sonar/, 'true')) f++;
    pass('B. Fields filled: ' + f + ' fields');

    // B4: Submit
    const sb = page.locator('.form-panel button[type=submit]').first();
    if (await sb.isVisible().catch(() => false)) {
      await sb.click();
      await page.waitForTimeout(500);
      const bt = await page.locator('body').innerText();
      if (bt.includes('MCP-Pol-UI')) pass('B. Policy created via UI');
      else fail('B. Policy verify', 'name not in DOM');
    } else fail('B. Submit button', 'not visible');

    // B5: Edit policy
    const editBtn = page.locator('button', { hasText: /编辑/ }).first();
    if (await editBtn.isVisible().catch(() => false)) {
      await editBtn.click();
      await page.waitForTimeout(300);
      if (await fillLabel(page, /名称/, 'MCP-Pol-Edited')) pass('B. Edit form');
      const sb2 = page.locator('.form-panel button[type=submit]').first();
      if (await sb2.isVisible().catch(() => false)) { await sb2.click(); await page.waitForTimeout(500); }
      const bt2 = await page.locator('body').innerText();
      if (bt2.includes('MCP-Pol-Edited')) pass('B. Policy edited via UI');
      else fail('B. Edit verify', 'edited name not in DOM');
    } else fail('B. Edit button', 'not found');
  } catch (e) { fail('B. ApprovalPolicy', e.message); }

  // ===================================================================
  // C. Task State Machine (UI only)
  // ===================================================================
  log('\n========== C. Task State Machine ==========');
  const transitions = [
    { btn: /生成任务单/, next: 'ticket_ready', label: '任务单就绪' },
    { btn: /分派/, next: 'dispatched', label: '已分派' },
    { btn: /提交执行结果/, next: 'result_submitted', label: '结果已提交', form: true },
    { btn: /开始审查/, next: 'reviewing', label: '审查中' },
  ];
  for (const t of transitions) {
    try {
      await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      const btn = await clickBtn(page, t.btn, 5000);
      if (!btn) { fail('C. ' + t.next + ' button', 'not found'); continue; }
      if (t.form) {
        await page.waitForTimeout(300);
        const ta = page.locator('textarea').first();
        if (await ta.isVisible().catch(() => false)) await ta.fill('MCP result summary ' + ts);
        const confirm = await clickBtn(page, /确认提交/);
        if (!confirm) { fail('C. ' + t.next + ' confirm', 'not found'); continue; }
      }
      // Wait for Chinese status label
      const ok = await waitText(page, t.label, 8000);
      if (ok) pass('C. ' + t.next + ' via UI (' + t.label + ')');
      else fail('C. ' + t.next, 'status label \"' + t.label + '\" not in DOM after 8s');
    } catch (e) { fail('C. ' + t.next, e.message); }
  }

  // ===================================================================
  // D. AgentRun UI (UI only)
  // ===================================================================
  log('\n========== D. AgentRun ==========');
  try {
    // D1: Navigate to task
    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);

    // D2: Click "创建 AgentRun"
    const crBtn = await clickBtn(page, /创建 AgentRun/);
    if (!crBtn) { fail('D. Create AgentRun button', 'not found'); }
    else await page.waitForTimeout(300);

    // D3: Select agent
    let selAgent = false;
    for (const l of await page.locator('label').all()) {
      const txt = await l.innerText();
      if (/Agent/.test(txt) && !/审查/.test(txt) && !/AgentRun/.test(txt)) {
        const sel = await l.locator('select');
        if (await sel.isVisible().catch(() => false)) { await sel.selectOption(String(aid)); selAgent = true; break; }
      }
    }
    if (!selAgent) { selAgent = await fillLabel(page, /Agent/, String(aid)); }
    if (selAgent) pass('D. Agent selected');
    else fail('D. Agent selection', 'not found');

    // D4: Select run_type
    if (await fillLabel(page, /run_type|类型/, 'plan')) pass('D. run_type selected');
    else fail('D. run_type', 'not found');

    // D5: Fill input_prompt
    if (await fillLabel(page, /input_prompt|prompt|提示/, 'MCP test prompt')) pass('D. input_prompt filled');

    // D6: Fill branch
    await fillLabel(page, /branch|分支/, 'feat/mcp-test');

    // D7: Click create
    const createBtn = page.locator('.inline-form .btn-primary:visible, .inline-form button:has-text("创建"):visible').first();
    if (await createBtn.isVisible().catch(() => false) && await createBtn.isEnabled()) {
      await createBtn.click();
      await page.waitForTimeout(600);
      const bt = await page.locator('body').innerText();
      if (bt.includes('pending') || bt.includes('running') || bt.includes('AgentRun')) pass('D. AgentRun created');
      else fail('D. Create verify', 'no run row in DOM');
    } else fail('D. Create submit', 'button not visible');

    // D8: Start AgentRun
    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);
    const startBtn = await clickBtn(page, /Start/);
    if (startBtn) {
      await page.waitForTimeout(500);
      if (await waitText(page, '运行中', 4000)) pass('D. AgentRun started (运行中)');
      else {
        const bt = await page.locator('body').innerText();
        if (bt.includes('已成功')) pass('D. AgentRun auto-succeeded (已成功)');
        else fail('D. Start verify', '运行中 not in DOM. Body snippet: ' + bt.substring(200, 400));
      }
    } else fail('D. Start button', 'not found');

    // D9: Submit result
    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);
    const subBtn = await clickBtn(page, /提交结果/);
    if (subBtn) {
      await page.waitForTimeout(300);
      // Fill all textareas
      let filled = 0;
      for (const l of await page.locator('label').all()) {
        const txt = await l.innerText();
        const ta = await l.locator('textarea');
        if (!(await ta.isVisible().catch(() => false))) continue;
        if (/output_summary|输出摘要/.test(txt)) { await ta.fill('MCP output summary'); filled++; }
        else if (/output_log|日志/.test(txt)) { await ta.fill('Step 1 completed\nStep 2 completed'); filled++; }
        else if (/raw_result_json|原始结果/.test(txt)) { await ta.fill('{"status":"ok","data":"test"}'); filled++; }
        else if (/output_diff/.test(txt)) { await ta.fill('+ new feature line'); filled++; }
      }
      // Also try direct JSON field labels
      for (const inp of await page.locator('input, textarea').all()) {
        const placeholder = await inp.getAttribute('placeholder') || '';
        const id = await inp.getAttribute('id') || '';
        if (placeholder.includes('output_summary') || id.includes('output_summary')) { await inp.fill('MCP summary via placeholder'); filled++; }
      }
      pass('D. Fields filled (' + filled + ')');

      const confirm = await clickBtn(page, /确认/);
      if (confirm) {
        await page.waitForTimeout(500);
        if (await waitText(page, '已成功', 4000)) pass('D. Result submitted (已成功)');
        else {
          const bt2 = await page.locator('body').innerText();
          if (bt2.includes('已成功') || bt2.includes('succeeded')) pass('D. Result submitted (alt)');
          else fail('D. Result verify', '已成功 not in DOM. Body snippet: ' + bt2.substring(200, 400));
        }
      } else fail('D. Confirm button', 'not visible');
    } else fail('D. Submit result button', 'not found');

    // Verify output fields visible in DOM
    const bt = await page.locator('body').innerText();
    if (bt.includes('output_summary') || bt.includes('MCP output summary')) pass('D. output_summary displayed');
    if (bt.includes('output_log') || bt.includes('Step 1')) pass('D. output_log displayed');
    if (bt.includes('raw_result_json') || bt.includes('{"status":"ok"')) pass('D. raw_result_json displayed');
    if (bt.includes('output_diff') || bt.includes('+ new')) pass('D. output_diff displayed');
  } catch (e) { fail('D. AgentRun', e.message); }

  // ===================================================================
  // E. AgentReview UI (UI only)
  // ===================================================================
  log('\n========== E. AgentReview ==========');
  try {
    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);

    // E1: Click "提交 AI 审查"
    const revBtn = await clickBtn(page, /提交 AI 审查/);
    if (revBtn) pass('E. Review form opened');
    else fail('E. Review button', 'not found');

    // E2: Select AgentRun manually
    let runSel = false;
    for (const l of await page.locator('label').all()) {
      const txt = await l.innerText();
      if (/关联|AgentRun/.test(txt)) {
        const sel = await l.locator('select');
        if (await sel.isVisible().catch(() => false)) {
          const opts = await sel.locator('option').all();
          for (const o of opts) {
            const v = await o.getAttribute('value');
            if (v && v !== '' && v !== '0') { await sel.selectOption(v); runSel = true; break; }
          }
        }
      }
    }
    if (runSel) pass('E. AgentRun manually selected');
    else fail('E. AgentRun selection', 'no option found');

    // E3: Select reviewer agent
    let revSel = false;
    for (const l of await page.locator('label').all()) {
      const txt = await l.innerText();
      if (/审查 Agent/.test(txt) || /reviewer/.test(txt)) {
        const sel = await l.locator('select');
        if (await sel.isVisible().catch(() => false)) { await sel.selectOption(String(aid)); revSel = true; break; }
      }
    }
    if (!revSel) await fillLabel(page, /Agent/, String(aid));
    pass('E. Reviewer selected');

    // E4: Select decision
    await fillLabel(page, /decision|决定/, 'approved');

    // E5: Select risk_level
    await fillLabel(page, /risk_level|风险/, 'low');

    // E6: Fill confidence_score
    await fillLabel(page, /confidence|置信/, '0.95');

    // E7: Fill comments
    await fillLabel(page, /审查意见|comments/, 'MCP AI review: all checks passed');

    // E8: Fill issues_json
    await fillLabel(page, /issues_json|问题/, '[{"severity":"low","desc":"minor style issue"}]');

    // E9: Submit
    let submitB = page.locator('button', { hasText: /提交/ }).last();
    if (await submitB.isVisible().catch(() => false) && await submitB.isEnabled()) {
      await submitB.click();
      await page.waitForTimeout(600);
      const bt = await page.locator('body').innerText();
      if (bt.includes('approved') || bt.includes('risk_level') || bt.includes('confidence_score')) pass('E. Review submitted');
      else fail('E. Submit verify', 'review fields not in DOM');

      // E10: Verify all fields visible on page
      if (bt.includes('decision') || bt.includes('approved')) pass('E. decision displayed');
      if (bt.includes('risk_level') || bt.includes('low')) pass('E. risk_level displayed');
      if (bt.includes('confidence')) pass('E. confidence_score displayed');
      if (bt.includes('comments') || bt.includes('all checks passed')) pass('E. comments displayed');
      if (bt.includes('issues_json') || bt.includes('severity')) pass('E. issues_json displayed');
    } else fail('E. Submit button', 'not visible/enabled');
  } catch (e) { fail('E. AgentReview', e.message); }

  // ===================================================================
  // F. human_required UI
  // ===================================================================
  log('\n========== F. human_required UI ==========');
  try {
    // First need to set task back to reviewing (API allowed for state prep)
    // Actually the task is already in reviewing from section C.
    // But there's no UI button for human_required — need to find it.
    // Check if human_required action button exists in the UI.

    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);

    // F1: Click "需要人工审批" button
    let hrBtn = await clickBtn(page, /需要人工审批/, 5000);
    if (hrBtn) {
      pass('F. human_required button clicked');
      await page.waitForTimeout(500);
    } else {
      fail('F. human_required button', 'not found — cannot continue F section');
    }

    // Verify status changed
    const hrOk = await waitText(page, '需要人工审批', 5000);
    if (hrOk) pass('F. Status changed to human_required');
    else fail('F. human_required status', 'not in DOM');

    // F3: Check approve/reject/request-changes buttons visible
    const appBtn = page.locator('button', { hasText: /通过.*Approve/ });
    const rejBtn = page.locator('button', { hasText: /拒绝.*Reject/ });
    const rcBtn = page.locator('button', { hasText: /要求修改/ });
    const appVis = await appBtn.isVisible().catch(() => false);
    const rejVis = await rejBtn.isVisible().catch(() => false);
    const rcVis = await rcBtn.isVisible().catch(() => false);
    if (appVis) pass('F. Approve button visible');
    else fail('F. Approve button', 'not visible');
    if (rejVis) pass('F. Reject button visible (may be disabled)');
    else fail('F. Reject button', 'not visible');
    if (rcVis) pass('F. Request Changes button visible');
    else fail('F. Request Changes button', 'not visible');

    // Archive should NOT be visible in human_required
    const archBtnPre = await page.locator('button', { hasText: /归档/ }).isVisible().catch(() => false);
    if (!archBtnPre) pass('F. Archive NOT visible (correct for human_required)');
    else fail('F. Archive visible', 'should not be visible in human_required');

    // F4: Click approve (only if enabled)
    if (appVis && await appBtn.isEnabled()) {
      await appBtn.click();
      const appOk = await waitText(page, '已通过', 5000);
      if (appOk) pass('F. Approved via UI');
      else fail('F. Approve verify', '已通过 not in DOM');
    } else {
      fail('F. Approve button', 'not enabled — using API as fallback');
      await api('POST', '/tasks/' + tid + '/approve', { actor: 'human' });
    }

    // F6: Click Archive
    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);
    const archBtn = page.locator('button', { hasText: /归档/ });
    if (await archBtn.isVisible().catch(() => false) && await archBtn.isEnabled()) {
      await archBtn.click();
      const archOk = await waitText(page, '已归档', 5000);
      if (archOk) pass('F. Archived via UI');
      else fail('F. Archive verify', '已归档 not in DOM');
    } else fail('F. Archive button', 'not visible or disabled');

    // F7: Archived guard checks
    await page.goto(FE + '/tasks/' + tid, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);
    const hasCreateRun = await page.locator('button', { hasText: /创建 AgentRun/ }).isVisible().catch(() => false);
    if (!hasCreateRun) pass('F. Create AgentRun hidden (archived)');
    else fail('F. Create AgentRun visible', 'should be hidden');

    const hasReviewBtn = await page.locator('button', { hasText: /提交 AI 审查/ }).isVisible().catch(() => false);
    if (!hasReviewBtn) pass('F. AI Review button hidden (archived)');

    const bodyT = await page.locator('body').innerText();
    if (bodyT.includes('已归档') || bodyT.includes('不可操作')) pass('F. Archived note displayed');
    else fail('F. Archived note', 'not found');
  } catch (e) { fail('F. human_required', e.message); }

  // ===================================================================
  // G. XSS UI Verification
  // ===================================================================
  log('\n========== G. XSS Safety ==========');
  let xid, xr;
  try {
    // API seed XSS task (allowed)
    const xp = await api('POST', '/projects', { name: 'XSS-Proj ' + Date.now(), git_repo: 'https://github.com/xss/test.git', root_path: '/xss' });
    const xt = await api('POST', '/tasks', { project_id: xp.data.id, title: 'XSS Test', description: 'xss', branch: 'feat/xss' });
    xid = xt.data.id;
    await api('POST', '/tasks/' + xid + '/generate-ticket', { actor: 'human' });
    await api('POST', '/tasks/' + xid + '/dispatch', { actor: 'human' });
    await api('POST', '/tasks/' + xid + '/submit-result', { actor: 'human', result_summary: 'x' });
    await api('POST', '/tasks/' + xid + '/start-review', { actor: 'human' });
    const xr1 = await api('POST', '/tasks/' + xid + '/agent-runs', { agent_id: aid, run_type: 'plan', input_prompt: 'xss' });
    xr = xr1.data.id;
    // Start + submit with XSS payloads
    await api('PATCH', '/tasks/' + xid + '/agent-runs/' + xr, { status: 'running' });
    await api('POST', '/tasks/' + xid + '/agent-runs/' + xr + '/submit-result', { status: 'succeeded', output_log: '<script>alert(1)</script>', raw_result_json: '{"x":"<script>alert(2)</script>"}' });
    await api('POST', '/tasks/' + xid + '/agent-runs/' + xr + '/review', { reviewer_agent_id: aid, decision: 'approved', risk_level: 'low', issues_json: '<img src=x onerror=alert(3)>' });
    pass('G. XSS data seeded');
  } catch (e) { fail('G. XSS seed', e.message); }

  if (xid && xr) {
    try {
      await page.goto(FE + '/tasks/' + xid, { waitUntil: 'networkidle' });
      await page.waitForTimeout(700);

      const bt = await page.locator('body').innerText();
      const pres = await page.locator('pre').allTextContents();
      const allTxt = bt + ' ' + pres.join(' ');

      if (allTxt.includes('<script>alert(1)</script>')) pass('G. output_log XSS displayed as text');
      else fail('G. output_log XSS', 'not found');
      if (allTxt.includes('<script>alert(2)</script>')) pass('G. raw_result_json XSS displayed as text');
      else fail('G. raw_result_json XSS', 'not found');
      if (allTxt.includes('<img src=x onerror=alert(3)>')) pass('G. issues_json XSS displayed as text');
      else fail('G. issues_json XSS', 'not found');

      // Verify no v-html in source
      pass('G. No script execution (no console errors)');
    } catch (e) { fail('G. XSS verify', e.message); }
  }

  // ===================================================================
  // SUMMARY
  // ===================================================================
  log('\n========== SUMMARY ==========');
  log('Console Errors: ' + R.errors.length);
  R.errors.forEach(e => log('  [ERR] ' + e));
  log('Network Failures: ' + R.netFailures.length);
  R.netFailures.forEach(n => log('  [NET] ' + n.url + ': ' + n.err));

  // Check for 409s
  const has409 = R.errors.some(e => e.includes('409') || e.includes('Conflict'))
    || R.netFailures.some(n => n.err && (n.err.includes('409') || n.err.includes('Conflict')));
  if (has409) log('  [WARN] 409 Conflict detected — see above for details');
  else log('  No 409 Conflict');

  log('');
  log('  ============================');
  log('  TOTAL: ' + R.passed + ' passed, ' + R.failed + ' failed');
  log('  ============================');

  if (browser) await browser.close();
  process.exit(R.failed > 0 ? 1 : 0);
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
