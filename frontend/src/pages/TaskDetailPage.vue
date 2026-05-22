<template>
  <div class="page" v-if="task">
    <header class="detail-header">
      <div>
        <h1>{{ task.title }}</h1>
        <p class="meta">
          {{ task.project_name }} · #{{ task.id }}
          <StatusBadge :status="task.status" />
          <span class="priority" :class="task.priority">{{ task.priority }}</span>
        </p>
      </div>
      <router-link :to="`/tasks?project_id=${task.project_id}`" class="back-link">← 返回列表</router-link>
    </header>

    <div class="action-bar card">
      <button
        v-for="act in availableActions"
        :key="act.action"
        class="btn btn-sm"
        :class="act.cls"
        @click="handleAction(act.action)"
        :disabled="actionLoading"
      >
        {{ act.label }}
      </button>
      <span v-if="isArchived" class="archived-label">已归档，不可操作</span>
    </div>

    <div v-if="showResultForm" class="result-form card">
      <h3>提交执行结果</h3>
      <label>
        执行摘要
        <textarea v-model="resultSummary" placeholder="描述执行结果，如遇问题请说明..." rows="5"></textarea>
      </label>
      <div class="form-actions">
        <button class="btn btn-primary" @click="confirmSubmitResult" :disabled="actionLoading">确认提交</button>
        <button class="btn" @click="showResultForm = false" :disabled="actionLoading">取消</button>
      </div>
    </div>

    <div class="detail-body">
      <section class="card">
        <h2>需求描述</h2>
        <pre class="description-text">{{ task.description || '（无描述）' }}</pre>
      </section>

      <section v-if="task.result_summary" class="card">
        <h2>执行结果</h2>
        <pre class="description-text">{{ task.result_summary }}</pre>
      </section>

      <section v-if="task.ticket_content" class="card">
        <h2>执行任务单</h2>
        <TicketPreview :content="task.ticket_content" />
      </section>

      <!-- Real AI Run -->
      <section class="card real-ai-run">
        <div class="section-header">
          <h2>Real AI Run / 真实 AI 调用</h2>
          <span class="workspace-readonly">S11 gated execution</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-provider">provider: openai</span>
          <span class="label-badge label-ai">model: {{ realAiDryRunResult?.model || 'backend configured' }}</span>
          <span class="label-badge label-redacted">AI_EXECUTION_ENABLED required</span>
          <span class="label-badge label-redacted">OPENAI_API_KEY required</span>
          <span class="label-badge label-provider">allowlist: openai</span>
          <span class="label-badge label-merged">No auto merge</span>
        </div>
        <div class="real-ai-form">
          <label>
            mode
            <select v-model="realAiMode">
              <option value="planning">planning</option>
              <option value="review">review</option>
              <option value="risk">risk</option>
              <option value="patch_generation">patch_generation</option>
            </select>
          </label>
          <label>
            task_goal
            <textarea v-model="realAiTaskGoal" rows="4"></textarea>
          </label>
          <div class="form-actions">
            <button class="btn btn-sm" @click="runAiDryRun" :disabled="realAiLoading || !task">Dry-run</button>
            <button class="btn btn-primary btn-sm" @click="executeRealAiRun" :disabled="realAiLoading || !task">Execute</button>
          </div>
        </div>
        <p v-if="realAiError" class="run-error">{{ realAiError }}</p>
        <div v-if="realAiDryRunResult" class="real-ai-result">
          <strong>dry-run result</strong>
          <div class="dispatch-job-hashes">
            <code>prompt_hash: {{ realAiDryRunResult.prompt_hash || '-' }}</code>
            <code>context_packet_hash: {{ realAiDryRunResult.context_packet_hash || '-' }}</code>
          </div>
          <div class="dispatch-job-meta">
            <span>would_dispatch={{ realAiDryRunResult.would_dispatch }}</span>
            <span>estimated_tokens={{ realAiDryRunResult.estimated_tokens }}</span>
            <span>model={{ realAiDryRunResult.model }}</span>
            <span>mode={{ realAiDryRunResult.mode }}</span>
          </div>
          <pre>{{ formatSafetyGate(realAiDryRunResult.safety_gate) }}</pre>
          <div v-if="dryRunBlockedReasons.length" class="run-error">
            <span>blocked:</span>
            <span v-for="reason in dryRunBlockedReasons" :key="reason">{{ reason }}</span>
          </div>
        </div>
        <div v-if="realAiExecuteResult" class="real-ai-result">
          <strong>execute result</strong>
          <div class="dispatch-job-meta">
            <span>agent_run_id: {{ realAiExecuteResult.agent_run_id }}</span>
            <span>status: {{ realAiExecuteResult.status }}</span>
            <span>pipeline_status: {{ realAiExecuteResult.pipeline_status }}</span>
          </div>
          <p v-if="realAiExecuteResult.output_summary" class="run-output">{{ realAiExecuteResult.output_summary }}</p>
          <div class="dispatch-job-hashes">
            <code>prompt_hash: {{ realAiExecuteResult.prompt_hash || '-' }}</code>
            <code>context_packet_hash: {{ realAiExecuteResult.context_packet_hash || '-' }}</code>
          </div>
          <div class="dispatch-job-meta">
            <span>artifacts:</span>
            <span v-for="name in executeArtifactNames" :key="name">{{ name }}</span>
          </div>
          <div class="real-ai-sandbox">
            <strong>Patch Sandbox / Gate</strong>
            <p class="section-note">Patch is not applied to the real repository. Sandbox only.</p>
            <p class="section-note">Sandbox Gate passed is required before any PR step.</p>
            <div class="dispatch-job-meta">
              <span>sandbox_applied={{ realAiExecuteResult.sandbox_applied }}</span>
              <span>sandbox_gate_passed={{ realAiExecuteResult.sandbox_gate_passed }}</span>
              <span>pipeline_status: {{ realAiExecuteResult.pipeline_status }}</span>
              <span>{{ pipelineStatusLabel(realAiExecuteResult.pipeline_status) }}</span>
            </div>
            <div v-if="realAiExecuteResult.sandbox_gate_blocked_reasons.length" class="run-error">
              <span>sandbox_gate_blocked_reasons:</span>
              <span v-for="reason in realAiExecuteResult.sandbox_gate_blocked_reasons" :key="reason">{{ reason }}</span>
            </div>
            <div v-if="sandboxGateStepNames.length" class="dispatch-job-meta">
              <span>steps:</span>
              <span v-for="step in sandboxGateStepNames" :key="step">{{ step }}</span>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>角色信息</h2>
        <div class="roles">
          <div><strong>Planner:</strong> {{ task.planner || '-' }}</div>
          <div><strong>Executor:</strong> {{ task.executor || '-' }}</div>
          <div><strong>Reviewer:</strong> {{ task.reviewer || '-' }}</div>
          <div><strong>Approver:</strong> {{ task.human_approver || '-' }}</div>
        </div>
      </section>

      <!-- Agent Runs -->
      <section class="card">
        <div class="section-header">
          <h2>Agent 运行</h2>
          <button v-if="!isArchived" class="btn btn-sm btn-primary" @click="showAgentRunForm = true">+ 创建 AgentRun</button>
        </div>
        <p v-if="isArchived && task" class="section-note">已归档，不能创建 AgentRun</p>

        <div v-if="showAgentRunForm && !isArchived" class="inline-form">
          <label>
            Agent
            <select v-model="agentRunForm.agent_id">
              <option value="">请选择</option>
              <option v-for="a in agents" :key="a.id" :value="a.id" :disabled="!a.enabled">
                {{ a.name }} ({{ a.agent_type }})
              </option>
            </select>
          </label>
          <label>
            运行类型
            <select v-model="agentRunForm.run_type">
              <option value="plan">规划 (Plan)</option>
              <option value="execute">执行 (Execute)</option>
              <option value="review">审查 (Review)</option>
              <option value="test">测试 (Test)</option>
              <option value="remediate">修复 (Remediate)</option>
            </select>
          </label>
          <label>
            输入提示
            <textarea v-model="agentRunForm.input_prompt" rows="4" placeholder="输入 prompt..."></textarea>
          </label>
          <label>分支<input v-model="agentRunForm.branch" placeholder="可选" /></label>
          <div class="form-actions">
            <button class="btn btn-primary btn-sm" @click="handleCreateAgentRun" :disabled="!agentRunForm.agent_id">创建</button>
            <button class="btn btn-sm" @click="showAgentRunForm = false">取消</button>
          </div>
        </div>

        <div v-if="agentRuns.length === 0" class="empty-state" style="margin-top: 12px;">
          <p>暂无 Agent 运行记录</p>
        </div>
        <div v-for="r in agentRuns" :key="r.id" class="agent-run-item">
          <div class="agent-run-header">
            <strong>{{ runTypeLabel(r.run_type) }}</strong>
            <span class="run-status-badge" :class="r.status">{{ AGENT_RUN_STATUS_LABELS[r.status] || r.status }}</span>
            <span class="run-risk" :class="r.risk_level">风险: {{ r.risk_level }}</span>
            <span class="run-attempt">#{{ r.attempt_no }}</span>
          </div>
          <div class="agent-run-meta">
            Agent #{{ r.agent_id }} · {{ r.branch || '无分支' }}
            <span v-if="r.duration_ms"> · {{ Math.round(r.duration_ms / 1000) }}s</span>
            <span v-if="r.commit_sha"> · commit {{ r.commit_sha.substring(0, 8) }}</span>
          </div>
          <div class="agent-run-meta">
            创建: {{ formatTime(r.created_at) }}
            <span v-if="r.updated_at"> · 更新: {{ formatTime(r.updated_at) }}</span>
          </div>
          <p v-if="r.input_prompt" class="run-prompt">{{ r.input_prompt }}</p>
          <p v-if="r.output_summary" class="run-output">{{ r.output_summary }}</p>
          <p v-if="r.error_message" class="run-error">{{ r.error_message }}</p>
          <div v-if="r.output_diff" class="run-diff">
            <DiffViewer :content="r.output_diff" />
          </div>
          <div v-if="r.output_log" class="run-field">
            <span class="field-label">日志输出 (output_log)</span>
            <pre class="run-pre">{{ r.output_log }}</pre>
          </div>
          <div v-if="r.raw_result_json" class="run-field">
            <span class="field-label">原始结果 JSON (raw_result_json)</span>
            <pre class="run-pre">{{ r.raw_result_json }}</pre>
          </div>

          <!-- Governance display -->
          <div v-if="parseGovernance(r)" class="gov-section">
            <span class="field-label">治理校验</span>
            <div class="gov-grid">
              <span class="gov-tag" :class="parseGovernance(r).valid ? 'gov-pass' : 'gov-fail'">
                {{ parseGovernance(r).valid ? 'Valid' : 'Invalid' }}
              </span>
              <span v-if="parseGovernance(r).requires_human" class="gov-tag gov-human">需人工审批</span>
              <span class="gov-tag" :class="'gov-risk-' + (parseGovernance(r).risk_level || 'low')">
                风险: {{ parseGovernance(r).risk_level }}
              </span>
              <span v-if="parseTrace(r)?.provider" class="gov-tag gov-info">
                {{ parseTrace(r).provider }}
              </span>
            </div>
            <div v-if="parseGovernance(r).errors?.length" class="gov-issues">
              <div v-for="e in parseGovernance(r).errors" class="gov-error">{{ e }}</div>
            </div>
            <div v-if="parseGovernance(r).warnings?.length" class="gov-issues">
              <div v-for="w in parseGovernance(r).warnings" class="gov-warn">{{ w }}</div>
            </div>
          </div>

          <div class="agent-run-actions">
            <button v-if="r.status === 'queued'" class="btn btn-sm btn-primary" @click="startAgentRun(r)">Start</button>
            <button v-if="r.status === 'queued' || r.status === 'running'" class="btn btn-sm btn-warn" @click="cancelAgentRun(r)">Cancel</button>
            <button v-if="r.status === 'running'" class="btn btn-sm" @click="showSubmitResult(r)">提交结果</button>
          </div>

          <div v-if="submitFormRunId === r.id" class="inline-form">
            <label>
              结果状态
              <select v-model="submitForm.status">
                <option value="succeeded">成功 (Succeeded)</option>
                <option value="failed">失败 (Failed)</option>
              </select>
            </label>
            <label>输出摘要<textarea v-model="submitForm.output_summary" rows="3"></textarea></label>
            <label>错误信息<textarea v-model="submitForm.error_message" rows="2"></textarea></label>
            <label>Diff 输出<textarea v-model="submitForm.output_diff" rows="3"></textarea></label>
            <label>日志输出<textarea v-model="submitForm.output_log" rows="3"></textarea></label>
            <label>
              原始结果 JSON (raw_result_json)
              <textarea v-model="submitForm.raw_result_json" rows="3" placeholder='{"key": "value"}'></textarea>
            </label>
            <div class="form-actions">
              <button class="btn btn-primary btn-sm" @click="confirmSubmitRunResult(r)" :disabled="actionLoading">确认</button>
              <button class="btn btn-sm" @click="submitFormRunId = null" :disabled="actionLoading">取消</button>
            </div>
          </div>
        </div>
      </section>

      <!-- Multi-AI Answer Workspace -->
      <section class="card multi-ai-workspace">
        <div class="section-header">
          <h2>Multi-AI Answer Workspace / 多 AI 回答工作台</h2>
          <span class="workspace-readonly">Read-only display</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Read-only display</span>
          <span class="label-badge label-provider">No external PR created</span>
          <span class="label-badge label-merged">No auto merge</span>
          <span class="label-badge label-applied">Sandbox only</span>
        </div>
        <p v-if="dispatchBatchError" class="run-error">{{ dispatchBatchError }}</p>
        <div v-else-if="dispatchBatches.length === 0" class="empty-state"><p>暂无多 AI Dispatch 记录</p></div>
        <div v-else class="dispatch-batch-list">
          <div v-for="batch in dispatchBatches" :key="batch.dispatch_batch_id" class="dispatch-batch-item">
            <div class="dispatch-batch-header">
              <strong>Batch #{{ batch.dispatch_batch_id }}</strong>
              <span class="label-badge label-provider">{{ batch.batch_mode }}</span>
              <span class="run-status-badge" :class="batch.status">{{ batch.status }}</span>
            </div>
            <div class="dispatch-batch-meta">
              <span>task_goal: {{ batch.task_goal || '-' }}</span>
              <span>summary: {{ formatSummary(batch.summary) }}</span>
            </div>
            <div class="dispatch-job-grid">
              <div v-for="job in batch.jobs" :key="`${batch.dispatch_batch_id}-${job.sequence_no}-${job.dispatch_job_id || job.question}`" class="dispatch-job-card">
                <div class="dispatch-job-header">
                  <strong>#{{ job.sequence_no }} {{ job.question }}</strong>
                  <span class="run-status-badge" :class="job.status">{{ job.status }}</span>
                </div>
                <div class="dispatch-job-meta">
                  <span>provider: {{ job.provider }}</span>
                  <span>model: {{ job.model }}</span>
                  <span>mode: {{ job.mode }}</span>
                  <span>expected_artifact_type: {{ job.expected_artifact_type || '-' }}</span>
                </div>
                <div class="dispatch-job-hashes">
                  <code>prompt_hash: {{ job.prompt_hash || '-' }}</code>
                  <code>context_packet_hash: {{ job.context_packet_hash || '-' }}</code>
                </div>
                <div class="dispatch-job-meta">
                  <span>agent_run_id: {{ job.agent_run_id || '-' }}</span>
                  <span>artifact_ids: {{ formatArtifactIds(job.artifact_ids) }}</span>
                </div>
                <p v-if="job.error_message" class="run-error">{{ job.error_message }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Answer Synthesis -->
      <section class="card answer-synthesis-workspace">
        <div class="section-header">
          <h2>Answer Synthesis / 多 AI 综合结论</h2>
          <button class="btn btn-sm" @click="refreshAnswerSynthesis" :disabled="answerSynthesisLoading || dispatchBatches.length === 0">
            重新生成综合结论
          </button>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-provider">Rule-based preview</span>
          <span class="label-badge label-exec">No AI provider called</span>
          <span class="label-badge label-applied">No database write</span>
          <span class="label-badge label-merged">No auto approve</span>
          <span class="label-badge label-exec">No PR created</span>
        </div>
        <p v-if="answerSynthesisError" class="run-error">{{ answerSynthesisError }}</p>
        <div v-else-if="dispatchBatches.length === 0" class="empty-state"><p>暂无可综合的多 AI 结果</p></div>
        <div v-else-if="answerSynthesisLoading && !answerSynthesis" class="empty-state"><p>综合结论生成中...</p></div>
        <div v-else-if="answerSynthesis" class="synthesis-panel">
          <div class="synthesis-metrics">
            <span class="run-status-badge" :class="answerSynthesis.synthesis_status">{{ answerSynthesis.synthesis_status }}</span>
            <span>confidence: {{ formatConfidence(answerSynthesis.confidence) }}</span>
            <span>job_count: {{ answerSynthesis.job_count }}</span>
            <span>succeeded_jobs: {{ answerSynthesis.succeeded_jobs }}</span>
            <span>failed_jobs: {{ answerSynthesis.failed_jobs }}</span>
            <span>blocked_jobs: {{ answerSynthesis.blocked_jobs }}</span>
          </div>
          <div class="synthesis-grid">
            <div class="synthesis-list">
              <strong>common_findings</strong>
              <p v-if="answerSynthesis.common_findings.length === 0">-</p>
              <ul v-else><li v-for="item in answerSynthesis.common_findings" :key="item">{{ item }}</li></ul>
            </div>
            <div class="synthesis-list">
              <strong>risks</strong>
              <p v-if="answerSynthesis.risks.length === 0">-</p>
              <ul v-else><li v-for="item in answerSynthesis.risks" :key="item">{{ item }}</li></ul>
            </div>
            <div class="synthesis-list">
              <strong>recommended_actions</strong>
              <p v-if="answerSynthesis.recommended_actions.length === 0">-</p>
              <ul v-else><li v-for="item in answerSynthesis.recommended_actions" :key="item">{{ item }}</li></ul>
            </div>
            <div class="synthesis-list">
              <strong>next_questions</strong>
              <p v-if="answerSynthesis.next_questions.length === 0">-</p>
              <ul v-else><li v-for="item in answerSynthesis.next_questions" :key="item">{{ item }}</li></ul>
            </div>
            <div class="synthesis-list">
              <strong>disagreements</strong>
              <p v-if="answerSynthesis.disagreements.length === 0">-</p>
              <ul v-else><li v-for="item in answerSynthesis.disagreements" :key="item">{{ item }}</li></ul>
            </div>
            <div class="synthesis-list">
              <strong>safety_notes</strong>
              <p v-if="answerSynthesis.safety_notes.length === 0">-</p>
              <ul v-else><li v-for="item in answerSynthesis.safety_notes" :key="item">{{ item }}</li></ul>
            </div>
          </div>
          <div class="synthesis-source-ids">
            <code>source_job_ids: {{ formatArtifactIds(answerSynthesis.source_job_ids) }}</code>
            <code>source_agent_run_ids: {{ formatArtifactIds(answerSynthesis.source_agent_run_ids) }}</code>
            <code>source_artifact_ids: {{ formatArtifactIds(answerSynthesis.source_artifact_ids) }}</code>
          </div>
          <div class="synthesis-artifacts">
            <strong>artifact_summaries</strong>
            <div v-if="answerSynthesis.artifact_summaries.length === 0" class="empty-state"><p>-</p></div>
            <div v-for="artifact in answerSynthesis.artifact_summaries" :key="artifact.artifact_id" class="synthesis-artifact-item">
              <span>#{{ artifact.artifact_id }} {{ artifact.filename || '-' }} · {{ artifact.artifact_type }}</span>
              <span v-if="artifact.is_truncated" class="label-badge label-redacted">truncated</span>
              <pre>{{ artifact.summary || '-' }}</pre>
            </div>
          </div>
        </div>
      </section>

      <!-- AI Handoff Packet -->
      <section class="card ai-handoff-workspace">
        <div class="section-header">
          <h2>AI Handoff Packet / 下一 AI 接管包</h2>
          <div class="section-actions">
            <button class="btn btn-sm" @click="refreshAiHandoff" :disabled="aiHandoffLoading || !task">
              重新生成接管包
            </button>
            <button class="btn btn-sm" @click="copyNextAiPrompt" :disabled="!aiHandoff?.next_ai_prompt">
              复制 next_ai_prompt
            </button>
          </div>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-provider">Stateless preview</span>
          <span class="label-badge label-exec">No AI provider called</span>
          <span class="label-badge label-applied">No database write</span>
          <span class="label-badge label-redacted">Verify current master before acting</span>
          <span class="label-badge label-redacted">verify_current_master_on_github_before_acting</span>
          <span class="label-badge label-ai">AGENTS.md</span>
          <span class="label-badge label-provider">Do not read .env.</span>
          <span class="label-badge label-merged">No auto merge</span>
        </div>
        <p v-if="aiHandoffError" class="run-error">{{ aiHandoffError }}</p>
        <p v-if="aiHandoffCopyMessage" class="copy-message">{{ aiHandoffCopyMessage }}</p>
        <div v-if="!task && !aiHandoffError" class="empty-state"><p>暂无可生成接管包的任务</p></div>
        <div v-else-if="aiHandoffLoading && !aiHandoff" class="empty-state"><p>接管包生成中...</p></div>
        <div v-else-if="aiHandoff" class="handoff-panel">
          <div class="synthesis-metrics">
            <span class="run-status-badge" :class="aiHandoff.handoff_status">{{ aiHandoff.handoff_status }}</span>
            <span>project_id: {{ aiHandoff.project_id }}</span>
            <span>task_id: {{ aiHandoff.task_id || '-' }}</span>
            <span>redaction_applied: {{ aiHandoff.redaction_applied }}</span>
          </div>
          <pre class="handoff-details">{{ formatHandoffDetails(aiHandoff) }}</pre>
          <div class="handoff-prompt-block">
            <strong>next_ai_prompt</strong>
            <textarea readonly :value="aiHandoff.next_ai_prompt" aria-label="next_ai_prompt"></textarea>
          </div>
        </div>
      </section>

      <!-- Code Context -->
      <section class="card">
        <h2>代码上下文</h2>
        <div v-if="!codeContext" class="empty-state"><p>暂无代码上下文数据</p></div>
        <div v-else>
          <div class="context-meta">
            <span class="label-badge label-ai">API-provided context</span>
            <span class="label-badge label-redacted">Redacted</span>
            <span class="label-badge label-applied">Not read from repository</span>
            <span class="context-stat">{{ codeContext.file_count }} 文件 · {{ codeContext.total_size_bytes }} 字节</span>
          </div>
          <div v-for="f in codeContext.files" :key="f.path" class="context-file-item">
            <div class="context-file-header">
              <strong>{{ f.path }}</strong>
              <span class="context-lang">{{ f.language || 'text' }}</span>
            </div>
            <pre class="context-file-preview">{{ f.content.substring(0, 300) }}{{ f.content.length > 300 ? '...' : '' }}</pre>
          </div>
        </div>
      </section>

      <!-- Patch Sandbox -->
      <section class="card">
        <h2>补丁沙箱</h2>
        <p class="section-note">在内存沙箱中验证 AI 生成的补丁，不提交至真实仓库。</p>

        <div v-if="!isArchived && agentRuns.some(r => r.status === 'succeeded' && r.run_type === 'execute')" class="sandbox-apply-area">
          <div class="sandbox-label-bar">
            <span class="label-badge label-applied">Sandbox only</span>
            <span class="label-badge label-merged">Not committed</span>
            <span class="label-badge label-exec">No PR created</span>
          </div>
          <div class="sandbox-run-select">
            <label>
              选择已成功的 Execute AgentRun：
              <select v-model="selectedSandboxRunId">
                <option value="">请选择</option>
                <option v-for="r in agentRuns.filter(x => x.status === 'succeeded' && x.run_type === 'execute')" :key="r.id" :value="r.id">
                  #{{ r.id }} · {{ r.output_summary?.substring(0, 60) || '无摘要' }}
                </option>
              </select>
            </label>
            <button class="btn btn-sm btn-primary" :disabled="!selectedSandboxRunId || sandboxLoading" @click="handleSandboxApply(selectedSandboxRunId!)">
              {{ sandboxLoading ? '应用中...' : 'Apply in Sandbox' }}
            </button>
          </div>
        </div>

        <div v-if="isArchived" class="sandbox-archived-note">任务已归档，无法执行沙箱操作。</div>

        <!-- Apply result -->
        <div v-if="applyResult" class="sandbox-result">
          <div class="sandbox-result-header">
            <span class="run-status-badge" :class="applyResult.success ? 'succeeded' : 'failed'">
              {{ applyResult.success ? '已应用' : '失败' }}
            </span>
            <span>{{ applyResult.message }}</span>
          </div>
          <p v-if="applyResult.report.errors?.length" class="sandbox-errors">
            <span v-for="e in applyResult.report.errors" class="sandbox-error-item">{{ e }}</span>
          </p>
          <p v-if="applyResult.report.warnings?.length" class="sandbox-warnings">
            <span v-for="w in applyResult.report.warnings" class="sandbox-warn-item">{{ w }}</span>
          </p>

          <!-- Changed files -->
          <div v-if="applyResult.report.changed_files?.length" class="sandbox-changed-files">
            <h3>变更文件</h3>
            <table class="sandbox-table">
              <thead><tr><th>文件路径</th><th>状态</th><th>增</th><th>删</th><th>Before SHA256</th><th>After SHA256</th></tr></thead>
              <tbody>
                <tr v-for="cf in applyResult.report.changed_files" :key="cf.path">
                  <td class="cf-path">{{ cf.path }}</td>
                  <td><span class="run-status-badge" :class="cf.status === 'added' ? 'succeeded' : 'running'">{{ cf.status }}</span></td>
                  <td class="cf-num cf-add">+{{ cf.additions }}</td>
                  <td class="cf-num cf-del">-{{ cf.deletions }}</td>
                  <td class="cf-sha"><code>{{ cf.before_sha256?.substring(0, 12) || '-' }}</code></td>
                  <td class="cf-sha"><code>{{ cf.after_sha256?.substring(0, 12) || '-' }}</code></td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Before/after previews -->
          <div v-if="applyResult.before_after_previews && Object.keys(applyResult.before_after_previews).length" class="sandbox-previews">
            <h3>Before / After 预览</h3>
            <div v-for="(preview, path) in applyResult.before_after_previews" :key="path" class="sandbox-preview-pair">
              <div class="preview-col">
                <span class="preview-label">Before</span>
                <pre class="preview-code">{{ preview.before || '(空文件)' }}</pre>
              </div>
              <div class="preview-col">
                <span class="preview-label">After</span>
                <pre class="preview-code">{{ preview.after || '(空文件)' }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- Sandbox result artifacts -->
        <div v-if="sandboxResults.length" class="sandbox-artifacts">
          <h3>沙箱产物</h3>
          <div v-for="art in sandboxResults" :key="art.id" class="sandbox-artifact-item">
            <div class="sandbox-artifact-header">
              <span class="label-badge label-ai">{{ art.artifact_type }}</span>
              <span class="sandbox-artifact-meta">{{ art.filename }} · {{ art.size_bytes }} 字节</span>
              <code class="sandbox-artifact-sha">{{ art.sha256?.substring(0, 16) || '' }}</code>
            </div>
            <pre v-if="art.content" class="sandbox-artifact-content">{{ art.content.substring(0, 500) }}{{ art.content.length > 500 ? '...' : '' }}</pre>
          </div>
        </div>
      </section>

      <!-- Sandbox Gate -->
      <section class="card">
        <h2>沙箱审批门</h2>
        <p class="section-note">Sandbox Approval Gate 评估沙箱结果是否满足提 PR 前置条件。</p>
        <div v-if="sandboxGateLoading" class="sandbox-gate-loading">评估中...</div>
        <div v-else-if="sandboxGate" class="sandbox-gate-result">
          <div class="sandbox-gate-header">
            <span class="run-status-badge" :class="sandboxGate.passed ? 'succeeded' : 'failed'">
              {{ sandboxGate.passed ? '已通过' : '已拦截' }}
            </span>
            <span>{{ sandboxGate.message }}</span>
            <button class="btn btn-sm" @click="refreshSandboxGate" :disabled="sandboxGateLoading">重新评估</button>
          </div>
          <div v-if="sandboxGate.blocked_reasons.length" class="sandbox-gate-reasons">
            <h3>拦截原因</h3>
            <ul>
              <li v-for="br in sandboxGate.blocked_reasons" :key="br.reason">
                <strong>{{ br.reason }}</strong>
                <span v-if="br.detail">: {{ br.detail }}</span>
              </li>
            </ul>
          </div>

        </div>
      </section>

      <!-- Agent Review -->
      <section class="card">
        <div class="section-header">
          <h2>Agent 审查</h2>
          <button v-if="agentRuns.length > 0 && !isArchived" class="btn btn-sm btn-primary" @click="showAgentReviewForm = true">+ 提交 AI 审查</button>
        </div>
        <p class="section-note">AgentReview 是 AI 预审建议，不等同于人类最终审批</p>

        <div v-if="showAgentReviewForm && !isArchived" class="inline-form">
          <label>
            关联 AgentRun
            <select v-model="agentReviewForm.agent_run_id" class="run-select">
              <option value="">请选择 AgentRun</option>
              <option v-for="r in agentRuns" :key="r.id" :value="r.id">
                #{{ r.id }} · {{ runTypeLabel(r.run_type) }} · {{ AGENT_RUN_STATUS_LABELS[r.status] || r.status }} · {{ formatTime(r.created_at) }}
              </option>
            </select>
          </label>
          <label>
            审查 Agent
            <select v-model="agentReviewForm.reviewer_agent_id">
              <option value="">请选择</option>
              <option v-for="a in agents" :key="a.id" :value="a.id" :disabled="!a.enabled">
                {{ a.name }} ({{ a.agent_type }})
              </option>
            </select>
          </label>
          <label>
            决策
            <select v-model="agentReviewForm.decision">
              <option value="approved">通过 (Approved)</option>
              <option value="changes_requested">要求修改 (Changes Requested)</option>
              <option value="rejected">拒绝 (Rejected)</option>
              <option value="human_required">需要人工审批 (Human Required)</option>
            </select>
          </label>
          <label>
            风险等级
            <select v-model="agentReviewForm.risk_level">
              <option value="low">低 (Low)</option>
              <option value="medium">中 (Medium)</option>
              <option value="high">高 (High)</option>
              <option value="critical">严重 (Critical)</option>
            </select>
          </label>
          <label>置信度 (0-1)<input v-model.number="agentReviewForm.confidence_score" type="number" min="0" max="1" step="0.1" /></label>
          <label>审查意见<textarea v-model="agentReviewForm.comments" rows="3"></textarea></label>
          <label>
            问题列表 JSON (issues_json)
            <textarea v-model="agentReviewForm.issues_json" rows="3" placeholder='[{"severity":"high","description":"..."}]'></textarea>
          </label>
          <div class="form-actions">
            <button class="btn btn-primary btn-sm" @click="handleCreateAgentReview" :disabled="!agentReviewForm.reviewer_agent_id || !agentReviewForm.agent_run_id">提交</button>
            <button class="btn btn-sm" @click="showAgentReviewForm = false">取消</button>
          </div>
        </div>

        <div v-if="agentReviews.length === 0" class="empty-state" style="margin-top: 12px;">
          <p>暂无 AI 审查记录</p>
        </div>
        <div v-for="rev in agentReviews" :key="rev.id" class="agent-review-item">
          <div class="agent-review-header">
            <span class="review-decision" :class="rev.decision">{{ rev.decision }}</span>
            <span class="review-risk" :class="rev.risk_level">风险: {{ rev.risk_level }}</span>
            <span v-if="rev.confidence_score !== null" class="review-confidence">置信度 {{ rev.confidence_score }}</span>
            <span class="review-time">{{ formatTime(rev.created_at) }}</span>
          </div>
          <p class="review-meta">审查 Agent #{{ rev.reviewer_agent_id }} · AgentRun #{{ rev.agent_run_id }}</p>
          <p v-if="rev.comments" class="review-comments">{{ rev.comments }}</p>
          <div v-if="rev.issues_json" class="run-field">
            <span class="field-label">问题列表 (issues_json)</span>
            <pre class="run-pre">{{ rev.issues_json }}</pre>
          </div>
        </div>
      </section>

      <!-- Governance Status -->
      <section class="card">
        <h2>AI 输出治理</h2>
        <div v-if="agentRuns.length === 0" class="empty-state"><p>暂无 AgentRun 数据</p></div>
        <div v-for="r in agentRuns" :key="r.id" class="gov-status-item">
          <div class="gov-status-header">
            <strong>AgentRun #{{ r.id }} · {{ runTypeLabel(r.run_type) }}</strong>
            <span class="run-status-badge" :class="r.status">{{ AGENT_RUN_STATUS_LABELS[r.status] || r.status }}</span>
          </div>
          <div class="gov-badges">
            <span class="label-badge label-ai">AI-generated</span>
            <span v-if="parseTrace(r)?.provider" class="label-badge label-provider">{{ parseTrace(r).provider }} 输出</span>
            <span v-if="r.raw_result_json?.includes('REDACTED')" class="label-badge label-redacted">Secret redacted</span>
            <span class="label-badge label-merged">Not automatically merged</span>
            <span class="label-badge label-exec">Not executed</span>
            <span class="label-badge label-applied">Not applied to repository</span>
          </div>
        </div>
      </section>

      <!-- Approval Decisions -->
      <section class="card">
        <h2>审批决策</h2>
        <div v-if="approvalDecisions.length === 0" class="empty-state"><p>暂无审批决策记录</p></div>
        <div v-for="d in approvalDecisions" :key="d.id" class="approval-decision-item">
          <div class="approval-decision-header">
            <span class="gov-tag" :class="d.human_required ? 'gov-human' : 'gov-pass'">
              {{ d.human_required ? '需人工审批' : '系统自动判定' }}
            </span>
            <span class="gov-tag" :class="'gov-risk-' + (d.risk_level || 'low')">风险: {{ d.risk_level }}</span>
            <span class="gov-tag" :class="d.auto_approve_allowed ? 'gov-pass' : 'gov-fail'">
              自动审批: {{ d.auto_approve_allowed ? '允许' : '禁止' }}
            </span>
          </div>
          <p v-if="d.decision_reason" class="gov-reason">{{ d.decision_reason }}</p>
          <p class="gov-time">创建时间: {{ formatTime(d.created_at) }}</p>
        </div>
      </section>

      <!-- AI Artifacts -->
      <section class="card">
        <h2>AI 产物</h2>
        <ArtifactTab :task-id="task.id" :task-status="task.status" />
        <div class="artifact-note">
          <span class="label-badge label-ai">AI-generated</span>
          <span class="label-badge label-redacted">Secret redacted</span>
          <span class="label-badge label-merged">Not automatically merged</span>
          <span class="label-badge label-exec">Not executed</span>
          <span class="label-badge label-applied">Not applied to repository</span>
        </div>
      </section>

      <section class="card">
        <h2>审查记录</h2>
        <ReviewPanel :task-id="task.id" :task-status="task.status" @review-submitted="refresh" />
      </section>

      <section class="card">
        <h2>审计日志</h2>
        <EventTimeline :task-id="task.id" />
      </section>

    </div>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore } from '../stores/taskStore'
import {
  fetchAgents,
  fetchAgentRuns, createAgentRun, updateAgentRun, submitAgentRunResult,
  fetchAgentReviews, createAgentReview,
  fetchApprovalDecisions,
  fetchDispatchBatches, previewAnswerSynthesis, previewAiHandoff,
  dryRunAiDispatch, executeAiDispatch,
  fetchCodeContext,
  applyPatchInSandbox, fetchSandboxResults, fetchSandboxGate, evaluateSandboxGate,
} from '../services/agentService'
import type { AgentProfile, AgentRun, AgentReview, AgentRunSubmitResult, ApprovalDecision, CodeContextResponse, PatchApplyResult, SandboxArtifactEntry, SandboxGateDecision, DispatchBatchResponse, AnswerSynthesisPreviewResponse, AiHandoffPreviewResponse, AiDispatchMode, AiDispatchRequest, AiDispatchDryRunResponse, AiDispatchExecuteResponse, AiDispatchSafetyGate } from '../types/agent'
import { AGENT_RUN_STATUS_LABELS, AGENT_RUN_TYPE_LABELS } from '../types/agent'
import StatusBadge from '../components/StatusBadge.vue'
import TicketPreview from '../components/TicketPreview.vue'
import ArtifactTab from '../components/ArtifactTab.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import EventTimeline from '../components/EventTimeline.vue'
import DiffViewer from '../components/DiffViewer.vue'

const route = useRoute()
const taskStore = useTaskStore()
const task = ref<any>(null)
const actionLoading = ref(false)
const showResultForm = ref(false)
const resultSummary = ref('')

const agents = ref<AgentProfile[]>([])
const agentRuns = ref<AgentRun[]>([])
const agentReviews = ref<AgentReview[]>([])
const approvalDecisions = ref<ApprovalDecision[]>([])
const dispatchBatches = ref<DispatchBatchResponse[]>([])
const dispatchBatchError = ref('')
const answerSynthesis = ref<AnswerSynthesisPreviewResponse | null>(null)
const answerSynthesisError = ref('')
const answerSynthesisLoading = ref(false)
const aiHandoff = ref<AiHandoffPreviewResponse | null>(null)
const aiHandoffError = ref('')
const aiHandoffLoading = ref(false)
const aiHandoffCopyMessage = ref('')
const realAiMode = ref<AiDispatchMode>('review')
const realAiTaskGoal = ref('')
const realAiLoading = ref(false)
const realAiError = ref('')
const realAiDryRunResult = ref<AiDispatchDryRunResponse | null>(null)
const realAiExecuteResult = ref<AiDispatchExecuteResponse | null>(null)
const codeContext = ref<CodeContextResponse | null>(null)
const sandboxResults = ref<SandboxArtifactEntry[]>([])
const applyResult = ref<PatchApplyResult | null>(null)
const sandboxLoading = ref(false)
const selectedSandboxRunId = ref<number | null>(null)
const sandboxGate = ref<SandboxGateDecision | null>(null)
const sandboxGateLoading = ref(false)
const showAgentRunForm = ref(false)
const showAgentReviewForm = ref(false)
const submitFormRunId = ref<number | null>(null)

const agentRunForm = ref({ agent_id: 0, run_type: 'plan', input_prompt: '', branch: '' })
const agentReviewForm = ref({ reviewer_agent_id: 0, decision: 'approved', risk_level: 'low', comments: '', confidence_score: null as number | null, agent_run_id: 0, issues_json: '' })
const submitForm = ref<AgentRunSubmitResult>({ status: 'succeeded', output_summary: '', error_message: '', output_diff: '', output_log: '', raw_result_json: '' })

const ACTION_MAP: Record<string, { action: string; label: string; cls: string }[]> = {
  draft: [{ action: 'generate-ticket', label: '生成任务单', cls: 'btn-primary' }],
  ticket_ready: [{ action: 'dispatch', label: '分派给 Executor', cls: 'btn-primary' }],
  dispatched: [{ action: 'submit-result', label: '提交执行结果', cls: 'btn-primary' }],
  result_submitted: [{ action: 'start-review', label: '开始审查', cls: 'btn-primary' }],
  reviewing: [
    { action: 'require-human-approval', label: '需要人工审批', cls: 'btn-warn' },
    { action: 'approve', label: '通过 (Approve)', cls: 'btn-approve' },
    { action: 'reject', label: '拒绝 (Reject)', cls: 'btn-reject' },
    { action: 'request-changes', label: '要求修改', cls: 'btn-warn' },
  ],
  changes_requested: [{ action: 'dispatch', label: '重新分派', cls: 'btn-primary' }],
  human_required: [
    { action: 'approve', label: '通过 (Approve)', cls: 'btn-approve' },
    { action: 'reject', label: '拒绝 (Reject)', cls: 'btn-reject' },
    { action: 'request-changes', label: '要求修改', cls: 'btn-warn' },
  ],
  approved: [{ action: 'archive', label: '归档', cls: 'btn-archive' }],
  rejected: [{ action: 'archive', label: '归档', cls: 'btn-archive' }],
}

const isArchived = computed(() => task.value?.status === 'archived')

const availableActions = computed(() => {
  if (!task.value || isArchived.value) return []
  return ACTION_MAP[task.value.status] || []
})

function runTypeLabel(t: string) {
  return AGENT_RUN_TYPE_LABELS[t] || t
}

function formatTime(ts: string | null | undefined) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString()
}

function formatArtifactIds(ids: number[] | undefined) {
  return ids && ids.length ? ids.join(', ') : '-'
}

function formatSummary(summary: Record<string, unknown> | null | undefined) {
  if (!summary || Object.keys(summary).length === 0) return '-'
  return JSON.stringify(summary)
}

function formatConfidence(value: number | null | undefined) {
  if (typeof value !== 'number') return '-'
  return `${Math.round(value * 100)}%`
}

const dryRunBlockedReasons = computed(() => {
  const gate = realAiDryRunResult.value?.safety_gate
  if (!gate) return ''
  return aiDispatchBlockedReasons(gate)
})

const executeArtifactNames = computed(() => {
  const artifacts = realAiExecuteResult.value?.artifacts || []
  const names = artifacts.map((artifact) => String(artifact.filename || artifact.id || JSON.stringify(artifact)))
  return names.length ? names : ['-']
})

const sandboxGateStepNames = computed(() => {
  const steps = realAiExecuteResult.value?.steps || []
  return steps
    .filter((step) => /sandbox|gate/i.test(`${step.step} ${step.details || ''}`))
    .map((step) => `${step.step}: ${step.status}${step.details ? ` (${step.details})` : ''}`)
})

function formatHandoffDetails(packet: AiHandoffPreviewResponse) {
  return JSON.stringify({
    current_master_commit_hint: packet.current_master_commit_hint,
    required_handoff_docs: ['AGENTS.md'],
    project_snapshot: packet.project_snapshot,
    current_task_summary: packet.current_task_summary,
    recent_capabilities: packet.recent_capabilities,
    current_pr_summary: packet.current_pr_summary,
    recent_dispatch_summary: packet.recent_dispatch_summary,
    answer_synthesis_summary: packet.answer_synthesis_summary,
    safety_rules: packet.safety_rules,
    next_recommended_steps: packet.next_recommended_steps,
    source_ids: packet.source_ids,
    safety_notes: packet.safety_notes,
  }, null, 2)
}

function buildAiDispatchRequest(): AiDispatchRequest | null {
  if (!task.value) return null
  return {
    task_goal: realAiTaskGoal.value || defaultRealAiTaskGoal(),
    module_name: task.value.project_name || 'task_detail',
    task_type: 'task_detail_real_ai_run',
    mode: realAiMode.value,
    task_id: task.value.id,
    project_id: task.value.project_id,
  }
}

function defaultRealAiTaskGoal() {
  if (!task.value) return ''
  const description = task.value.description ? `\n\n${task.value.description}` : ''
  return `${task.value.title}${description}`
}

function aiDispatchBlockedReasons(gate: AiDispatchSafetyGate) {
  const reasons: string[] = []
  if (!gate.execution_enabled) reasons.push('AI_EXECUTION_ENABLED 未开启')
  if (!gate.openai_key_present) reasons.push('OPENAI_API_KEY 缺失')
  if (!gate.provider_allowed) reasons.push('openai 不在 allowlist')
  if (!gate.mode_valid) reasons.push('mode 不合法')
  if (!gate.budget_ok) reasons.push('prompt budget 超限')
  if (!gate.gate_passed) reasons.push('safety gate blocked')
  return reasons
}

function pipelineStatusLabel(status: string) {
  const labels: Record<string, string> = {
    succeeded: 'succeeded',
    sandbox_failed: 'sandbox failed / blocked',
    sandbox_gate_blocked: 'gate blocked',
    ai_failed: 'AI failed',
  }
  return labels[status] || status
}

function formatSafetyGate(gate: AiDispatchSafetyGate) {
  return JSON.stringify(gate, null, 2)
}

onMounted(async () => {
  agents.value = await fetchAgents()
  await refresh()
})

async function refresh() {
  const id = Number(route.params.id)
  task.value = await taskStore.fetchTask(id)
  realAiTaskGoal.value = defaultRealAiTaskGoal()
  agentRuns.value = await fetchAgentRuns(id)
  agentReviews.value = await fetchAgentReviews(id)
  approvalDecisions.value = await fetchApprovalDecisions(id)
  await loadDispatchBatches(id)
  await loadAiHandoff()
  codeContext.value = await fetchCodeContext(id)
  sandboxResults.value = await fetchSandboxResults(id)
  applyResult.value = null
  await loadSandboxGate()
}

async function runAiDryRun() {
  const body = buildAiDispatchRequest()
  if (!body) return
  realAiLoading.value = true
  realAiError.value = ''
  try {
    realAiDryRunResult.value = await dryRunAiDispatch(body)
  } catch (e: any) {
    realAiDryRunResult.value = null
    realAiError.value = e.message || 'AI dry-run failed'
  } finally {
    realAiLoading.value = false
  }
}

async function executeRealAiRun() {
  const body = buildAiDispatchRequest()
  if (!body) return
  realAiLoading.value = true
  realAiError.value = ''
  try {
    realAiExecuteResult.value = await executeAiDispatch(body)
    await refreshAfterRealAiRun()
  } catch (e: any) {
    realAiExecuteResult.value = null
    realAiError.value = e.message || 'AI execute failed'
  } finally {
    realAiLoading.value = false
  }
}

async function refreshAfterRealAiRun() {
  if (!task.value) return
  const id = task.value.id
  agentRuns.value = await fetchAgentRuns(id)
  agentReviews.value = await fetchAgentReviews(id)
  await loadDispatchBatches(id)
  await loadAiHandoff()
  sandboxResults.value = await fetchSandboxResults(id)
  await loadSandboxGate()
}

async function loadDispatchBatches(id: number) {
  dispatchBatchError.value = ''
  try {
    dispatchBatches.value = await fetchDispatchBatches(id)
    const latestBatch = dispatchBatches.value[dispatchBatches.value.length - 1]
    if (latestBatch) {
      await loadAnswerSynthesis(id, latestBatch.dispatch_batch_id)
    } else {
      answerSynthesis.value = null
      answerSynthesisError.value = ''
    }
  } catch (e: any) {
    dispatchBatches.value = []
    answerSynthesis.value = null
    dispatchBatchError.value = e.message || '多 AI Dispatch 记录加载失败'
  }
}

async function loadAnswerSynthesis(taskId: number, dispatchBatchId?: number | null) {
  if (!dispatchBatchId) {
    answerSynthesis.value = null
    answerSynthesisError.value = ''
    return
  }
  answerSynthesisLoading.value = true
  answerSynthesisError.value = ''
  try {
    answerSynthesis.value = await previewAnswerSynthesis({
      task_id: taskId,
      dispatch_batch_id: dispatchBatchId,
      include_artifacts: true,
      max_artifact_chars: 2000,
    })
  } catch (e: any) {
    answerSynthesis.value = null
    answerSynthesisError.value = e.message || '多 AI 综合结论加载失败'
  } finally {
    answerSynthesisLoading.value = false
  }
}

async function refreshAnswerSynthesis() {
  const latestBatch = dispatchBatches.value[dispatchBatches.value.length - 1]
  if (!task.value || !latestBatch) return
  await loadAnswerSynthesis(task.value.id, latestBatch.dispatch_batch_id)
}

async function loadAiHandoff() {
  if (!task.value?.project_id || !task.value?.id) {
    aiHandoff.value = null
    aiHandoffError.value = ''
    return
  }
  aiHandoffLoading.value = true
  aiHandoffError.value = ''
  try {
    aiHandoff.value = await previewAiHandoff({
      project_id: task.value.project_id,
      task_id: task.value.id,
      include_recent_batches: true,
      include_answer_synthesis: true,
      include_safety_rules: true,
      max_chars: 12000,
    })
  } catch (e: any) {
    aiHandoff.value = null
    aiHandoffError.value = e.message || 'AI 接管包生成失败'
  } finally {
    aiHandoffLoading.value = false
  }
}

async function refreshAiHandoff() {
  await loadAiHandoff()
}

async function copyNextAiPrompt() {
  if (!aiHandoff.value?.next_ai_prompt) return
  try {
    await navigator.clipboard.writeText(aiHandoff.value.next_ai_prompt)
    aiHandoffCopyMessage.value = 'next_ai_prompt 已复制'
  } catch {
    aiHandoffCopyMessage.value = '复制失败，请手动选择文本'
  }
}

async function refreshSandboxGate() {
  const id = Number(route.params.id)
  sandboxGateLoading.value = true
  try {
    sandboxGate.value = await evaluateSandboxGate(id)
  } catch {
    sandboxGate.value = null
  } finally {
    sandboxGateLoading.value = false
  }
}

async function loadSandboxGate() {
  const id = Number(route.params.id)
  try {
    sandboxGate.value = await fetchSandboxGate(id)
  } catch {
    sandboxGate.value = null
  }
}

function parseGovernance(r: any): any {
  if (!r.raw_result_json) return null
  try {
    const p = JSON.parse(r.raw_result_json)
    return p.governance || null
  } catch { return null }
}

function parseTrace(r: any): any {
  if (!r.raw_result_json) return null
  try {
    const p = JSON.parse(r.raw_result_json)
    return p.trace || null
  } catch { return null }
}

async function handleAction(action: string) {
  if (action === 'submit-result') {
    showResultForm.value = true
    return
  }
  await doTransition(action)
}

async function confirmSubmitResult() {
  if (actionLoading.value) return
  await doTransition('submit-result', { result_summary: resultSummary.value })
  showResultForm.value = false
  resultSummary.value = ''
}

async function doTransition(action: string, extra: Record<string, any> = {}) {
  actionLoading.value = true
  try {
    await taskStore.transitionTask(task.value.id, action, { actor: 'human', ...extra })
    await refresh()
  } catch (e: any) {
    alert(e.message)
  } finally {
    actionLoading.value = false
  }
}


// Agent Run actions
async function handleCreateAgentRun() {
  if (!agentRunForm.value.agent_id) return
  try {
    await createAgentRun(task.value.id, agentRunForm.value)
    agentRunForm.value = { agent_id: 0, run_type: 'plan', input_prompt: '', branch: '' }
    showAgentRunForm.value = false
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

async function startAgentRun(r: AgentRun) {
  try {
    await updateAgentRun(task.value.id, r.id, { status: 'running' })
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

async function cancelAgentRun(r: AgentRun) {
  try {
    await updateAgentRun(task.value.id, r.id, { status: 'canceled' })
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

function showSubmitResult(r: AgentRun) {
  submitFormRunId.value = r.id
  submitForm.value = { status: 'succeeded' as const, output_summary: '', error_message: '', output_diff: '', output_log: '', raw_result_json: '' }
}

async function confirmSubmitRunResult(r: AgentRun) {
  if (actionLoading.value) return
  actionLoading.value = true
  try {
    await submitAgentRunResult(task.value.id, r.id, submitForm.value)
    submitFormRunId.value = null
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  } finally {
    actionLoading.value = false
  }
}

// Sandbox actions
async function handleSandboxApply(runId: number) {
  if (sandboxLoading.value) return
  sandboxLoading.value = true
  applyResult.value = null
  try {
    applyResult.value = await applyPatchInSandbox(task.value.id, runId)
    sandboxResults.value = await fetchSandboxResults(task.value.id)
  } catch (e: any) {
    applyResult.value = { success: false, message: e.message, report: { applied: false, changed_files: [], warnings: [], errors: [e.message] }, before_after_previews: {} }
  } finally {
    sandboxLoading.value = false
  }
}

// Agent Review actions
async function handleCreateAgentReview() {
  if (!agentReviewForm.value.reviewer_agent_id || !agentReviewForm.value.agent_run_id) return
  try {
    await createAgentReview(task.value.id, agentReviewForm.value.agent_run_id, {
      reviewer_agent_id: agentReviewForm.value.reviewer_agent_id,
      decision: agentReviewForm.value.decision,
      risk_level: agentReviewForm.value.risk_level,
      comments: agentReviewForm.value.comments || null,
      confidence_score: agentReviewForm.value.confidence_score,
      issues_json: agentReviewForm.value.issues_json || null,
    })
    agentReviewForm.value = { reviewer_agent_id: 0, decision: 'approved', risk_level: 'low', comments: '', confidence_score: null, agent_run_id: 0, issues_json: '' }
    showAgentReviewForm.value = false
    agentReviews.value = await fetchAgentReviews(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.detail-header h1 { font-size: 24px; font-weight: 700; }
.meta { display: flex; gap: 8px; align-items: center; margin-top: 4px; color: var(--color-text-secondary); font-size: 14px; flex-wrap: wrap; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; padding: 16px; }
.archived-label { color: var(--color-text-secondary); font-size: 13px; font-style: italic; }
.result-form { margin-bottom: 16px; padding: 20px; }
.result-form h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.result-form textarea { width: 100%; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; font-family: inherit; resize: vertical; }
.form-actions { display: flex; gap: 8px; margin-top: 8px; }
.detail-body { display: flex; flex-direction: column; gap: 20px; }
.detail-body section h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border); }
.description-text { white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; color: var(--color-text-secondary); }
.real-ai-run { border-left: 3px solid var(--color-primary); }
.real-ai-form { display: grid; grid-template-columns: minmax(160px, 220px) 1fr; gap: 12px; align-items: start; margin-top: 12px; }
.real-ai-form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.real-ai-form textarea { min-height: 90px; resize: vertical; }
.real-ai-result { margin-top: 12px; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; display: flex; flex-direction: column; gap: 8px; }
.real-ai-result pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--color-text-secondary); }
.real-ai-sandbox { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; display: flex; flex-direction: column; gap: 6px; }
.real-ai-sandbox strong { font-size: 13px; }
.roles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 14px; }
.loading { text-align: center; padding: 60px; color: var(--color-text-secondary); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border); }
.section-header h2 { font-size: 16px; font-weight: 600; margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
.section-note { font-size: 12px; color: var(--color-text-secondary); font-style: italic; margin-bottom: 12px; }
.inline-form { background: var(--color-bg); border-radius: var(--radius); padding: 16px; display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.inline-form label { font-size: 13px; }
.inline-form input, .inline-form select, .inline-form textarea { width: 100%; }
.agent-run-item { padding: 12px; margin-top: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.agent-run-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.agent-run-header strong { font-size: 14px; }
.run-status-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.run-status-badge.queued { background: #f5f5f5; color: #616161; }
.run-status-badge.running { background: #e3f2fd; color: #1565c0; }
.run-status-badge.succeeded { background: #e8f5e9; color: #2e7d32; }
.run-status-badge.failed { background: #ffebee; color: #c62828; }
.run-status-badge.canceled { background: #f5f5f5; color: #9e9e9e; }
.run-status-badge.human_required { background: #fce4ec; color: #c62828; }
.run-risk { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.run-risk.low { background: #e8f5e9; color: #2e7d32; }
.run-risk.medium { background: #fff3e0; color: #e65100; }
.run-risk.high { background: #ffebee; color: #c62828; }
.run-risk.critical { background: #fce4ec; color: #b71c1c; }
.run-attempt { font-size: 12px; color: var(--color-text-secondary); margin-left: auto; }
.agent-run-meta { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 4px; }
.run-prompt { font-size: 13px; color: var(--color-text-secondary); background: #f5f5f5; padding: 8px; border-radius: 6px; margin: 4px 0; white-space: pre-wrap; }
.run-output { font-size: 13px; color: var(--color-text); margin: 4px 0; white-space: pre-wrap; }
.run-error { font-size: 13px; color: var(--color-danger); margin: 4px 0; white-space: pre-wrap; }
.run-diff { margin: 4px 0; }
.run-field { margin: 4px 0; }
.field-label { font-size: 11px; color: var(--color-text-secondary); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.run-pre { background: #f5f5f5; padding: 8px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; margin-top: 4px; }
.agent-run-actions { display: flex; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--color-border); }
.agent-review-item { padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.agent-review-item:last-child { border-bottom: none; }
.agent-review-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.review-decision { padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.review-decision.approved { background: #e8f5e9; color: #2e7d32; }
.review-decision.rejected { background: #ffebee; color: #c62828; }
.review-decision.changes_requested { background: #fff3e0; color: #e65100; }
.review-decision.human_required { background: #fce4ec; color: #c62828; }
.review-risk { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.review-risk.low { background: #e8f5e9; color: #2e7d32; }
.review-risk.medium { background: #fff3e0; color: #e65100; }
.review-risk.high { background: #ffebee; color: #c62828; }
.review-risk.critical { background: #fce4ec; color: #b71c1c; }
.review-confidence { font-size: 12px; color: var(--color-text-secondary); }
.review-time { font-size: 12px; color: var(--color-text-secondary); margin-left: auto; }
.review-meta { font-size: 12px; color: var(--color-text-secondary); }
.review-comments { font-size: 13px; color: var(--color-text-secondary); margin-top: 4px; }
.run-select { max-width: 100%; }
.gov-section { margin: 8px 0; padding: 8px; background: #fafafa; border-radius: 6px; border: 1px solid var(--color-border); }
.gov-grid { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.gov-tag { padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; }
.gov-pass { background: #e8f5e9; color: #2e7d32; }
.gov-fail { background: #ffebee; color: #c62828; }
.gov-human { background: #f8bbd0; color: #000000; }
.gov-risk-low { background: #e8f5e9; color: #2e7d32; }
.gov-risk-medium { background: #ffcc80; color: #000000; }
.gov-risk-high { background: #ffebee; color: #c62828; }
.gov-risk-critical { background: #fce4ec; color: #b71c1c; }
.gov-info { background: #e3f2fd; color: #1565c0; }
.gov-issues { margin-top: 4px; }
.gov-error { font-size: 12px; color: #c62828; margin: 2px 0; }
.gov-warn { font-size: 12px; color: #e65100; margin: 2px 0; }
.gov-reason { font-size: 13px; color: var(--color-text-secondary); margin-top: 4px; white-space: pre-wrap; }
.gov-time { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
.gov-status-item { padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.gov-status-item:last-child { border-bottom: none; }
.gov-status-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.gov-status-header strong { font-size: 14px; }
.gov-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.label-badge { padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; }
.label-ai { background: #e8f5e9; color: #2e7d32; }
.label-provider { background: #e3f2fd; color: #1565c0; }
.label-redacted { background: #fff3e0; color: #e65100; }
.label-merged { background: #ce93d8; color: #000000; }
.label-exec { background: #ffcdd2; color: #b71c1c; }
.label-applied { background: #ffcdd2; color: #b71c1c; }
.approval-decision-item { padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.approval-decision-item:last-child { border-bottom: none; }
.approval-decision-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.artifact-note { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--color-border); }


/* Multi-AI Answer Workspace */
.workspace-readonly { font-size: 12px; color: var(--color-text-secondary); font-weight: 500; }
.workspace-safety { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.dispatch-batch-list { display: flex; flex-direction: column; gap: 12px; }
.dispatch-batch-item { padding: 12px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.dispatch-batch-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 6px; }
.dispatch-batch-meta { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--color-text-secondary); margin-bottom: 10px; word-break: break-word; }
.dispatch-job-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.dispatch-job-card { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.dispatch-job-header { display: flex; gap: 8px; align-items: flex-start; justify-content: space-between; margin-bottom: 6px; }
.dispatch-job-header strong { font-size: 13px; line-height: 1.4; }
.dispatch-job-meta { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--color-text-secondary); margin: 6px 0; word-break: break-word; }
.dispatch-job-hashes { display: flex; flex-direction: column; gap: 3px; margin: 6px 0; }
.dispatch-job-hashes code { font-size: 11px; white-space: normal; word-break: break-all; color: var(--color-text-secondary); }
.run-status-badge.blocked { background: #fff3e0; color: #e65100; }
.run-status-badge.ready { background: #e8f5e9; color: #1b5e20; }
.run-status-badge.attention_required { background: #fff3e0; color: #e65100; }
.run-status-badge.empty { background: #eeeeee; color: #424242; }

/* Answer Synthesis */
.answer-synthesis-workspace { margin-top: 12px; }
.synthesis-panel { display: flex; flex-direction: column; gap: 12px; }
.synthesis-metrics { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 12px; color: var(--color-text-secondary); }
.synthesis-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.synthesis-list { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.synthesis-list strong, .synthesis-artifacts strong { display: block; margin-bottom: 6px; font-size: 13px; }
.synthesis-list ul { margin: 0; padding-left: 18px; }
.synthesis-list li { margin: 3px 0; font-size: 12px; line-height: 1.45; word-break: break-word; }
.synthesis-list p { margin: 0; color: var(--color-text-secondary); }
.synthesis-source-ids { display: flex; flex-direction: column; gap: 4px; }
.synthesis-source-ids code { font-size: 11px; white-space: normal; word-break: break-all; color: var(--color-text-secondary); }
.synthesis-artifacts { display: flex; flex-direction: column; gap: 8px; }
.synthesis-artifact-item { padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.synthesis-artifact-item span { font-size: 12px; color: var(--color-text-secondary); }
.synthesis-artifact-item pre { margin-top: 6px; max-height: 160px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; }
/* AI Handoff */
.ai-handoff-workspace { margin-top: 12px; }
.section-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.handoff-panel { display: flex; flex-direction: column; gap: 12px; }
.handoff-details { margin: 0; max-height: 360px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.45; color: var(--color-text-secondary); padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.handoff-prompt-block { display: flex; flex-direction: column; gap: 6px; }
.handoff-prompt-block textarea { min-height: 260px; width: 100%; resize: vertical; border: 1px solid var(--color-border); border-radius: var(--radius); padding: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.45; color: var(--color-text); background: #fff; }
.copy-message { margin: 0 0 8px; color: var(--color-success); font-size: 12px; }
.synthesis-list pre { margin: 0; max-height: 180px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--color-text-secondary); }
/* Code Context */
.context-meta { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.context-stat { font-size: 12px; color: var(--color-text-secondary); margin-left: auto; }
.context-file-item { padding: 8px; margin-bottom: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.context-file-header { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
.context-lang { font-size: 11px; color: var(--color-text-secondary); background: #f5f5f5; padding: 2px 8px; border-radius: 8px; }
.context-file-preview { background: #f5f5f5; padding: 8px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 150px; overflow-y: auto; }

/* Patch Sandbox */
.sandbox-apply-area { margin: 12px 0; padding: 12px; background: #fafafa; border: 1px solid var(--color-border); border-radius: var(--radius); }
.sandbox-label-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.sandbox-run-select { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.sandbox-run-select label { font-size: 13px; }
.sandbox-run-select select { padding: 6px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 13px; min-width: 280px; }
.sandbox-archived-note { font-size: 12px; color: var(--color-text-secondary); font-style: italic; margin-top: 8px; }
.sandbox-result { margin-top: 12px; padding: 12px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.sandbox-result-header { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; font-size: 14px; }
.sandbox-errors { margin: 4px 0; }
.sandbox-error-item { display: block; font-size: 12px; color: #c62828; padding: 2px 0; }
.sandbox-warnings { margin: 4px 0; }
.sandbox-warn-item { display: block; font-size: 12px; color: #e65100; padding: 2px 0; }
.sandbox-changed-files h3, .sandbox-previews h3, .sandbox-artifacts h3 { font-size: 14px; font-weight: 600; margin: 12px 0 8px; }
.sandbox-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.sandbox-table th, .sandbox-table td { padding: 6px 8px; border: 1px solid var(--color-border); text-align: left; }
.sandbox-table th { background: #f5f5f5; font-weight: 600; }
.cf-path { font-family: monospace; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cf-num { font-family: monospace; text-align: right; }
.cf-add { color: #2e7d32; }
.cf-del { color: #c62828; }
.cf-sha { font-family: monospace; font-size: 11px; }
.sandbox-previews { margin-top: 12px; }
.sandbox-preview-pair { display: flex; gap: 12px; margin-bottom: 12px; }
.preview-col { flex: 1; }
.preview-label { display: block; font-size: 11px; font-weight: 600; color: var(--color-text-secondary); margin-bottom: 4px; text-transform: uppercase; }
.preview-code { background: #f5f5f5; padding: 8px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
.sandbox-artifacts { margin-top: 12px; }
.sandbox-artifact-item { padding: 8px; margin-bottom: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.sandbox-artifact-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.sandbox-artifact-meta { font-size: 11px; color: var(--color-text-secondary); }
.sandbox-artifact-sha { font-size: 10px; color: var(--color-text-secondary); }
.sandbox-artifact-content { background: #f5f5f5; padding: 8px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; margin-top: 4px; }

/* Sandbox Gate */
.sandbox-gate-loading { font-size: 13px; color: var(--color-text-secondary); padding: 8px 0; }
.sandbox-gate-result { margin-top: 8px; }
.sandbox-gate-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 14px; margin-bottom: 8px; }
.sandbox-gate-reasons { margin: 8px 0; padding: 8px 12px; background: #fff3e0; border: 1px solid #ffe0b2; border-radius: var(--radius); }
.sandbox-gate-reasons h3 { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.sandbox-gate-reasons ul { margin: 0; padding-left: 16px; }
.sandbox-gate-reasons li { font-size: 12px; margin: 2px 0; }
.sandbox-gate-actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.sandbox-gate-pending-note { font-size: 11px; color: var(--color-text-secondary); font-style: italic; }

.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-approve { background: #4caf50; color: #fff; border-color: #4caf50; }
.btn-reject { background: #f44336; color: #fff; border-color: #f44336; }
.btn-warn { background: #ff9800; color: #fff; border-color: #ff9800; }
.btn-archive { background: #607d8b; color: #fff; border-color: #607d8b; }
.btn-sm { padding: 6px 14px; font-size: 13px; }
</style>
