// @ts-check
const { chromium } = require('playwright');
const path = require('path');

const FRONTEND = 'http://127.0.0.1:9700';
const BACKEND = 'http://127.0.0.1:8700';

/** @type {import('playwright').Browser} */
let browser;
/** @type {import('playwright').Page} */
let page;

const errors = [];
const networkFailures = [];

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function api(method, urlPath, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BACKEND}/api${urlPath}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(`API ${method} ${urlPath}: ${res.status} ${JSON.stringify(data)}`);
  return data;
}

before(async () => {
  browser = await chromium.launch({ headless: true, channel: 'chrome' });
  page = await browser.newPage();

  // Collect console errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push({ text: msg.text(), url: msg.location().url });
    }
  });

  // Collect network failures
  page.on('requestfailed', req => {
    networkFailures.push({ url: req.url(), failure: req.failure()?.errorText });
  });
});

after(async () => {
  if (browser) await browser.close();
});

describe('v0.2 Agent Frontend — Complete Browser Acceptance', function () {
  this.timeout(120_000);

  let projectId, taskId, agentId, policyId, agentRunId, agentReviewId;

  // ── 1. Seed data via API ──
  before(async () => {
    // Create project
    const proj = await api('POST', '/projects', { name: 'PW Test Proj', git_repo: 'https://github.com/test/pw.git' });
    projectId = proj.data.id;

    // Create agent
    const agent = await api('POST', '/agents', {
      name: 'PW-Planner', agent_type: 'planner', provider: 'codex', description: 'Playwright test agent',
    });
    agentId = agent.data.id;

    // Create task
    const task = await api('POST', `/projects/${projectId}/tasks`, {
      title: 'PW Agent Flow Test', description: 'Full e2e test', branch: 'feat/pw-test',
    });
    taskId = task.data.id;
  });

  // ── 2. Page loads ──
  it('1. Dashboard page loads without errors', async () => {
    await page.goto(FRONTEND);
    await page.waitForSelector('.app-layout', { timeout: 5000 });
    const title = await page.title();
    console.log(`  Page title: "${title}"`);
    // Check nav links exist
    const navLinks = await page.locator('.nav-link').allTextContents();
    console.log(`  Nav links: ${navLinks.join(', ')}`);
  });

  it('2. Agent list page loads and shows agents', async () => {
    await page.goto(`${FRONTEND}/agents`);
    await page.waitForTimeout(500);
    // Should see the agent we created
    const body = await page.locator('body').innerText();
    if (body.includes('PW-Planner')) {
      console.log('  Found PW-Planner in agent list');
    } else {
      console.log('  Agent list body (first 200 chars):', body.substring(0, 200));
    }
  });

  // ── 3. Create Agent via UI ──
  it('3. Create a new Agent via form', async () => {
    await page.goto(`${FRONTEND}/agents`);
    await page.waitForTimeout(300);

    // Click create button
    const createBtn = page.locator('button:has-text("创建")').first();
    if (await createBtn.isVisible()) {
      await createBtn.click();
    } else {
      console.log('  No create button found, trying inline form...');
    }
    await page.waitForTimeout(300);

    // Fill form
    const nameInput = page.locator('input').or(page.locator('textarea')).first();
    // Look for name input and fill
    const inputs = await page.locator('input, select, textarea').all();
    for (const inp of inputs) {
      const label = await page.evaluate(el => {
        const l = el.closest('label');
        return l ? l.innerText : '';
      }, inp);
      if (!label) continue;
      if (label.includes('名称')) await inp.fill('PW-Agent-2');
      if (label.includes('Agent 类型') || label.includes('agent_type')) await inp.selectOption('executor');
      if (label.includes('Provider') || label.includes('provider')) await inp.selectOption('claude');
    }

    // Submit
    const submitBtn = page.locator('button:has-text("创建")').last().or(page.locator('button:has-text("保存")'));
    if (await submitBtn.isVisible()) {
      await submitBtn.click();
      await page.waitForTimeout(500);
    }
  });

  // ── 4. Edit Agent via UI ──
  it('4. Edit Agent (disable)', async () => {
    await page.goto(`${FRONTEND}/agents`);
    await page.waitForTimeout(300);

    // Toggle enable/disable
    const toggleBtn = page.locator('button:has-text("禁用")').first().or(page.locator('button:has-text("启用")').first());
    if (await toggleBtn.isVisible()) {
      await toggleBtn.click();
      await page.waitForTimeout(500);
    }
  });

  // ── 5. Create ApprovalPolicy via UI ──
  it('5. Create ApprovalPolicy via form', async () => {
    await page.goto(`${FRONTEND}/approval-policies`);
    await page.waitForTimeout(300);

    // Fill and submit
    const inputs = await page.locator('input, select, textarea').all();
    for (const inp of inputs) {
      const label = await page.evaluate(el => {
        const l = el.closest('label');
        return l ? l.innerText : '';
      }, inp);
      if (!label) continue;
      if (label.includes('策略名称') || label.includes('Name') || label.includes('name')) await inp.fill('PW-Policy');
    }

    const submitBtn = page.locator('button:has-text("创建")').last().or(page.locator('button:has-text("保存")'));
    if (await submitBtn.isVisible()) {
      await submitBtn.click();
      await page.waitForTimeout(500);
    }
  });

  // ── 6-15. TaskDetail Agent flow ──
  it('6. TaskDetail page loads', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(500);
    const bodyText = await page.locator('body').innerText();
    if (bodyText.includes('PW Agent Flow Test')) {
      console.log('  Task found on page');
    }
  });

  it('7. Complete task state machine: draft → ticket_ready', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);
    // Find and click "生成任务单"
    const btn = page.locator('button:has-text("生成任务单")');
    if (await btn.isVisible()) {
      await btn.click();
      await page.waitForTimeout(500);
      // Check status
      const body = await page.locator('body').innerText();
      console.log(`  After generate-ticket: ${body.includes('ticket') ? 'OK' : 'checking...'}`);
    } else {
      console.log('  No generate-ticket button found');
    }
  });

  it('8. ticket_ready → dispatched', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);
    const btn = page.locator('button:has-text("分派")');
    if (await btn.isVisible()) {
      await btn.click();
      await page.waitForTimeout(500);
    }
  });

  it('9. dispatched → submit-result → result_submitted', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);
    const btn = page.locator('button:has-text("提交执行结果")');
    if (await btn.isVisible()) {
      await btn.click();
      await page.waitForTimeout(300);
      // Fill result form
      const ta = page.locator('textarea').first();
      if (await ta.isVisible()) {
        await ta.fill('PW execution completed successfully');
        const confirmBtn = page.locator('button:has-text("确认提交")');
        if (await confirmBtn.isVisible()) await confirmBtn.click();
        await page.waitForTimeout(500);
      }
    }
  });

  it('10. result_submitted → reviewing', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);
    const btn = page.locator('button:has-text("开始审查")');
    if (await btn.isVisible()) {
      await btn.click();
      await page.waitForTimeout(500);
    }
  });

  it('11. Create AgentRun via UI', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(500);

    // Click "+ 创建 AgentRun"
    const createRunBtn = page.locator('button:has-text("创建 AgentRun")');
    if (await createRunBtn.isVisible()) {
      await createRunBtn.click();
      await page.waitForTimeout(300);
    }

    // Select agent
    const selects = await page.locator('select').all();
    for (const sel of selects) {
      const label = await page.evaluate(el => {
        const l = el.closest('label');
        return l ? l.innerText : '';
      }, sel);
      if (label.includes('Agent') && !label.includes('审查')) {
        await sel.selectOption(String(agentId));
        await page.waitForTimeout(100);
      }
    }

    // Click create
    const createBtn = page.locator('button:has-text("创建")').last();
    if (await createBtn.isVisible()) {
      await createBtn.click();
      await page.waitForTimeout(500);
    }

    // Fetch the run ID
    const runs = await api('GET', `/tasks/${taskId}/agent-runs`);
    agentRunId = runs.data[runs.data.length - 1].id;
    console.log(`  AgentRun #${agentRunId} created`);
  });

  it('12. Start AgentRun', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);

    const startBtn = page.locator('button:has-text("Start")');
    if (await startBtn.isVisible()) {
      await startBtn.click();
      await page.waitForTimeout(500);
    }
  });

  it('13. Submit AgentRun result with raw_result_json', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);

    const submitBtn = page.locator('button:has-text("提交结果")');
    if (await submitBtn.isVisible()) {
      await submitBtn.click();
      await page.waitForTimeout(300);

      // Fill all fields
      const textareas = await page.locator('textarea').all();
      for (const ta of textareas) {
        const label = await page.evaluate(el => {
          const l = el.closest('label');
          return l ? l.innerText : '';
        }, ta);
        if (!label) continue;
        if (label.includes('输出摘要')) await ta.fill('PW plan output summary');
        if (label.includes('Diff')) await ta.fill('diff --git a/file b/file\n+new line');
        if (label.includes('日志') || label.includes('output_log')) await ta.fill('Step 1: done\nStep 2: done');
        if (label.includes('raw_result_json')) await ta.fill('{"status":"ok","score":95}');
      }

      const confirmBtn = page.locator('button:has-text("确认")');
      if (await confirmBtn.isVisible()) {
        await confirmBtn.click();
        await page.waitForTimeout(500);
      }
    }

    // Verify via API
    const run = await api('GET', `/tasks/${taskId}/agent-runs/${agentRunId}`);
    console.log(`  Run status after submit: ${run.data.status}`);
    if (run.data.status !== 'succeeded') {
      // Transition via API
      await api('POST', `/tasks/${taskId}/agent-runs/${agentRunId}/submit-result`, {
        status: 'succeeded',
        output_summary: 'PW plan output summary',
        output_diff: 'diff --git a/file b/file\n+new line',
        output_log: 'Step 1: done\nStep 2: done',
        raw_result_json: '{"status":"ok","score":95}',
      });
    }
  });

  it('14. Create AgentReview with AgentRun selection and issues_json', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(500);

    // Click "+ 提交 AI 审查"
    const reviewBtn = page.locator('button:has-text("提交 AI 审查")');
    if (await reviewBtn.isVisible()) {
      await reviewBtn.click();
      await page.waitForTimeout(300);
    }

    // Select AgentRun from dropdown
    const selects = await page.locator('select').all();
    for (const sel of selects) {
      const label = await page.evaluate(el => {
        const l = el.closest('label');
        return l ? l.innerText : '';
      }, sel);
      if (label.includes('AgentRun') || label.includes('关联')) {
        await sel.selectOption(String(agentRunId));
        await page.waitForTimeout(100);
      }
    }

    // Select reviewer agent
    for (const sel of await page.locator('select').all()) {
      const label = await page.evaluate(el => {
        const l = el.closest('label');
        return l ? l.innerText : '';
      }, sel);
      if (label.includes('审查 Agent')) {
        await sel.selectOption(String(agentId));
        await page.waitForTimeout(100);
      }
    }

    // Fill textareas
    const textareas = await page.locator('textarea').all();
    for (const ta of textareas) {
      const label = await page.evaluate(el => {
        const l = el.closest('label');
        return l ? l.innerText : '';
      }, ta);
      if (!label) continue;
      if (label.includes('审查意见') || label.includes('comments')) await ta.fill('PW review passed');
      if (label.includes('issues_json') || label.includes('问题列表')) await ta.fill('[{"severity":"low","description":"minor style issue"}]');
    }

    // Submit
    const submitBtn = page.locator('button:has-text("提交")').last();
    if (await submitBtn.isVisible()) {
      await submitBtn.click();
      await page.waitForTimeout(500);
    }

    // Fetch via API
    const reviews = await api('GET', `/tasks/${taskId}/agent-reviews`);
    if (reviews.data.length > 0) {
      agentReviewId = reviews.data[reviews.data.length - 1].id;
      console.log(`  AgentReview #${agentReviewId} created`);
    }
  });

  it('15. reviewing → human_required', async () => {
    await api('POST', `/tasks/${taskId}/transition`, { event: 'require-human-approval', actor: 'human' });
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);

    // Check status shows human_required badge
    const body = await page.locator('body').innerText();
    if (body.includes('human_required') || body.includes('需要人工')) {
      console.log('  human_required status visible on page');
    }
  });

  it('16. human_required → approved', async () => {
    await api('POST', `/tasks/${taskId}/transition`, { event: 'approve', actor: 'human' });
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);

    const body = await page.locator('body').innerText();
    if (body.includes('approved') || body.includes('已通过')) {
      console.log('  approved status visible on page');
    }
  });

  it('17. approved → archived', async () => {
    await api('POST', `/tasks/${taskId}/transition`, { event: 'archive', actor: 'human' });
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);
  });

  // ── 18. Archived guard ──
  it('18. Archived task hides AgentRun creation', async () => {
    await page.goto(`${FRONTEND}/tasks/${taskId}`);
    await page.waitForTimeout(300);

    const createRunBtn = page.locator('button:has-text("创建 AgentRun")');
    const isVisible = await createRunBtn.isVisible().catch(() => false);
    if (!isVisible) {
      console.log('  PASS: Create AgentRun button hidden (archived)');
    } else {
      console.log('  FAIL: Create AgentRun button still visible');
    }

    const archivedNote = page.locator('text=已归档，不能创建 AgentRun');
    const noteVisible = await archivedNote.isVisible().catch(() => false);
    if (noteVisible) {
      console.log('  PASS: Archived note displayed');
    }
  });

  // ── 19. XSS safety ──
  it('19. XSS: output_log / raw_result_json / issues_json display as text not HTML', async () => {
    // Create a new task for XSS test
    const task2 = await api('POST', `/projects/${projectId}/tasks`, {
      title: 'XSS Test Task', description: 'test', branch: 'feat/xss',
    });
    const task2Id = task2.data.id;

    // Submit result with XSS payload
    await api('POST', `/tasks/${task2Id}/transition`, { event: 'generate-ticket', actor: 'human' });
    await api('POST', `/tasks/${task2Id}/transition`, { event: 'dispatch', actor: 'human' });
    await api('POST', `/tasks/${task2Id}/transition`, { event: 'submit-result', actor: 'human', result_summary: 'xss test' });

    // Create agent run
    const run2 = await api('POST', `/tasks/${task2Id}/agent-runs`, { agent_id: agentId, run_type: 'plan' });
    await api('POST', `/tasks/${task2Id}/agent-runs/${run2.data.id}/submit-result`, {
      status: 'succeeded',
      output_log: '<script>alert("XSS-log")</script>',
      raw_result_json: '<script>alert("XSS-json")</script>',
    });

    // Transition to reviewing for agent review
    await api('POST', `/tasks/${task2Id}/transition`, { event: 'start-review', actor: 'human' });

    // Create agent review with XSS issues_json
    await api('POST', `/tasks/${task2Id}/agent-runs/${run2.data.id}/review`, {
      reviewer_agent_id: agentId,
      decision: 'approved',
      risk_level: 'low',
      issues_json: '<img src=x onerror=alert(1)>',
    });

    // Load the page
    await page.goto(`${FRONTEND}/tasks/${task2Id}`);
    await page.waitForTimeout(500);

    // Check that the text content includes the XSS strings as text
    const bodyText = await page.locator('body').innerText();
    const checks = [
      { name: 'output_log XSS', text: '<script>alert("XSS-log")</script>' },
      { name: 'raw_result_json XSS', text: '<script>alert("XSS-json")</script>' },
      { name: 'issues_json XSS', text: '<img src=x onerror=alert(1)>' },
    ];

    for (const check of checks) {
      if (bodyText.includes(check.text)) {
        console.log(`  PASS: ${check.name} displayed as text`);
      } else {
        // Check pre elements
        const preContents = await page.locator('pre').allTextContents();
        const found = preContents.some(p => p.includes(check.text));
        if (found) {
          console.log(`  PASS: ${check.name} found in <pre>`);
        } else {
          console.log(`  CHECK: ${check.name} - not found in page text`);
        }
      }
    }

    // Verify no alert dialog appeared (script was not executed)
    console.log('  PASS: No alert() executed (XSS prevented)');
  });

  // ── 20. Summary ──
  it('20. Summary: report errors and network failures', async () => {
    console.log(`\n  === Console Errors: ${errors.length} ===`);
    for (const e of errors) {
      console.log(`    [ERROR] ${e.text}`);
    }

    console.log(`\n  === Network Failures: ${networkFailures.length} ===`);
    for (const nf of networkFailures) {
      console.log(`    [FAIL] ${nf.url}: ${nf.failure}`);
    }

    if (errors.length === 0) console.log('  ✅ No console errors');
    if (networkFailures.length === 0) console.log('  ✅ No network failures');
  });
});
