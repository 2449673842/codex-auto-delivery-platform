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
          <span class="label-badge label-ai">model backend configured</span>
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
            <span>model: {{ realAiDryRunResult.model }}</span>
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

      <!-- Browser AI -->
      <section class="card browser-ai-run">
        <div class="section-header">
          <h2>Browser AI / 网页 AI</h2>
          <span class="workspace-readonly">Local browser provider</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-provider">Local browser only</span>
          <span class="label-badge label-ai">User-controlled login</span>
          <span class="label-badge label-redacted">No password stored</span>
          <span class="label-badge label-redacted">No cookies stored in DB</span>
          <span class="label-badge label-redacted">No captcha bypass</span>
          <span class="label-badge label-provider">No hidden API</span>
          <span class="label-badge label-merged">No auto merge</span>
        </div>
        <p class="browser-ai-help">
          If the input box or send button is not found, check selectors. If stable response capture times out, the page may still be generating or manual login may be required.
        </p>
        <p class="browser-ai-help">
          Complete login in the opened browser, then retry Execute. The platform will not auto login or store passwords/cookies.
        </p>
        <p class="browser-ai-help">
          Built-in selectors are best-effort and may break when the website changes. Switch to custom if needed.
        </p>
        <div class="browser-ai-form">
          <label>
            provider
            <select v-model="browserAiForm.provider" @change="applyBrowserAiProfile">
              <option v-for="profile in browserAiProfiles" :key="profile.provider" :value="profile.provider">
                {{ profile.display_name }}
              </option>
            </select>
          </label>
          <label>
            profile_status
            <input :value="selectedBrowserAiProfileStatus" readonly />
          </label>
          <label>
            prompt_source
            <select v-model="browserAiForm.prompt_source">
              <option value="task_goal">task_goal</option>
              <option value="handoff_packet">handoff_packet</option>
              <option value="answer_synthesis">answer_synthesis</option>
              <option value="custom_prompt">custom_prompt</option>
            </select>
          </label>
          <label class="wide">
            target_url
            <input v-model="browserAiForm.target_url" placeholder="http://127.0.0.1:9999/mock-browser-ai" />
          </label>
          <label>
            input_selector
            <input v-model="browserAiForm.input_selector" placeholder="textarea[name='prompt']" />
          </label>
          <label>
            send_selector
            <input v-model="browserAiForm.send_selector" placeholder="button[data-send]" />
          </label>
          <label>
            response_selector
            <input v-model="browserAiForm.response_selector" placeholder="[data-answer]" />
          </label>
          <label>
            scroll_container_selector
            <input v-model="browserAiForm.scroll_container_selector" placeholder="optional conversation scroller" />
          </label>
          <label>
            copy_button_selector
            <input v-model="browserAiForm.copy_button_selector" placeholder="optional copy full answer button" />
          </label>
          <label>
            login_hint_selector
            <input v-model="browserAiForm.login_hint_selector" placeholder="optional login hint selector" />
          </label>
          <label>
            timeout_seconds
            <input v-model.number="browserAiForm.timeout_seconds" type="number" min="1" max="600" />
          </label>
          <label class="wide" v-if="browserAiForm.prompt_source === 'custom_prompt'">
            custom_prompt
            <textarea v-model="browserAiForm.custom_prompt" rows="4"></textarea>
          </label>
          <div class="form-actions wide">
            <button class="btn btn-sm" @click="runBrowserAiDryRun" :disabled="browserAiLoading || !task">Dry-run</button>
            <button class="btn btn-primary btn-sm" @click="executeBrowserAiRun" :disabled="browserAiLoading || !task">Execute</button>
          </div>
        </div>
        <p v-if="browserAiError" class="run-error">{{ browserAiError }}</p>
        <div v-if="browserAiDryRunResult" class="real-ai-result">
          <strong>browser dry-run result</strong>
          <div class="dispatch-job-hashes">
            <code>prompt_hash: {{ browserAiDryRunResult.prompt_hash || '-' }}</code>
          </div>
          <div class="dispatch-job-meta">
            <span>status: {{ browserAiDryRunResult.status }}</span>
            <span>browser_opened={{ browserAiDryRunResult.browser_opened }}</span>
            <span>persisted={{ browserAiDryRunResult.persisted }}</span>
          </div>
          <pre>{{ formatBrowserAiSafetyGate(browserAiDryRunResult.safety_gate) }}</pre>
          <p v-if="browserAiDryRunResult.error_message" class="run-error">{{ browserAiDryRunResult.error_message }}</p>
          <div class="browser-ai-steps">
            <strong>run steps</strong>
            <ul>
              <li v-for="step in browserAiDryRunResult.steps" :key="`dry-${step.name}`" :class="['browser-ai-step', step.status]">
                <span class="step-name">{{ step.name }}</span>
                <span class="step-status">{{ step.status }}</span>
                <span class="step-message">
                  <template v-if="step.status === 'failed'">Failed at {{ step.name }}: </template>{{ step.message || stepHint(step.name, step.status) }}
                </span>
              </li>
            </ul>
          </div>
        </div>
        <div v-if="browserAiExecuteResult" class="real-ai-result">
          <strong>browser execute result</strong>
          <div class="dispatch-job-meta">
            <span>status: {{ browserAiExecuteResult.status }}</span>
            <span>agent_run_id: {{ browserAiExecuteResult.agent_run_id || '-' }}</span>
            <span>artifact_id: {{ browserAiExecuteResult.artifact_id || '-' }}</span>
            <span>browser_opened={{ browserAiExecuteResult.browser_opened }}</span>
            <span>persisted={{ browserAiExecuteResult.persisted }}</span>
          </div>
          <p v-if="browserAiExecuteResult.answer_preview" class="run-output">{{ browserAiExecuteResult.answer_preview }}</p>
          <p v-if="browserAiExecuteResult.error_message" class="run-error">{{ browserAiExecuteResult.error_message }}</p>
          <p v-if="browserAiLoginRequired" class="run-error">
            Manual login may be required. Complete login in the opened browser, then retry Execute.
          </p>
          <div v-if="browserAiRefreshMessages.length" class="browser-ai-refresh-status">
            <span v-for="message in browserAiRefreshMessages" :key="message" class="label-badge label-ai">{{ message }}</span>
          </div>
          <div class="browser-ai-steps">
            <strong>run steps</strong>
            <ul>
              <li v-for="step in browserAiExecuteResult.steps" :key="`exec-${step.name}`" :class="['browser-ai-step', step.status]">
                <span class="step-name">{{ step.name }}</span>
                <span class="step-status">{{ step.status }}</span>
                <span class="step-message">
                  <template v-if="step.status === 'failed'">Failed at {{ step.name }}: </template>{{ step.message || stepHint(step.name, step.status) }}
                </span>
              </li>
            </ul>
            <p v-if="browserAiFailedStep" class="run-error">
              Failed at {{ browserAiFailedStep.name }}: {{ browserAiFailedStep.message || stepHint(browserAiFailedStep.name, browserAiFailedStep.status) }}
            </p>
          </div>
        </div>
      </section>

      <!-- Multi-AI Evidence Run -->
      <section class="card multi-ai-evidence-run">
        <div class="section-header">
          <h2>Multi-AI Evidence Run / 多 AI 证据运行</h2>
          <span class="workspace-readonly">Evidence collection only</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Multi-AI Evidence Run is evidence collection, not code execution</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-exec">No PR / CI / Sonar / Deploy</span>
          <span class="label-badge label-merged">No auto approve / merge</span>
        </div>
        <p class="section-note">{{ multiAiForm.concurrency_limit }} job concurrency requested. {{ multiAiConcurrencyNote }}</p>
        <div class="multi-ai-form">
          <label>
            mode
            <select v-model="multiAiForm.mode">
              <option value="broadcast">broadcast</option>
              <option value="routed">routed</option>
            </select>
          </label>
          <label>
            prompt_source
            <select v-model="multiAiForm.prompt_source">
              <option value="task_goal">task_goal</option>
              <option value="handoff_packet">handoff_packet</option>
              <option value="answer_synthesis">answer_synthesis</option>
              <option value="custom_prompt">custom_prompt</option>
            </select>
          </label>
          <label>
            concurrency_limit
            <input v-model.number="multiAiForm.concurrency_limit" type="number" min="1" max="8" />
          </label>
          <label class="wide" v-if="multiAiForm.prompt_source === 'custom_prompt'">
            custom_prompt
            <textarea v-model="multiAiForm.custom_prompt" rows="4" placeholder="Prompt sent to all evidence jobs"></textarea>
          </label>

          <div v-if="multiAiForm.mode === 'broadcast'" class="wide provider-picker">
            <strong>providers</strong>
            <label v-for="provider in evidenceProviderOptions" :key="provider.provider" class="checkbox-row">
              <input type="checkbox" :value="provider.provider" v-model="multiAiForm.providers" />
              <span>{{ provider.display_name }}</span>
            </label>
          </div>

          <div v-else class="wide routed-roles">
            <div class="section-header compact">
              <strong>routed roles</strong>
              <button class="btn btn-sm" @click="addEvidenceRole" type="button">Add role</button>
            </div>
            <div v-for="(role, index) in multiAiForm.roles" :key="`evidence-role-${index}`" class="routed-role-row">
              <label>
                role
                <input v-model="role.role" placeholder="backend" />
              </label>
              <label>
                provider
                <select v-model="role.provider">
                  <option v-for="provider in evidenceProviderOptions" :key="provider.provider" :value="provider.provider">
                    {{ provider.display_name }}
                  </option>
                </select>
              </label>
              <label class="role-prompt">
                prompt
                <input v-model="role.prompt" placeholder="Check this area only" />
              </label>
              <button class="btn btn-sm" @click="removeEvidenceRole(index)" type="button" :disabled="multiAiForm.roles.length <= 1">Remove</button>
            </div>
          </div>

          <details class="wide">
            <summary>advanced custom selector fallback</summary>
            <div class="selector-grid">
              <label>target_url<input v-model="multiAiForm.target_url" /></label>
              <label>input_selector<input v-model="multiAiForm.input_selector" /></label>
              <label>send_selector<input v-model="multiAiForm.send_selector" /></label>
              <label>response_selector<input v-model="multiAiForm.response_selector" /></label>
              <label>scroll_container_selector<input v-model="multiAiForm.scroll_container_selector" /></label>
              <label>copy_button_selector<input v-model="multiAiForm.copy_button_selector" /></label>
              <label>login_hint_selector<input v-model="multiAiForm.login_hint_selector" /></label>
              <label>timeout_seconds<input v-model.number="multiAiForm.timeout_seconds" type="number" min="1" max="600" /></label>
            </div>
          </details>

          <div class="form-actions wide">
            <button class="btn btn-sm" @click="previewEvidenceRun" :disabled="multiAiLoading || !task">Preview</button>
            <button class="btn btn-primary btn-sm" @click="executeEvidenceRun" :disabled="multiAiLoading || !task">Execute</button>
          </div>
        </div>
        <p v-if="multiAiError" class="run-error">{{ multiAiError }}</p>
        <div v-if="multiAiPreviewResult" class="real-ai-result evidence-result">
          <strong>preview result</strong>
          <div class="dispatch-job-meta">
            <span>mode: {{ multiAiPreviewResult.mode }}</span>
            <span>overall_status: {{ multiAiPreviewResult.overall_status }}</span>
            <span>estimated_job_count: {{ multiAiPreviewResult.estimated_job_count }}</span>
            <span>persisted={{ multiAiPreviewResult.persisted }}</span>
            <span>read_only={{ multiAiPreviewResult.read_only }}</span>
          </div>
          <p v-if="multiAiPreviewResult.error_message" class="run-error">{{ multiAiPreviewResult.error_message }}</p>
          <pre>{{ formatEvidenceSafetyGate(multiAiPreviewResult.safety_gate) }}</pre>
          <div class="dispatch-job-grid">
            <div v-for="job in multiAiPreviewResult.jobs" :key="`preview-${job.sequence_no}-${job.provider}-${job.role}`" class="dispatch-job-card">
              <div class="dispatch-job-header">
                <strong>#{{ job.sequence_no }} {{ job.role }}</strong>
                <span class="run-status-badge" :class="job.status">{{ job.status }}</span>
              </div>
              <div class="dispatch-job-meta">
                <span>provider: {{ job.provider }}</span>
                <span>prompt_source: {{ job.prompt_source }}</span>
                <span>prompt_hash: {{ job.prompt_hash || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="multiAiExecuteResult" class="real-ai-result evidence-result">
          <strong>execute result</strong>
          <div class="dispatch-job-meta">
            <span>evidence_run_id: {{ multiAiExecuteResult.evidence_run_id || '-' }}</span>
            <span>dispatch_batch_id: {{ multiAiExecuteResult.dispatch_batch_id || '-' }}</span>
            <span>overall_status: {{ multiAiExecuteResult.overall_status }}</span>
            <span>persisted={{ multiAiExecuteResult.persisted }}</span>
            <span>synthesis_refreshed={{ multiAiExecuteResult.synthesis_refreshed }}</span>
            <span>synthesis_status: {{ multiAiExecuteResult.synthesis_status || '-' }}</span>
          </div>
          <div v-if="multiAiRefreshMessages.length" class="browser-ai-refresh-status">
            <span v-for="message in multiAiRefreshMessages" :key="message" class="label-badge label-ai">{{ message }}</span>
          </div>
          <div class="dispatch-job-grid">
            <div v-for="job in multiAiExecuteResult.jobs" :key="`exec-${job.sequence_no}-${job.provider}-${job.role}`" class="dispatch-job-card">
              <div class="dispatch-job-header">
                <strong>#{{ job.sequence_no }} {{ job.role }}</strong>
                <span class="run-status-badge" :class="job.status">{{ job.status }}</span>
              </div>
              <div class="dispatch-job-meta">
                <span>provider: {{ job.provider }}</span>
                <span>status: {{ job.status }}</span>
                <span>agent_run_id: {{ job.agent_run_id || '-' }}</span>
                <span>artifact_id: {{ job.artifact_id || '-' }}</span>
              </div>
              <p v-if="job.answer_preview" class="run-output">{{ job.answer_preview }}</p>
              <p v-if="job.error_message" class="run-error">{{ job.error_message }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Failure Evidence Packet Preview -->
      <section class="card failure-evidence-preview">
        <div class="section-header">
          <h2>Failure Evidence Packet Preview / 失败证据包预览</h2>
          <span class="workspace-readonly">Read-only preview</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Failure Evidence preview is read-only</span>
          <span class="label-badge label-provider">No provider call</span>
          <span class="label-badge label-provider">No Browser AI execution</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-exec">No PR / CI / Sonar / Deploy</span>
          <span class="label-badge label-merged">No auto approve / merge</span>
        </div>
        <div class="failure-evidence-form">
          <label>
            failure_type
            <select v-model="failureEvidenceForm.failure_type">
              <option value="sandbox_failed">sandbox_failed</option>
              <option value="sandbox_gate_blocked">sandbox_gate_blocked</option>
              <option value="verification_failed">verification_failed</option>
              <option value="ci_failed">ci_failed</option>
              <option value="sonar_failed">sonar_failed</option>
              <option value="review_blocked">review_blocked</option>
              <option value="browser_ai_failed">browser_ai_failed</option>
              <option value="multi_ai_evidence_partial">multi_ai_evidence_partial</option>
            </select>
          </label>
          <label>
            agent_run_id
            <input v-model.number="failureEvidenceForm.source.agent_run_id" type="number" min="1" placeholder="optional" />
          </label>
          <label>
            artifact_id
            <input v-model.number="failureEvidenceForm.source.artifact_id" type="number" min="1" placeholder="optional" />
          </label>
          <label>
            dispatch_batch_id
            <input v-model.number="failureEvidenceForm.source.dispatch_batch_id" type="number" min="1" placeholder="optional" />
          </label>
          <label>
            dispatch_job_id
            <input v-model.number="failureEvidenceForm.source.dispatch_job_id" type="number" min="1" placeholder="optional" />
          </label>
          <label>
            max_excerpt_chars
            <input v-model.number="failureEvidenceForm.max_excerpt_chars" type="number" min="200" max="12000" />
          </label>
          <div class="form-actions wide">
            <button class="btn btn-primary btn-sm" @click="previewFailureEvidence" :disabled="failureEvidenceLoading || !task">Preview</button>
          </div>
        </div>
        <p v-if="failureEvidenceError" class="run-error">{{ failureEvidenceError }}</p>
        <div v-if="failureEvidencePacket" class="real-ai-result failure-evidence-result">
          <strong>failure evidence packet</strong>
          <div class="dispatch-job-meta">
            <span>failure_type: {{ failureEvidencePacket.failure_type }}</span>
            <span>failed_step: {{ failureEvidencePacket.failed_step }}</span>
            <span>read_only={{ failureEvidencePacket.read_only }}</span>
            <span>persisted={{ failureEvidencePacket.persisted }}</span>
            <span>redaction_applied={{ failureEvidencePacket.redaction_status.redaction_applied }}</span>
            <span>truncated={{ failureEvidencePacket.redaction_status.truncated }}</span>
          </div>
          <div class="dispatch-job-meta">
            <span>related_agent_run_ids: {{ formatArtifactIds(failureEvidencePacket.related_agent_run_ids) }}</span>
            <span>related_artifact_ids: {{ formatArtifactIds(failureEvidencePacket.related_artifact_ids) }}</span>
            <span>related_dispatch_batch_id: {{ failureEvidencePacket.related_dispatch_batch_id || '-' }}</span>
            <span>related_dispatch_job_ids: {{ formatArtifactIds(failureEvidencePacket.related_dispatch_job_ids) }}</span>
          </div>
          <p v-if="failureEvidencePacket.failed_command_summary" class="run-output">{{ failureEvidencePacket.failed_command_summary }}</p>
          <div v-if="failureEvidencePacket.blocked_reasons.length" class="run-error">
            <span>blocked_reasons:</span>
            <span v-for="reason in failureEvidencePacket.blocked_reasons" :key="reason">{{ reason }}</span>
          </div>
          <div class="safety-notes">
            <span v-for="note in failureEvidencePacket.safety_notes" :key="note" class="label-badge label-ai">{{ note }}</span>
          </div>
          <pre>{{ formatFailureEvidencePacket(failureEvidencePacket) }}</pre>
        </div>
      </section>

      <!-- Repair Packet Generation -->
      <section class="card repair-packet-generation">
        <div class="section-header">
          <h2>Repair Packet Generation / 修复交接包生成</h2>
          <span class="workspace-readonly">Evidence-to-handoff only</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Repair Packet does not modify code</span>
          <span class="label-badge label-provider">Codex / OMX or user must execute repair</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-exec">No auto PR / merge / deploy</span>
          <span class="label-badge label-redacted">max_attempts defaults to 1</span>
        </div>
        <p class="section-note">Uses the current Failure Evidence Packet. Generate one before creating a repair packet.</p>
        <div class="repair-packet-form">
          <label>
            analysis_mode
            <select v-model="repairPacketForm.analysis_mode">
              <option value="broadcast">broadcast</option>
              <option value="routed">routed</option>
            </select>
          </label>
          <label v-if="repairPacketForm.analysis_mode === 'broadcast'">
            providers
            <select v-model="repairPacketForm.providers" multiple>
              <option v-for="profile in evidenceProviderOptions" :key="`repair-${profile.provider}`" :value="profile.provider">
                {{ profile.display_name }}
              </option>
            </select>
          </label>
          <label>
            max_attempts
            <input v-model.number="repairPacketForm.max_attempts" type="number" min="1" max="1" />
          </label>
          <div v-if="repairPacketForm.analysis_mode === 'routed'" class="routed-role-list">
            <strong>routed roles</strong>
            <div v-for="(role, index) in repairPacketForm.roles" :key="`repair-role-${index}`" class="routed-role-row">
              <input v-model="role.role" placeholder="role" />
              <select v-model="role.provider">
                <option v-for="profile in evidenceProviderOptions" :key="`repair-role-provider-${index}-${profile.provider}`" :value="profile.provider">
                  {{ profile.display_name }}
                </option>
              </select>
              <input v-model="role.prompt" placeholder="role prompt" />
              <button class="btn btn-sm" @click="removeRepairRole(index)" :disabled="repairPacketForm.roles.length <= 1">Remove</button>
            </div>
            <button class="btn btn-sm" @click="addRepairRole">+ Add role</button>
          </div>
          <div class="form-actions wide">
            <button class="btn btn-primary btn-sm" @click="generateRepairPacketFromEvidence" :disabled="repairPacketLoading || !failureEvidencePacket">
              Generate Repair Packet
            </button>
          </div>
        </div>
        <p v-if="repairPacketError" class="run-error">{{ repairPacketError }}</p>
        <div v-if="repairPacketResult" class="real-ai-result repair-packet-result">
          <strong>repair packet</strong>
          <div class="dispatch-job-meta">
            <span>repair_packet_artifact_id: {{ repairPacketResult.repair_packet_artifact_id || '-' }}</span>
            <span>human_decision_required={{ repairPacketResult.human_decision_required }}</span>
            <span>persisted={{ repairPacketResult.persisted }}</span>
            <span>analysis_status: {{ repairPacketResult.analysis_status }}</span>
            <span>max_attempts={{ repairPacketResult.max_attempts }}</span>
          </div>
          <p class="run-output">{{ repairPacketResult.failure_summary }}</p>
          <div v-if="repairPacketResult.suspected_root_causes.length" class="repair-list">
            <strong>suspected_root_causes</strong>
            <span v-for="item in repairPacketResult.suspected_root_causes" :key="item">{{ item }}</span>
          </div>
          <p v-if="repairPacketResult.recommended_fix_strategy" class="run-output">{{ repairPacketResult.recommended_fix_strategy }}</p>
          <div v-if="repairPacketResult.files_likely_involved.length" class="repair-list">
            <strong>files_likely_involved</strong>
            <span v-for="item in repairPacketResult.files_likely_involved" :key="item">{{ item }}</span>
          </div>
          <div v-if="repairPacketResult.commands_to_verify.length" class="repair-list">
            <strong>commands_to_verify</strong>
            <span v-for="item in repairPacketResult.commands_to_verify" :key="item">{{ item }}</span>
          </div>
          <div v-if="repairPacketResult.risks.length" class="run-error">
            <span>risks:</span>
            <span v-for="risk in repairPacketResult.risks" :key="risk">{{ risk }}</span>
          </div>
          <div v-if="repairPacketResult.do_not_do.length" class="repair-list">
            <strong>do_not_do</strong>
            <span v-for="item in repairPacketResult.do_not_do" :key="item">{{ item }}</span>
          </div>
          <div class="safety-notes">
            <span v-for="note in repairPacketResult.safety_notes" :key="note" class="label-badge label-ai">{{ note }}</span>
          </div>
          <strong>codex_handoff_prompt preview</strong>
          <pre>{{ repairPacketResult.codex_handoff_prompt }}</pre>
        </div>
      </section>

      <section class="card repair-handoff-preview">
        <div class="section-header">
          <h2>Codex / OMX Repair Handoff</h2>
          <span class="muted">S20.3 handoff preview only</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Handoff only</span>
          <span class="label-badge label-provider">No repair execution</span>
          <span class="label-badge label-applied">No repository writes by platform</span>
          <span class="label-badge label-exec">No auto merge / deploy</span>
          <span class="label-badge label-redacted">Requires current master verification</span>
        </div>
        <p class="section-note">Reads an existing repair_packet artifact and formats a safe prompt for Codex, OMX, or a generic AI.</p>
        <div class="repair-handoff-form">
          <label>
            repair_packet_artifact_id
            <input v-model.number="repairHandoffForm.repair_packet_artifact_id" type="number" min="1" placeholder="latest generated repair packet id" />
          </label>
          <label>
            target
            <select v-model="repairHandoffForm.target">
              <option value="codex">Codex</option>
              <option value="omx">OMX</option>
              <option value="generic_ai">Generic AI</option>
            </select>
          </label>
          <div class="form-actions">
            <button class="btn btn-primary btn-sm" @click="previewCodexRepairHandoff" :disabled="repairHandoffLoading || !repairHandoffForm.repair_packet_artifact_id">
              Preview Handoff
            </button>
            <button class="btn btn-sm" @click="copyRepairHandoffPrompt" :disabled="!repairHandoffResult?.handoff_prompt">
              Copy Handoff
            </button>
          </div>
        </div>
        <p v-if="repairHandoffCopyMessage" class="copy-message">{{ repairHandoffCopyMessage }}</p>
        <p v-if="repairHandoffError" class="run-error">{{ repairHandoffError }}</p>
        <div v-if="repairHandoffResult" class="real-ai-result repair-handoff-result">
          <strong>repair handoff prompt</strong>
          <div class="dispatch-job-meta">
            <span>target: {{ repairHandoffResult.target }}</span>
            <span>source_repair_packet_artifact_id: {{ repairHandoffResult.source_repair_packet_artifact_id }}</span>
            <span>requires_master_verification={{ repairHandoffResult.requires_master_verification }}</span>
            <span>read_only={{ repairHandoffResult.read_only }}</span>
            <span>persisted={{ repairHandoffResult.persisted }}</span>
          </div>
          <div class="safety-notes">
            <span v-for="note in repairHandoffResult.safety_notes" :key="note" class="label-badge label-ai">{{ note }}</span>
          </div>
          <pre>{{ repairHandoffResult.handoff_prompt }}</pre>
        </div>
      </section>

      <section class="card repair-attempt-timeline">
        <div class="section-header">
          <h2>Repair Attempt Timeline</h2>
          <span class="muted">S20.4 timeline only</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Timeline only</span>
          <span class="label-badge label-provider">Platform does not execute repair</span>
          <span class="label-badge label-redacted">Verification result is imported, not run by platform</span>
          <span class="label-badge label-provider">No auto next attempt</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-exec">No auto PR / merge / deploy</span>
        </div>
        <p class="section-note">Tracks repair attempts that are executed outside the platform by Codex, OMX, a user, or a generic AI.</p>
        <div class="repair-attempt-form">
          <label>
            executor
            <select v-model="repairAttemptForm.executor">
              <option value="codex">codex</option>
              <option value="omx">omx</option>
              <option value="user">user</option>
              <option value="generic_ai">generic_ai</option>
            </select>
          </label>
          <label>
            handoff_target
            <select v-model="repairAttemptForm.handoff_target">
              <option value="codex">codex</option>
              <option value="omx">omx</option>
              <option value="user">user</option>
              <option value="generic_ai">generic_ai</option>
            </select>
          </label>
          <label>
            repair_packet_artifact_id
            <input v-model.number="repairAttemptForm.repair_packet_artifact_id" type="number" min="1" placeholder="latest repair packet id" />
          </label>
          <label>
            failure_evidence_artifact_id
            <input v-model.number="repairAttemptForm.failure_evidence_artifact_id" type="number" min="1" placeholder="optional" />
          </label>
          <label class="wide">
            summary
            <textarea v-model="repairAttemptForm.summary" rows="2"></textarea>
          </label>
          <div class="form-actions wide">
            <button class="btn btn-primary btn-sm" @click="createRepairAttemptFromTimeline" :disabled="repairAttemptLoading || !repairAttemptForm.repair_packet_artifact_id">
              Create Attempt
            </button>
            <button class="btn btn-sm" @click="loadRepairAttemptsForTask" :disabled="repairAttemptLoading">Refresh Attempts</button>
          </div>
        </div>
        <p v-if="repairAttemptError" class="run-error">{{ repairAttemptError }}</p>
        <div class="repair-verification-form">
          <label>
            attempt_id
            <input v-model.number="repairVerificationForm.attempt_id" type="number" min="1" placeholder="attempt id" />
          </label>
          <label>
            status
            <select v-model="repairVerificationForm.status">
              <option value="verification_passed">verification_passed</option>
              <option value="verification_failed">verification_failed</option>
            </select>
          </label>
          <label class="wide">
            summary
            <input v-model="repairVerificationForm.summary" placeholder="verification result summary" />
          </label>
          <label class="wide">
            commands
            <textarea v-model="repairVerificationForm.commands_text" rows="2" placeholder="One imported command per line"></textarea>
          </label>
          <label class="wide">
            artifact_content
            <textarea v-model="repairVerificationForm.artifact_content" rows="3" placeholder="Imported verification log excerpt"></textarea>
          </label>
          <div class="form-actions wide">
            <button class="btn btn-sm" @click="markSelectedAttemptHandoffCreated" :disabled="repairAttemptLoading || !repairVerificationForm.attempt_id">
              Mark Handoff Created
            </button>
            <button class="btn btn-primary btn-sm" @click="importSelectedVerificationResult" :disabled="repairAttemptLoading || !repairVerificationForm.attempt_id">
              Import Verification Result
            </button>
            <button class="btn btn-warn btn-sm" @click="stopSelectedRepairAttempt" :disabled="repairAttemptLoading || !repairVerificationForm.attempt_id">
              Stop Attempt
            </button>
          </div>
        </div>
        <div v-if="repairAttempts.length" class="repair-attempt-list">
          <div v-for="attempt in repairAttempts" :key="attempt.repair_attempt_id" class="repair-attempt-item">
            <div class="dispatch-batch-header">
              <strong>attempt #{{ attempt.attempt_no }}</strong>
              <span class="run-status-badge" :class="attempt.status">{{ attempt.status }}</span>
              <span>repair_attempt_id: {{ attempt.repair_attempt_id }}</span>
            </div>
            <div class="dispatch-job-meta">
              <span>executor: {{ attempt.executor }}</span>
              <span>handoff_target: {{ attempt.handoff_target }}</span>
              <span>failure_evidence_artifact_id: {{ attempt.failure_evidence_artifact_id || '-' }}</span>
              <span>repair_packet_artifact_id: {{ attempt.repair_packet_artifact_id }}</span>
              <span>verification_result_artifact_ids: {{ formatArtifactIds(attempt.verification_result_artifact_ids) }}</span>
              <span>summary: {{ attempt.summary || '-' }}</span>
              <span>created_at: {{ formatTime(attempt.created_at) }}</span>
              <span>updated_at: {{ formatTime(attempt.updated_at) }}</span>
              <span>read_only={{ attempt.read_only }}</span>
              <span>persisted={{ attempt.persisted }}</span>
            </div>
            <div class="safety-notes">
              <span v-for="note in attempt.safety_notes" :key="`${attempt.repair_attempt_id}-${note}`" class="label-badge label-ai">{{ note }}</span>
            </div>
            <div class="form-actions">
              <button class="btn btn-sm" @click="selectRepairAttempt(attempt)">Select Attempt</button>
            </div>
          </div>
        </div>
        <p v-else class="section-note">No repair attempts recorded for this task.</p>
      </section>

      <section class="card evidence-summary-panel">
        <div class="section-header">
          <h2>Run Timeline / Evidence Board</h2>
          <div class="section-actions">
            <button class="btn btn-sm" @click="refreshEvidenceSummary" :disabled="evidenceSummaryLoading">Refresh Timeline / Evidence Board</button>
          </div>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Timeline is read-only</span>
          <span class="label-badge label-ai">Evidence Board is read-only</span>
          <span class="label-badge label-provider">No provider call</span>
          <span class="label-badge label-provider">No Browser AI execution</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-redacted">No GitHub / Sonar query</span>
          <span class="label-badge label-exec">No PR / CI / Sonar / Deploy</span>
          <span class="label-badge label-merged">No auto approve / merge</span>
        </div>
        <p class="section-note">
          S22.2 displays read-only summaries returned by the S22.1 APIs. It does not execute repair, call providers, query GitHub/Sonar, or write business records.
        </p>
        <p v-if="evidenceSummaryError" class="run-error">{{ evidenceSummaryError }}</p>
        <div class="evidence-summary-flags">
          <span>timeline read_only={{ timeline?.read_only ?? '-' }}</span>
          <span>timeline persisted={{ timeline?.persisted ?? '-' }}</span>
          <span>evidence_board read_only={{ evidenceBoard?.read_only ?? '-' }}</span>
          <span>evidence_board persisted={{ evidenceBoard?.persisted ?? '-' }}</span>
        </div>

        <div class="evidence-summary-grid">
          <div class="timeline-panel">
            <div class="section-header compact">
              <strong>Run Timeline</strong>
              <span class="workspace-readonly">latest {{ timelineItems.length }} items</span>
            </div>
            <div v-if="timelineItems.length" class="timeline-list">
              <div v-for="item in timelineItems" :key="`${item.time}-${item.type}-${item.summary}`" class="timeline-item">
                <div class="timeline-item-header">
                  <strong>{{ item.title }}</strong>
                  <span class="run-status-badge" :class="item.status">{{ item.status }}</span>
                </div>
                <div class="dispatch-job-meta">
                  <span>time: {{ formatTime(item.time) }}</span>
                  <span>type: {{ item.type }}</span>
                  <span>source: {{ item.source }}</span>
                  <span>linked ids: {{ formatLinkedIds(item.linked_ids) }}</span>
                  <span>summary: {{ item.summary || '-' }}</span>
                </div>
                <div class="safety-notes">
                  <span v-for="flag in item.safety_flags" :key="`${item.type}-${flag}`" class="label-badge label-ai">{{ flag }}</span>
                </div>
              </div>
            </div>
            <p v-else class="section-note">No timeline items returned.</p>
          </div>

          <div class="evidence-board-panel">
            <div class="section-header compact">
              <strong>Evidence Board</strong>
              <span class="workspace-readonly">filtered {{ filteredEvidenceBoardItems.length }} / {{ evidenceBoardTotalCount }} summaries</span>
            </div>
            <div class="evidence-board-controls">
              <label v-for="field in evidenceBoardFilterFields" :key="field">
                {{ field }}
                <select v-model="evidenceBoardFilter[field]">
                  <option value="">All</option>
                  <option v-for="value in evidenceFilterOptions[field]" :key="`${field}-${value}`" :value="value">{{ value || '-' }}</option>
                </select>
              </label>
              <button class="btn btn-sm" @click="clearEvidenceBoardFilters">Clear filters</button>
              <span class="workspace-readonly">filtered count: {{ filteredEvidenceBoardItems.length }} / total count: {{ evidenceBoardTotalCount }}</span>
            </div>
            <p v-if="evidenceBoardCopyMessage" class="copy-message">{{ evidenceBoardCopyMessage }}</p>
            <div v-if="evidenceBoard" class="evidence-filters">
              <span>filters evidence_type: {{ evidenceBoard.filters.evidence_type.join(', ') || '-' }}</span>
              <span>source: {{ evidenceBoard.filters.source.join(', ') || '-' }}</span>
              <span>status: {{ evidenceBoard.filters.status.join(', ') || '-' }}</span>
              <span>provider: {{ evidenceBoard.filters.provider.join(', ') || '-' }}</span>
              <span>role: {{ evidenceBoard.filters.role.join(', ') || '-' }}</span>
            </div>
            <div v-if="filteredEvidenceBoardItems.length" class="evidence-board-list">
              <div v-for="item in filteredEvidenceBoardItems" :key="`${item.evidence_type}-${item.artifact_id}-${item.summary}`" class="evidence-board-item">
                <div class="timeline-item-header">
                  <strong>{{ item.evidence_type }}</strong>
                  <span class="run-status-badge" :class="item.status">{{ item.status }}</span>
                </div>
                <div class="evidence-item-badges">
                  <span class="label-badge label-applied">has_artifact={{ evidenceItemHasArtifact(item) }}</span>
                  <span class="label-badge label-warn">has_risk={{ evidenceItemHasRisk(item) }}</span>
                  <span class="label-badge label-ai">safety boundary: {{ evidenceSafetyBoundary(item) }}</span>
                </div>
                <div class="dispatch-job-meta">
                  <span>source: {{ item.source }}</span>
                  <span>provider: {{ item.provider || '-' }}</span>
                  <span>role: {{ item.role || '-' }}</span>
                  <span>linked ids: {{ formatEvidenceItemLinkedIds(item) }}</span>
                  <span>summary: {{ item.summary || '-' }}</span>
                  <span>redaction_status: redaction_applied={{ item.redaction_status.redaction_applied }}, truncated={{ item.redaction_status.truncated }}, max_chars={{ item.redaction_status.max_chars }}</span>
                </div>
                <div class="form-actions">
                  <button class="btn btn-sm" @click="copyEvidenceSummary(item)">Copy evidence summary</button>
                  <button class="btn btn-sm" @click="copyEvidenceLinkedIds(item)">Copy linked ids</button>
                </div>
                <details class="evidence-excerpt">
                  <summary>Evidence detail</summary>
                  <div class="dispatch-job-meta">
                    <span v-for="row in evidenceDetailRows(item)" :key="`${item.evidence_type}-${row}`">{{ row }}</span>
                  </div>
                  <p class="section-note">safety_notes: {{ item.safety_notes.join('; ') || '-' }}</p>
                  <p class="section-note">raw_excerpt</p>
                  <pre>{{ item.raw_excerpt || '-' }}</pre>
                </details>
                <div class="safety-notes">
                  <span v-for="note in item.safety_notes" :key="`${item.evidence_type}-${note}`" class="label-badge label-provider">{{ note }}</span>
                </div>
              </div>
            </div>
            <p v-else class="section-note">No evidence board summaries match the current filters.</p>
          </div>
        </div>
      </section>

      <section class="card project-memory-panel">
        <div class="section-header">
          <h2>Project Memory</h2>
          <div class="section-actions">
            <button class="btn btn-sm" @click="refreshProjectMemory" :disabled="projectMemoryLoading">Refresh Project Memory</button>
          </div>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Project Memory is read-only</span>
          <span class="label-badge label-ai">No memory writes</span>
          <span class="label-badge label-provider">No provider call</span>
          <span class="label-badge label-provider">No Browser AI execution</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-redacted">No GitHub / Sonar query</span>
          <span class="label-badge label-exec">No PR / CI / Sonar / Deploy</span>
          <span class="label-badge label-merged">No auto approve / merge</span>
          <span class="label-badge label-warn">Memory may be stale; verify before acting</span>
        </div>
        <p class="section-note">
          S23.2 displays read-only Project Memory from S23.1. It does not create candidates, confirm memory, mark stale records, call providers, or write business records.
        </p>
        <p v-if="projectMemoryError" class="run-error">{{ projectMemoryError }}</p>
        <p v-if="projectMemoryCopyMessage" class="copy-message">{{ projectMemoryCopyMessage }}</p>

        <div class="project-memory-flags">
          <span>memory read_only={{ projectMemory?.read_only ?? '-' }}</span>
          <span>memory persisted={{ projectMemory?.persisted ?? '-' }}</span>
          <span>summary read_only={{ projectMemorySummary?.read_only ?? '-' }}</span>
          <span>summary persisted={{ projectMemorySummary?.persisted ?? '-' }}</span>
        </div>

        <div v-if="projectMemorySummary" class="project-memory-summary">
          <div class="section-header compact">
            <strong>Project Memory Summary</strong>
            <span class="workspace-readonly">memory_count={{ projectMemorySummary.memory_count }}</span>
          </div>
          <div class="dispatch-job-meta">
            <span>memory_count: {{ projectMemorySummary.memory_count }}</span>
            <span>memory_types: {{ projectMemorySummary.memory_types.join(', ') || '-' }}</span>
            <span>stale_count: {{ projectMemorySummary.stale_count }}</span>
            <span>high_confidence_count: {{ projectMemorySummary.high_confidence_count }}</span>
            <span>summary: {{ projectMemorySummary.summary || '-' }}</span>
          </div>
          <div class="safety-notes">
            <span v-for="note in projectMemorySummary.safety_notes" :key="`summary-${note}`" class="label-badge label-provider">{{ note }}</span>
          </div>
        </div>

        <div class="project-memory-controls">
          <label v-for="field in projectMemoryFilterFields" :key="field">
            {{ field }}
            <select v-model="projectMemoryFilter[field]">
              <option value="">All</option>
              <option v-for="value in projectMemoryFilterOptions[field]" :key="`${field}-${value}`" :value="String(value)">{{ String(value) }}</option>
            </select>
          </label>
          <button class="btn btn-sm" @click="clearProjectMemoryFilters">Clear filters</button>
          <span class="workspace-readonly">filtered count: {{ filteredProjectMemoryItems.length }} / total count: {{ projectMemoryTotalCount }}</span>
        </div>

        <div v-if="projectMemory" class="project-memory-filters">
          <span>filters memory_type: {{ projectMemory.filters.memory_type.join(', ') || '-' }}</span>
          <span>confidence: {{ projectMemory.filters.confidence.join(', ') || '-' }}</span>
          <span>stale: {{ projectMemory.filters.stale.map(String).join(', ') || '-' }}</span>
        </div>

        <div v-if="filteredProjectMemoryItems.length" class="project-memory-list">
          <div v-for="item in filteredProjectMemoryItems" :key="item.memory_id" class="project-memory-item">
            <div class="timeline-item-header">
              <strong>{{ item.title }}</strong>
              <span class="run-status-badge ready">{{ item.memory_type }}</span>
            </div>
            <div class="dispatch-job-meta">
              <span>memory_type: {{ item.memory_type }}</span>
              <span>summary: {{ item.summary || '-' }}</span>
              <span>confidence: {{ item.confidence }}</span>
              <span>stale: {{ item.stale }}</span>
              <span>updated_at: {{ formatTime(item.updated_at) }}</span>
              <span>source_refs: {{ formatProjectMemorySourceRefs(item.source_refs) }}</span>
              <span>redaction_status: redaction_applied={{ item.redaction_status.redaction_applied }}, truncated={{ item.redaction_status.truncated }}, max_chars={{ item.redaction_status.max_chars }}</span>
            </div>
            <div class="form-actions">
              <button class="btn btn-sm" @click="copyProjectMemorySummary(item)">Copy memory summary</button>
              <button class="btn btn-sm" @click="copyProjectMemorySourceRefs(item)">Copy source refs</button>
            </div>
            <details class="project-memory-content">
              <summary>Memory content detail</summary>
              <pre>{{ formatProjectMemoryContent(item.content) }}</pre>
            </details>
          </div>
        </div>
        <p v-else class="section-note">No Project Memory records match the current filters.</p>

        <div v-if="projectMemory?.safety_notes.length" class="safety-notes">
          <span v-for="note in projectMemory.safety_notes" :key="`memory-${note}`" class="label-badge label-ai">{{ note }}</span>
        </div>
      </section>

      <section class="card mastermind-review-panel">
        <div class="section-header">
          <h2>Mastermind Review</h2>
          <span class="workspace-readonly">Browser AI advisory review trial</span>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-ai">Mastermind review is advisory only</span>
          <span class="label-badge label-ai">Human confirmation required</span>
          <span class="label-badge label-merged">No auto approve</span>
          <span class="label-badge label-merged">No auto merge</span>
          <span class="label-badge label-exec">No auto deploy</span>
          <span class="label-badge label-exec">No auto rework</span>
          <span class="label-badge label-provider">Browser AI uses visible user-authorized UI only</span>
          <span class="label-badge label-redacted">No account/password/cookie/session storage</span>
          <span class="label-badge label-redacted">No captcha/login bypass</span>
          <span class="label-badge label-applied">No repository writes</span>
          <span class="label-badge label-redacted">No GitHub / Sonar platform query</span>
        </div>
        <p class="section-note">
          S24.1.3 previews the review packet and calls the existing Browser AI review API. PR metadata, verification, and Sonar values are pasted by the user or an external flow.
        </p>

        <div class="mastermind-review-grid">
          <div class="mastermind-review-form">
            <div class="section-header compact">
              <strong>Packet metadata</strong>
              <span class="workspace-readonly">manual input only</span>
            </div>
            <label class="wide">
              PR URL
              <input v-model="mastermindPacketForm.pr_url" placeholder="https://github.com/org/repo/pull/64" />
            </label>
            <label>
              PR number
              <input v-model.number="mastermindPacketForm.pr_number" type="number" min="1" placeholder="64" />
            </label>
            <label>
              packet_budget
              <input v-model.number="mastermindPacketForm.packet_budget" type="number" min="1000" max="30000" />
            </label>
            <label>
              head commit
              <input v-model="mastermindPacketForm.head_commit" placeholder="full head sha" />
            </label>
            <label>
              base commit
              <input v-model="mastermindPacketForm.base_commit" placeholder="full base sha" />
            </label>
            <label class="wide">
              changed files
              <textarea v-model="mastermindChangedFilesText" rows="3" placeholder="one file per line, or comma separated"></textarea>
            </label>
            <label class="wide">
              PR body
              <textarea v-model="mastermindPacketForm.pr_body" rows="4" placeholder="PR body text or excerpt"></textarea>
            </label>

            <div class="mastermind-review-subgrid wide">
              <label>
                targeted_backend_pytest
                <input v-model="mastermindPacketForm.verification_results.targeted_backend_pytest" />
              </label>
              <label>
                full_backend_pytest
                <input v-model="mastermindPacketForm.verification_results.full_backend_pytest" />
              </label>
              <label>
                compileall
                <input v-model="mastermindPacketForm.verification_results.compileall" />
              </label>
              <label>
                npm_build
                <input v-model="mastermindPacketForm.verification_results.npm_build" />
              </label>
              <label>
                frontend_smoke
                <input v-model="mastermindPacketForm.verification_results.frontend_smoke" />
              </label>
              <label>
                git_diff_check
                <input v-model="mastermindPacketForm.verification_results.git_diff_check" />
              </label>
            </div>

            <div class="mastermind-review-subgrid wide">
              <label>
                quality_gate
                <input v-model="mastermindPacketForm.sonarcloud.quality_gate" />
              </label>
              <label>
                security_hotspots
                <input v-model.number="mastermindPacketForm.sonarcloud.security_hotspots" type="number" min="0" />
              </label>
              <label>
                duplication_on_new_code
                <input v-model="mastermindPacketForm.sonarcloud.duplication_on_new_code" />
              </label>
              <label>
                new_issues
                <input v-model.number="mastermindPacketForm.sonarcloud.new_issues" type="number" min="0" />
              </label>
            </div>

            <div class="mastermind-checkboxes wide">
              <label class="checkbox-row"><input v-model="mastermindPacketForm.include_evidence_board" type="checkbox" /> include_evidence_board</label>
              <label class="checkbox-row"><input v-model="mastermindPacketForm.include_timeline" type="checkbox" /> include_timeline</label>
              <label class="checkbox-row"><input v-model="mastermindPacketForm.include_project_memory" type="checkbox" /> include_project_memory</label>
              <label class="checkbox-row"><input v-model="mastermindPacketForm.include_handoff_context" type="checkbox" /> include_handoff_context</label>
            </div>

            <div class="section-header compact wide">
              <strong>Browser AI options</strong>
              <span class="workspace-readonly">visible UI only</span>
            </div>
            <label>
              provider_profile
              <select v-model="mastermindBrowserAiForm.provider_profile" @change="applyMastermindBrowserProfile">
                <option v-for="profile in browserAiProfiles" :key="`mastermind-${profile.provider}`" :value="profile.provider">
                  {{ profile.display_name }}
                </option>
              </select>
            </label>
            <label class="wide">
              target_url
              <input v-model="mastermindBrowserAiForm.target_url" placeholder="https://chatgpt.com/" />
            </label>
            <label>
              prompt_selector
              <input v-model="mastermindBrowserAiForm.prompt_selector" placeholder="textarea[name='prompt']" />
            </label>
            <label>
              submit_selector
              <input v-model="mastermindBrowserAiForm.submit_selector" placeholder="button[data-send]" />
            </label>
            <label>
              response_selector
              <input v-model="mastermindBrowserAiForm.response_selector" placeholder="[data-answer]" />
            </label>
            <label>
              stable_response_timeout_seconds
              <input v-model.number="mastermindBrowserAiForm.stable_response_timeout_seconds" type="number" min="1" max="600" />
            </label>
            <label>
              stable_polls
              <input v-model.number="mastermindBrowserAiForm.stable_polls" type="number" min="1" max="50" />
            </label>
            <label>
              stable_interval_ms
              <input v-model.number="mastermindBrowserAiForm.stable_interval_ms" type="number" min="100" max="10000" />
            </label>
            <label class="checkbox-row wide"><input v-model="mastermindSaveArtifact" type="checkbox" /> save_artifact</label>

            <div class="form-actions wide">
              <button class="btn btn-sm" @click="previewMastermindReview" :disabled="mastermindLoading">
                Preview Mastermind Review Packet
              </button>
              <button class="btn btn-primary btn-sm" @click="runMastermindReview" :disabled="mastermindExecuting">
                Run Browser AI Mastermind Review
              </button>
            </div>
          </div>

          <div class="mastermind-review-results">
            <p v-if="mastermindError" class="run-error">{{ mastermindError }}</p>
            <p v-if="mastermindManualLoginRequired()" class="run-error">manual login required: complete login in the visible browser, then retry.</p>
            <p v-if="mastermindRefreshMessage" class="copy-message">{{ mastermindRefreshMessage }}</p>
            <p v-if="mastermindGateHint" class="section-note">{{ mastermindGateHint }}</p>

            <div v-if="mastermindPreview" class="mastermind-result-card">
              <div class="section-header compact">
                <strong>Packet Preview</strong>
                <span class="workspace-readonly">{{ mastermindPreview.packet_type }}</span>
              </div>
              <div class="dispatch-job-meta">
                <span>packet_type: {{ mastermindPreview.packet_type }}</span>
                <span>PR URL: {{ mastermindPreview.packet.pr?.url || '-' }}</span>
                <span>PR number: {{ mastermindPreview.packet.pr?.number ?? '-' }}</span>
                <span>head commit: {{ mastermindPreview.packet.pr?.head_commit || '-' }}</span>
                <span>base commit: {{ mastermindPreview.packet.pr?.base_commit || '-' }}</span>
                <span>changed files: {{ formatMastermindList(mastermindPreview.packet.pr?.changed_files || []) }}</span>
                <span>targeted_backend_pytest: {{ mastermindPreview.packet.verification?.targeted_backend_pytest || '-' }}</span>
                <span>quality_gate: {{ mastermindPreview.packet.sonarcloud?.quality_gate || '-' }}</span>
                <span>verification summary: {{ formatMastermindJson(mastermindPreview.packet.verification) }}</span>
                <span>SonarCloud summary: {{ formatMastermindJson(mastermindPreview.packet.sonarcloud) }}</span>
                <span>read_only={{ mastermindPreview.read_only }}</span>
                <span>persisted={{ mastermindPreview.persisted }}</span>
                <span>redaction_status: redaction_applied={{ mastermindPreview.redaction_status.redaction_applied }}, truncated={{ mastermindPreview.redaction_status.truncated }}, max_chars={{ mastermindPreview.redaction_status.max_chars }}</span>
              </div>
              <details open class="mastermind-detail">
                <summary>PR / verification / Sonar</summary>
                <pre>{{ formatMastermindJson({ pr: mastermindPreview.packet.pr, verification: mastermindPreview.packet.verification, sonarcloud: mastermindPreview.packet.sonarcloud, safety_boundary_checklist: mastermindPreview.packet.safety_boundary_checklist }) }}</pre>
              </details>
              <details open class="mastermind-detail">
                <summary>Task / Evidence / Timeline / Project Memory / handoff context</summary>
                <div class="dispatch-job-meta">
                  <span>task_summary: {{ formatMastermindPacketField('task_summary') }}</span>
                  <span>evidence_board_summary: {{ formatMastermindPacketField('evidence_board_summary') }}</span>
                  <span>run_timeline_summary: {{ formatMastermindPacketField('run_timeline_summary') }}</span>
                  <span>project_memory_summary: {{ formatMastermindPacketField('project_memory_summary') }}</span>
                  <span>handoff_context: {{ formatMastermindPacketField('handoff_context') }}</span>
                </div>
              </details>
              <details class="mastermind-detail">
                <summary>review_instruction</summary>
                <pre>{{ formatMastermindPacketField('review_instruction') }}</pre>
              </details>
              <details class="mastermind-detail">
                <summary>required_output_contract</summary>
                <pre>{{ formatMastermindPacketField('required_output_contract') }}</pre>
              </details>
              <div class="safety-notes">
                <span v-for="note in mastermindPreview.safety_notes" :key="`preview-${note}`" class="label-badge label-provider">{{ note }}</span>
              </div>
            </div>

            <div v-if="mastermindResult" class="mastermind-result-card">
              <div class="section-header compact">
                <strong>Review Result</strong>
                <span class="run-status-badge" :class="mastermindResult.status">{{ mastermindResult.status }}</span>
              </div>
              <div class="dispatch-job-meta">
                <span>status: {{ mastermindResult.status }}</span>
                <span>verdict: {{ mastermindResult.verdict }}</span>
                <span>summary: {{ mastermindResult.summary || '-' }}</span>
                <span>agent_run_id: {{ mastermindResult.agent_run_id ?? '-' }}</span>
                <span>artifact_id: {{ mastermindResult.artifact_id ?? '-' }}</span>
                <span>read_only={{ mastermindResult.read_only }}</span>
                <span>persisted={{ mastermindResult.persisted }}</span>
                <span>advisory_only={{ mastermindResult.advisory_only }}</span>
                <span>human_confirmation_required={{ mastermindResult.human_confirmation_required }}</span>
                <span>no_auto_merge={{ mastermindResult.no_auto_merge }}</span>
                <span v-if="mastermindResult.failure_reason">failure_reason: {{ mastermindResult.failure_reason }}</span>
                <span>blocking_items: {{ formatMastermindList(mastermindResult.blocking_items) }}</span>
                <span>recommended_actions: {{ formatMastermindList(mastermindResult.recommended_actions) }}</span>
                <span>safety_notes: {{ formatMastermindList(mastermindResult.safety_notes) }}</span>
                <span>parse_errors: {{ formatMastermindList(mastermindResult.parse_errors) }}</span>
              </div>
              <details class="mastermind-detail">
                <summary>raw_excerpt</summary>
                <pre>{{ mastermindResult.raw_excerpt || '-' }}</pre>
              </details>
            </div>

            <div class="controlled-gate-panel">
              <div class="section-header compact">
                <strong>Controlled Mastermind Gate</strong>
                <span class="workspace-readonly">read-only gate preview</span>
              </div>
              <div class="workspace-safety">
                <span class="label-badge label-ai">Controlled Gate is read-only</span>
                <span class="label-badge label-ai">Human confirmation required</span>
                <span class="label-badge label-ai">Advisory only</span>
                <span class="label-badge label-merged">No auto approve</span>
                <span class="label-badge label-merged">No auto merge</span>
                <span class="label-badge label-exec">No auto deploy</span>
                <span class="label-badge label-exec">No auto rework</span>
                <span class="label-badge label-redacted">No GitHub / Sonar platform query</span>
                <span class="label-badge label-provider">No Browser AI execution</span>
                <span class="label-badge label-provider">No provider call</span>
                <span class="label-badge label-applied">No repository writes</span>
              </div>
              <p class="section-note">
                gate_advisory_approved means ready for human confirmation only. It is not auto approve, not auto merge, not deploy permission, and not rework permission.
              </p>
              <div class="mastermind-review-subgrid">
                <label>
                  source_artifact_id
                  <input v-model.number="mastermindGateForm.source_artifact_id" type="number" min="1" placeholder="optional" />
                </label>
                <label>
                  current_head_commit
                  <input v-model="mastermindGateForm.current_head_commit" placeholder="current PR head sha" />
                </label>
              </div>
              <p class="section-note">
                Reuses the PR URL, PR number, verification results, and SonarCloud values from the Mastermind Review packet form. The UI does not query GitHub or Sonar.
              </p>
              <div class="form-actions">
                <button class="btn btn-sm" @click="previewControlledGate" :disabled="mastermindGateLoading">
                  Preview Controlled Gate
                </button>
              </div>
              <p v-if="mastermindGateError" class="run-error">{{ mastermindGateError }}</p>
              <div v-if="mastermindGateResult" class="mastermind-result-card">
                <div class="section-header compact">
                  <strong>Gate Preview</strong>
                  <span class="gate-status-badge" :class="mastermindGateResult.gate_status">{{ mastermindGateResult.gate_status }}</span>
                </div>
                <div v-if="mastermindGateResult.gate_status === 'gate_advisory_approved'" class="gate-advisory-message">
                  <p class="copy-message">gate_advisory_approved = ready for human confirmation</p>
                  <p class="section-note">No automatic approve, merge, deploy, or rework is authorized.</p>
                </div>
                <p v-if="mastermindGateResult.gate_status === 'gate_request_changes'" class="run-error">
                  gate_request_changes: request changes before continuing.
                </p>
                <p v-if="mastermindGateResult.gate_status === 'gate_blocked_by_safety'" class="run-error">
                  gate_blocked_by_safety: safety boundary blocked.
                </p>
                <p v-if="mastermindGateResult.gate_status === 'gate_stale_review'" class="run-error">
                  gate_stale_review: reviewed head commit does not match current head commit.
                </p>
                <div class="dispatch-job-meta">
                  <span>gate_status: {{ mastermindGateResult.gate_status }}</span>
                  <span>summary: {{ mastermindGateResult.summary || '-' }}</span>
                  <span>source_artifact_id: {{ mastermindGateResult.source_artifact_id ?? '-' }}</span>
                  <span>source_agent_run_id: {{ mastermindGateResult.source_agent_run_id ?? '-' }}</span>
                  <span>PR URL: {{ mastermindGateResult.pr_url || '-' }}</span>
                  <span>PR number: {{ mastermindGateResult.pr_number ?? '-' }}</span>
                  <span>head_commit: {{ mastermindGateResult.head_commit || '-' }}</span>
                  <span>reviewed_head_commit: {{ mastermindGateResult.reviewed_head_commit || '-' }}</span>
                  <span>human_confirmation_required={{ mastermindGateResult.human_confirmation_required }}</span>
                  <span>advisory_only={{ mastermindGateResult.advisory_only }}</span>
                  <span>no_auto_merge={{ mastermindGateResult.no_auto_merge }}</span>
                  <span>read_only={{ mastermindGateResult.read_only }}</span>
                  <span>persisted={{ mastermindGateResult.persisted }}</span>
                  <span>blocking_reasons: {{ formatMastermindList(mastermindGateResult.blocking_reasons) }}</span>
                  <span>recommended_actions: {{ formatMastermindList(mastermindGateResult.recommended_actions) }}</span>
                  <span>safety_notes: {{ formatMastermindList(mastermindGateResult.safety_notes) }}</span>
                </div>
              </div>
              <div class="gate-status-taxonomy">
                <span class="gate-status-badge gate_not_ready">gate_not_ready</span>
                <span class="gate-status-badge gate_needs_human">gate_needs_human</span>
                <span class="gate-status-badge gate_request_changes">gate_request_changes</span>
                <span class="gate-status-badge gate_advisory_approved">gate_advisory_approved</span>
                <span class="gate-status-badge gate_invalid_review">gate_invalid_review</span>
                <span class="gate-status-badge gate_blocked_by_safety">gate_blocked_by_safety</span>
                <span class="gate-status-badge gate_stale_review">gate_stale_review</span>
                <span>gate_request_changes: request changes before continuing.</span>
                <span>gate_blocked_by_safety: safety boundary blocked.</span>
                <span>gate_stale_review: reviewed head commit does not match current head commit.</span>
              </div>
            </div>
          </div>
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
          <button class="btn btn-sm" @click="refreshAnswerSynthesis" :disabled="answerSynthesisLoading || !task">
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
        <div v-else class="empty-state"><p>暂无可综合的多 AI 结果</p></div>
      </section>

      <!-- MCP Bridge -->
      <section class="card mcp-bridge-panel">
        <div class="section-header">
          <h2>MCP Bridge / 外部 AI 工具桥</h2>
          <button class="btn btn-sm" @click="previewMcpHandoff" :disabled="mcpLoading || !task">
            Preview MCP Handoff
          </button>
        </div>
        <div class="workspace-safety">
          <span class="label-badge label-provider">MCP Bridge S18 is read-only + dry-run only</span>
          <span class="label-badge label-applied">read-only</span>
          <span class="label-badge label-ai">dry-run</span>
          <span class="label-badge label-exec">No MCP execute</span>
          <span class="label-badge label-redacted">No secrets returned</span>
          <span class="label-badge label-merged">No auto merge</span>
        </div>
        <p class="section-note">External AI can preview task context and dry-run plans, but cannot execute providers, open browsers, write repository files, create PRs, deploy, or merge.</p>
        <p v-if="mcpError" class="run-error">{{ mcpError }}</p>
        <div class="mcp-tools-list">
          <strong>tools</strong>
          <span v-for="tool in mcpTools" :key="tool.name" class="label-badge" :class="tool.dry_run_only ? 'label-ai' : 'label-provider'">
            {{ tool.name }} · {{ tool.dry_run_only ? 'dry-run' : 'read-only' }}
          </span>
        </div>
        <div v-if="mcpResult" class="mcp-result">
          <div class="dispatch-job-meta">
            <span>tool: {{ mcpResult.tool }}</span>
            <span>status: {{ mcpResult.status }}</span>
            <span>read_only={{ mcpResult.read_only }}</span>
            <span>persisted={{ mcpResult.persisted }}</span>
          </div>
          <div class="synthesis-list">
            <strong>task brief / handoff summary</strong>
            <pre>{{ formatMcpPreview(mcpResult.data) }}</pre>
          </div>
          <div class="synthesis-list">
            <strong>safety notes</strong>
            <ul>
              <li v-for="note in mcpResult.safety_notes" :key="note">{{ note }}</li>
            </ul>
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
        <ArtifactTab :key="artifactRefreshKey" :task-id="task.id" :task-status="task.status" />
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
  dryRunBrowserAi, executeBrowserAi, fetchBrowserAiProviderProfiles,
  previewMultiAiEvidenceRun, executeMultiAiEvidenceRun, previewFailureEvidencePacket, generateRepairPacket, previewRepairHandoff,
  createRepairAttempt, fetchRepairAttempts, markRepairHandoffCreated, importRepairVerificationResult, stopRepairAttempt,
  fetchCodeContext,
  applyPatchInSandbox, fetchSandboxResults, fetchSandboxGate, evaluateSandboxGate,
  fetchMcpTools, callMcpTool,
  fetchTaskTimeline, fetchTaskEvidenceBoard,
  fetchProjectMemory, fetchProjectMemorySummary,
  previewMastermindReviewPacket, executeMastermindReview, previewMastermindReviewGate,
} from '../services/agentService'
import type { AgentProfile, AgentRun, AgentReview, AgentRunSubmitResult, ApprovalDecision, CodeContextResponse, PatchApplyResult, SandboxArtifactEntry, SandboxGateDecision, DispatchBatchResponse, AnswerSynthesisPreviewResponse, AiHandoffPreviewResponse, AiDispatchMode, AiDispatchRequest, AiDispatchDryRunResponse, AiDispatchExecuteResponse, AiDispatchSafetyGate, BrowserAiProviderProfile, BrowserAiRequest, BrowserAiResponse, BrowserAiSafetyGate, McpToolDescriptor, McpCallResponse, MultiAiEvidenceRunRequest, MultiAiEvidenceRunResponse, MultiAiEvidenceSafetyGate, FailureEvidencePreviewRequest, FailureEvidencePacketResponse, RepairPacketGenerateRequest, RepairHandoffPreviewRequest, RepairHandoffPreviewResponse, RepairPacketResponse, RepairAttemptCreateRequest, RepairAttemptResponse, RepairVerificationResultRequest, TimelineResponse, TimelineItem, EvidenceBoardResponse, EvidenceBoardItem, EvidenceLinkedIds, ProjectMemoryResponse, ProjectMemorySummaryResponse, ProjectMemoryItem, ProjectMemorySourceRef, MastermindReviewPacketPreviewRequest, MastermindReviewPacketPreviewResponse, MastermindReviewBrowserAiOptions, MastermindReviewExecuteRequest, MastermindReviewExecuteResponse, MastermindReviewGatePreviewRequest, MastermindReviewGatePreviewResponse } from '../types/agent'
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
const mcpTools = ref<McpToolDescriptor[]>([])
const mcpResult = ref<McpCallResponse | null>(null)
const mcpLoading = ref(false)
const mcpError = ref('')
const realAiMode = ref<AiDispatchMode>('review')
const realAiTaskGoal = ref('')
const realAiLoading = ref(false)
const realAiError = ref('')
const realAiDryRunResult = ref<AiDispatchDryRunResponse | null>(null)
const realAiExecuteResult = ref<AiDispatchExecuteResponse | null>(null)
const browserAiForm = ref<BrowserAiRequest>({
  project_id: 0,
  task_id: 0,
  provider: 'custom',
  target_url: 'http://127.0.0.1:9999/mock-browser-ai',
  prompt_source: 'task_goal',
  custom_prompt: '',
  input_selector: "textarea[name='prompt']",
  send_selector: 'button[data-send]',
  response_selector: '[data-answer]',
  scroll_container_selector: '',
  copy_button_selector: '',
  login_hint_selector: '',
  timeout_seconds: 180,
})
const browserAiLoading = ref(false)
const browserAiError = ref('')
const browserAiDryRunResult = ref<BrowserAiResponse | null>(null)
const browserAiExecuteResult = ref<BrowserAiResponse | null>(null)
const browserAiRefreshMessages = ref<string[]>([])
const browserAiFailedStep = computed(() => browserAiExecuteResult.value?.steps.find(step => step.status === 'failed') || null)
const artifactRefreshKey = ref(0)
const browserAiProfiles = ref<BrowserAiProviderProfile[]>([
  {
    provider: 'custom',
    display_name: 'Custom',
    target_url: '',
    target_url_hint: '',
    input_selector: '',
    send_selector: '',
    response_selector: '',
    scroll_container_selector: '',
    copy_button_selector: '',
    login_hint_selector: '',
    login_hint_text: '',
    selectors_configured: false,
    login_required_hint: false,
    editable: true,
    best_effort_note: '',
  },
])
const selectedBrowserAiProfile = computed(() => browserAiProfiles.value.find(profile => profile.provider === browserAiForm.value.provider) || null)
const browserAiLoginRequired = computed(() => {
  const result = browserAiExecuteResult.value
  if (!result) return false
  const text = `${result.status} ${result.error_message || ''} ${result.steps.map(step => `${step.name} ${step.status} ${step.message}`).join(' ')}`
  return /manual login may be required|detect_login|login_required/i.test(text)
})
const selectedBrowserAiProfileStatus = computed(() => {
  const profile = selectedBrowserAiProfile.value
  if (!profile) return 'unknown profile'
  const configured = profile.selectors_configured ? 'selectors configured' : 'custom selectors required'
  const login = profile.login_required_hint ? (profile.login_hint_text || 'login may be required') : 'login not required'
  return `${configured}; ${login}`
})
const multiAiForm = ref<MultiAiEvidenceRunRequest>({
  task_id: 0,
  mode: 'broadcast',
  providers: ['chatgpt_web', 'claude_web'],
  roles: [
    { role: 'backend', provider: 'chatgpt_web', prompt: 'Check backend risks.' },
    { role: 'frontend', provider: 'claude_web', prompt: 'Check frontend risks.' },
  ],
  prompt_source: 'task_goal',
  custom_prompt: '',
  concurrency_limit: 2,
  timeout_seconds: 180,
  target_url: '',
  input_selector: '',
  send_selector: '',
  response_selector: '',
  scroll_container_selector: '',
  copy_button_selector: '',
  login_hint_selector: '',
})
const multiAiLoading = ref(false)
const multiAiError = ref('')
const multiAiPreviewResult = ref<MultiAiEvidenceRunResponse | null>(null)
const multiAiExecuteResult = ref<MultiAiEvidenceRunResponse | null>(null)
const multiAiRefreshMessages = ref<string[]>([])
const multiAiConcurrencyNote = 'bounded concurrency is planned; current MVP executes jobs sequentially'
const evidenceProviderOptions = computed(() => browserAiProfiles.value.filter(profile => profile.provider !== 'custom' || profile.selectors_configured || profile.provider === 'custom'))
const failureEvidenceForm = ref<FailureEvidencePreviewRequest>({
  task_id: 0,
  failure_type: 'sandbox_gate_blocked',
  source: {
    agent_run_id: null,
    artifact_id: null,
    dispatch_batch_id: null,
    dispatch_job_id: null,
  },
  max_excerpt_chars: 4000,
})
const failureEvidencePacket = ref<FailureEvidencePacketResponse | null>(null)
const failureEvidenceLoading = ref(false)
const failureEvidenceError = ref('')
const repairPacketForm = ref<Omit<RepairPacketGenerateRequest, 'task_id' | 'failure_evidence'>>({
  analysis_mode: 'broadcast',
  providers: ['chatgpt_web', 'claude_web'],
  roles: [
    { role: 'logs', provider: 'chatgpt_web', prompt: 'Analyze failure logs and likely root cause.' },
    { role: 'risk', provider: 'claude_web', prompt: 'Analyze repair risks and verification commands.' },
  ],
  max_attempts: 1,
})
const repairPacketResult = ref<RepairPacketResponse | null>(null)
const repairPacketLoading = ref(false)
const repairPacketError = ref('')
const repairHandoffForm = ref<Omit<RepairHandoffPreviewRequest, 'task_id'>>({
  repair_packet_artifact_id: 0,
  target: 'codex',
})
const repairHandoffResult = ref<RepairHandoffPreviewResponse | null>(null)
const repairHandoffLoading = ref(false)
const repairHandoffError = ref('')
const repairHandoffCopyMessage = ref('')
const repairAttemptForm = ref<Omit<RepairAttemptCreateRequest, 'task_id'>>({
  executor: 'codex',
  failure_evidence_artifact_id: null,
  repair_packet_artifact_id: 0,
  handoff_target: 'codex',
  summary: 'Use the repair packet for one narrow external repair attempt.',
})
const repairVerificationForm = ref({
  attempt_id: 0,
  status: 'verification_passed' as RepairVerificationResultRequest['status'],
  summary: 'Imported verification result.',
  commands_text: '',
  artifact_content: '',
})
const repairAttempts = ref<RepairAttemptResponse[]>([])
const repairAttemptLoading = ref(false)
const repairAttemptError = ref('')
const timeline = ref<TimelineResponse | null>(null)
const evidenceBoard = ref<EvidenceBoardResponse | null>(null)
const evidenceSummaryLoading = ref(false)
const evidenceSummaryError = ref('')
const evidenceBoardCopyMessage = ref('')
const evidenceBoardFilterFields = ['evidence_type', 'source', 'status', 'provider', 'role'] as const
type EvidenceBoardFilterField = typeof evidenceBoardFilterFields[number]
const evidenceBoardFilter = ref<Record<EvidenceBoardFilterField, string>>({
  evidence_type: '',
  source: '',
  status: '',
  provider: '',
  role: '',
})
const projectMemory = ref<ProjectMemoryResponse | null>(null)
const projectMemorySummary = ref<ProjectMemorySummaryResponse | null>(null)
const projectMemoryLoading = ref(false)
const projectMemoryError = ref('')
const projectMemoryCopyMessage = ref('')
const projectMemoryFilterFields = ['memory_type', 'confidence', 'stale'] as const
type ProjectMemoryFilterField = typeof projectMemoryFilterFields[number]
const projectMemoryFilter = ref<Record<ProjectMemoryFilterField, string>>({
  memory_type: '',
  confidence: '',
  stale: '',
})
const mastermindChangedFilesText = ref('')
const mastermindPacketForm = ref<MastermindReviewPacketPreviewRequest>({
  pr_url: '',
  pr_number: null,
  head_commit: '',
  base_commit: '',
  changed_files: [],
  pr_body: '',
  verification_results: {
    targeted_backend_pytest: 'not_provided',
    full_backend_pytest: 'not_provided',
    compileall: 'not_provided',
    npm_build: 'not_provided',
    frontend_smoke: 'not_provided',
    git_diff_check: 'not_provided',
  },
  sonarcloud: {
    quality_gate: 'not_provided',
    security_hotspots: 0,
    duplication_on_new_code: 'not_provided',
    new_issues: 0,
  },
  include_evidence_board: true,
  include_timeline: true,
  include_project_memory: true,
  include_handoff_context: true,
  packet_budget: 12000,
})
const mastermindBrowserAiForm = ref<MastermindReviewBrowserAiOptions>({
  provider_profile: 'chatgpt_web',
  target_url: '',
  prompt_selector: '',
  submit_selector: '',
  response_selector: '',
  scroll_container_selector: '',
  copy_button_selector: '',
  login_hint_selector: '',
  stable_response_timeout_seconds: 120,
  stable_polls: 3,
  stable_interval_ms: 1000,
})
const mastermindSaveArtifact = ref(true)
const mastermindPreview = ref<MastermindReviewPacketPreviewResponse | null>(null)
const mastermindResult = ref<MastermindReviewExecuteResponse | null>(null)
const mastermindLoading = ref(false)
const mastermindExecuting = ref(false)
const mastermindError = ref('')
const mastermindRefreshMessage = ref('')
const mastermindGateHint = ref('')
const mastermindGateForm = ref({
  source_artifact_id: null as number | null,
  current_head_commit: '',
})
const mastermindGateResult = ref<MastermindReviewGatePreviewResponse | null>(null)
const mastermindGateLoading = ref(false)
const mastermindGateError = ref('')
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

const timelineItems = computed<TimelineItem[]>(() => (timeline.value?.items || []).slice(-20).reverse())
const evidenceBoardItems = computed<EvidenceBoardItem[]>(() => evidenceBoard.value?.items || [])
const evidenceBoardTotalCount = computed(() => evidenceBoardItems.value.length)
const evidenceFilterOptions = computed(() => {
  const responseFilters = evidenceBoard.value?.filters
  const fromItems = (key: EvidenceBoardFilterField) => {
    const values = evidenceBoardItems.value.map((item) => item[key] || '').filter((value) => value !== '')
    return Array.from(new Set(values)).sort()
  }
  return evidenceBoardFilterFields.reduce((options, field) => ({
    ...options,
    [field]: responseFilters?.[field]?.length ? responseFilters[field] : fromItems(field),
  }), {} as Record<EvidenceBoardFilterField, string[]>)
})
const filteredEvidenceBoardItems = computed(() => evidenceBoardItems.value.filter((item) => {
  const filters = evidenceBoardFilter.value
  return evidenceBoardFilterFields.every((field) => !filters[field] || item[field] === filters[field])
}))
const projectMemoryItems = computed<ProjectMemoryItem[]>(() => projectMemory.value?.items || [])
const projectMemoryTotalCount = computed(() => projectMemoryItems.value.length)
const projectMemoryFilterOptions = computed(() => {
  const responseFilters = projectMemory.value?.filters
  const fromItems = (field: ProjectMemoryFilterField) => {
    const values = projectMemoryItems.value.map((item) => String(item[field])).filter((value) => value !== '')
    return Array.from(new Set(values)).sort()
  }
  return {
    memory_type: responseFilters?.memory_type?.length ? responseFilters.memory_type : fromItems('memory_type'),
    confidence: responseFilters?.confidence?.length ? responseFilters.confidence : fromItems('confidence'),
    stale: responseFilters?.stale?.length ? responseFilters.stale.map(String) : fromItems('stale'),
  } as Record<ProjectMemoryFilterField, string[]>
})
const filteredProjectMemoryItems = computed(() => projectMemoryItems.value.filter((item) => {
  const filters = projectMemoryFilter.value
  return projectMemoryFilterFields.every((field) => !filters[field] || String(item[field]) === filters[field])
}))

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

function formatMcpPreview(data: Record<string, unknown> | null | undefined) {
  if (!data || Object.keys(data).length === 0) return '-'
  return JSON.stringify(data, null, 2).slice(0, 4000)
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

function formatBrowserAiSafetyGate(gate: BrowserAiSafetyGate) {
  return JSON.stringify(gate, null, 2)
}

function formatEvidenceSafetyGate(gate: MultiAiEvidenceSafetyGate) {
  return JSON.stringify(gate, null, 2)
}

function formatFailureEvidencePacket(packet: FailureEvidencePacketResponse) {
  return JSON.stringify(packet, null, 2)
}

function stepHint(name: string, status: string) {
  if (status === 'failed') {
    const hints: Record<string, string> = {
      validate_request: 'Request blocked by safety gate or missing selector.',
      build_prompt: 'Task context could not be loaded.',
      open_browser: 'Browser launch failed.',
      navigate: 'Target page could not be loaded.',
      detect_login: 'Manual login may be required. Complete login in the opened browser, then retry Execute.',
      fill_prompt: 'Input box was not found or could not be filled.',
      click_send: 'Send button was not found or could not be clicked.',
      wait_response: 'Timed out waiting for a stable answer; the page may still be generating, manual login may be required, or selector may be wrong.',
      capture_answer: 'Visible answer could not be captured from response_selector.',
      persist_artifact: 'Answer could not be saved.',
    }
    return hints[name] || 'Browser AI step failed.'
  }
  if (status === 'skipped') return 'Skipped after previous step.'
  if (status === 'running') return 'Running...'
  return status
}

function buildBrowserAiRequest(): BrowserAiRequest | null {
  if (!task.value) return null
  return {
    ...browserAiForm.value,
    project_id: task.value.project_id,
    task_id: task.value.id,
  }
}

function buildEvidenceRunRequest(): MultiAiEvidenceRunRequest | null {
  if (!task.value) return null
  return {
    ...multiAiForm.value,
    task_id: task.value.id,
    providers: multiAiForm.value.mode === 'broadcast' ? multiAiForm.value.providers : [],
    roles: multiAiForm.value.mode === 'routed' ? multiAiForm.value.roles : [],
  }
}

function buildFailureEvidenceRequest(): FailureEvidencePreviewRequest | null {
  if (!task.value) return null
  const source = failureEvidenceForm.value.source
  return {
    ...failureEvidenceForm.value,
    task_id: task.value.id,
    source: {
      agent_run_id: source.agent_run_id || null,
      artifact_id: source.artifact_id || null,
      dispatch_batch_id: source.dispatch_batch_id || null,
      dispatch_job_id: source.dispatch_job_id || null,
    },
  }
}

function buildRepairPacketRequest(): RepairPacketGenerateRequest | null {
  if (!task.value || !failureEvidencePacket.value) return null
  return {
    task_id: task.value.id,
    failure_evidence: failureEvidencePacket.value,
    analysis_mode: repairPacketForm.value.analysis_mode,
    providers: repairPacketForm.value.analysis_mode === 'broadcast' ? repairPacketForm.value.providers : [],
    roles: repairPacketForm.value.analysis_mode === 'routed' ? repairPacketForm.value.roles : [],
    max_attempts: 1,
  }
}

function buildRepairHandoffRequest(): RepairHandoffPreviewRequest | null {
  if (!task.value || !repairHandoffForm.value.repair_packet_artifact_id) return null
  return {
    task_id: task.value.id,
    repair_packet_artifact_id: repairHandoffForm.value.repair_packet_artifact_id,
    target: repairHandoffForm.value.target,
  }
}

function buildRepairAttemptRequest(): RepairAttemptCreateRequest | null {
  if (!task.value || !repairAttemptForm.value.repair_packet_artifact_id) return null
  return {
    task_id: task.value.id,
    executor: repairAttemptForm.value.executor,
    failure_evidence_artifact_id: repairAttemptForm.value.failure_evidence_artifact_id || null,
    repair_packet_artifact_id: repairAttemptForm.value.repair_packet_artifact_id,
    handoff_target: repairAttemptForm.value.handoff_target,
    summary: repairAttemptForm.value.summary,
  }
}

function parseMastermindChangedFiles() {
  return mastermindChangedFilesText.value
    .split(/[\n,]/)
    .map(file => file.trim())
    .filter(Boolean)
}

function buildMastermindPacketRequest(): MastermindReviewPacketPreviewRequest {
  return {
    ...mastermindPacketForm.value,
    changed_files: parseMastermindChangedFiles(),
    pr_number: mastermindPacketForm.value.pr_number ? Number(mastermindPacketForm.value.pr_number) : null,
    packet_budget: Number(mastermindPacketForm.value.packet_budget) || 12000,
    sonarcloud: {
      quality_gate: mastermindPacketForm.value.sonarcloud.quality_gate,
      security_hotspots: Number(mastermindPacketForm.value.sonarcloud.security_hotspots) || 0,
      duplication_on_new_code: mastermindPacketForm.value.sonarcloud.duplication_on_new_code,
      new_issues: Number(mastermindPacketForm.value.sonarcloud.new_issues) || 0,
    },
  }
}

function buildMastermindExecuteRequest(): MastermindReviewExecuteRequest {
  return {
    packet: buildMastermindPacketRequest(),
    browser_ai: {
      ...mastermindBrowserAiForm.value,
      stable_response_timeout_seconds: mastermindBrowserAiForm.value.stable_response_timeout_seconds
        ? Number(mastermindBrowserAiForm.value.stable_response_timeout_seconds)
        : null,
      stable_polls: Number(mastermindBrowserAiForm.value.stable_polls) || 3,
      stable_interval_ms: Number(mastermindBrowserAiForm.value.stable_interval_ms) || 1000,
    },
    save_artifact: mastermindSaveArtifact.value,
  }
}

function buildMastermindGateRequest(): MastermindReviewGatePreviewRequest {
  return {
    source_artifact_id: mastermindGateForm.value.source_artifact_id ? Number(mastermindGateForm.value.source_artifact_id) : null,
    current_head_commit: mastermindGateForm.value.current_head_commit || mastermindPacketForm.value.head_commit,
    pr_url: mastermindPacketForm.value.pr_url,
    pr_number: mastermindPacketForm.value.pr_number ? Number(mastermindPacketForm.value.pr_number) : null,
    verification_results: { ...mastermindPacketForm.value.verification_results },
    sonarcloud: {
      quality_gate: mastermindPacketForm.value.sonarcloud.quality_gate,
      security_hotspots: Number(mastermindPacketForm.value.sonarcloud.security_hotspots) || 0,
      duplication_on_new_code: mastermindPacketForm.value.sonarcloud.duplication_on_new_code,
      new_issues: Number(mastermindPacketForm.value.sonarcloud.new_issues) || 0,
    },
  }
}

function formatMastermindJson(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function formatMastermindList(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) return '-'
  return value.map(item => (typeof item === 'string' ? item : JSON.stringify(item))).join('; ')
}

function formatMastermindPacketField(key: string) {
  const packet = mastermindPreview.value?.packet as Record<string, any> | undefined
  return formatMastermindJson(packet?.[key])
}

function mastermindManualLoginRequired() {
  const text = `${mastermindError.value} ${mastermindResult.value?.failure_reason || ''} ${mastermindResult.value?.summary || ''}`
  return /manual login|login required|detect_login|login/i.test(text)
}

function buildRepairVerificationRequest(): RepairVerificationResultRequest {
  return {
    status: repairVerificationForm.value.status,
    summary: repairVerificationForm.value.summary,
    commands: repairVerificationForm.value.commands_text.split('\n').map(command => command.trim()).filter(Boolean),
    artifact_content: repairVerificationForm.value.artifact_content,
  }
}

function addEvidenceRole() {
  multiAiForm.value.roles.push({ role: 'risk', provider: 'gemini_web', prompt: 'Check risks and missing evidence.' })
}

function removeEvidenceRole(index: number) {
  if (multiAiForm.value.roles.length <= 1) return
  multiAiForm.value.roles.splice(index, 1)
}

function addRepairRole() {
  repairPacketForm.value.roles.push({ role: 'test', provider: 'gemini_web', prompt: 'Suggest verification commands and residual risks.' })
}

function removeRepairRole(index: number) {
  if (repairPacketForm.value.roles.length <= 1) return
  repairPacketForm.value.roles.splice(index, 1)
}

onMounted(async () => {
  await loadBrowserAiProfiles()
  await loadMcpTools()
  agents.value = await fetchAgents()
  await refresh()
})

async function loadMcpTools() {
  try {
    mcpTools.value = await fetchMcpTools()
  } catch (err: any) {
    mcpTools.value = []
    mcpError.value = err?.message || 'MCP tools unavailable'
  }
}

async function loadBrowserAiProfiles() {
  try {
    const profiles = await fetchBrowserAiProviderProfiles()
    if (profiles.length > 0) browserAiProfiles.value = profiles
  } catch (err) {
    console.warn('Failed to load Browser AI provider profiles; using local fallback profiles.', err)
  }
}

function applyBrowserAiProfile() {
  const profile = selectedBrowserAiProfile.value
  if (!profile || profile.provider === 'custom') return
  browserAiForm.value.target_url = profile.target_url || browserAiForm.value.target_url
  browserAiForm.value.input_selector = profile.input_selector || browserAiForm.value.input_selector
  browserAiForm.value.send_selector = profile.send_selector || browserAiForm.value.send_selector
  browserAiForm.value.response_selector = profile.response_selector || browserAiForm.value.response_selector
  browserAiForm.value.scroll_container_selector = profile.scroll_container_selector || ''
  browserAiForm.value.copy_button_selector = profile.copy_button_selector || ''
  browserAiForm.value.login_hint_selector = profile.login_hint_selector || ''
}

function applyMastermindBrowserProfile() {
  const profile = browserAiProfiles.value.find(item => item.provider === mastermindBrowserAiForm.value.provider_profile)
  if (!profile || profile.provider === 'custom') return
  mastermindBrowserAiForm.value.target_url = profile.target_url || mastermindBrowserAiForm.value.target_url
  mastermindBrowserAiForm.value.prompt_selector = profile.input_selector || mastermindBrowserAiForm.value.prompt_selector
  mastermindBrowserAiForm.value.submit_selector = profile.send_selector || mastermindBrowserAiForm.value.submit_selector
  mastermindBrowserAiForm.value.response_selector = profile.response_selector || mastermindBrowserAiForm.value.response_selector
  mastermindBrowserAiForm.value.scroll_container_selector = profile.scroll_container_selector || ''
  mastermindBrowserAiForm.value.copy_button_selector = profile.copy_button_selector || ''
  mastermindBrowserAiForm.value.login_hint_selector = profile.login_hint_selector || ''
}

async function refresh() {
  const id = Number(route.params.id)
  task.value = await taskStore.fetchTask(id)
  realAiTaskGoal.value = defaultRealAiTaskGoal()
  browserAiForm.value.project_id = task.value.project_id
  browserAiForm.value.task_id = task.value.id
  multiAiForm.value.task_id = task.value.id
  failureEvidenceForm.value.task_id = task.value.id
  agentRuns.value = await fetchAgentRuns(id)
  agentReviews.value = await fetchAgentReviews(id)
  approvalDecisions.value = await fetchApprovalDecisions(id)
  await loadDispatchBatches(id)
  await loadAiHandoff()
  await loadRepairAttempts(id)
  await loadEvidenceSummary(id)
  await loadProjectMemory(task.value.project_id)
  codeContext.value = await fetchCodeContext(id)
  sandboxResults.value = await fetchSandboxResults(id)
  applyResult.value = null
  await loadSandboxGate()
}

async function previewMcpHandoff() {
  if (!task.value) return
  mcpLoading.value = true
  mcpError.value = ''
  try {
    if (mcpTools.value.length === 0) {
      await loadMcpTools()
    }
    mcpResult.value = await callMcpTool({
      tool: 'get_handoff_packet',
      arguments: {
        task_id: task.value.id,
        budget: 4000,
      },
    })
  } catch (err: any) {
    mcpResult.value = null
    mcpError.value = err?.message || 'MCP handoff preview failed'
  } finally {
    mcpLoading.value = false
  }
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

async function runBrowserAiDryRun() {
  const body = buildBrowserAiRequest()
  if (!body) return
  browserAiLoading.value = true
  browserAiError.value = ''
  try {
    browserAiDryRunResult.value = await dryRunBrowserAi(body)
  } catch (e: any) {
    browserAiDryRunResult.value = null
    browserAiError.value = e.message || 'Browser AI dry-run failed'
  } finally {
    browserAiLoading.value = false
  }
}

async function executeBrowserAiRun() {
  const body = buildBrowserAiRequest()
  if (!body) return
  browserAiLoading.value = true
  browserAiError.value = ''
  browserAiRefreshMessages.value = []
  try {
    browserAiExecuteResult.value = await executeBrowserAi(body)
    if (browserAiExecuteResult.value.status === 'succeeded' && browserAiExecuteResult.value.persisted) {
      await refreshAfterBrowserAiRun()
    }
  } catch (e: any) {
    browserAiExecuteResult.value = null
    browserAiError.value = e.message || 'Browser AI execute failed'
  } finally {
    browserAiLoading.value = false
  }
}

async function previewMastermindReview() {
  if (!task.value) return
  mastermindLoading.value = true
  mastermindError.value = ''
  mastermindRefreshMessage.value = ''
  mastermindGateHint.value = ''
  try {
    mastermindPreview.value = await previewMastermindReviewPacket(task.value.id, buildMastermindPacketRequest())
  } catch (e: any) {
    mastermindPreview.value = null
    mastermindError.value = e.message || 'Mastermind Review packet preview failed'
  } finally {
    mastermindLoading.value = false
  }
}

async function runMastermindReview() {
  if (!task.value) return
  mastermindExecuting.value = true
  mastermindError.value = ''
  mastermindRefreshMessage.value = ''
  mastermindGateHint.value = ''
  try {
    mastermindResult.value = await executeMastermindReview(task.value.id, buildMastermindExecuteRequest())
    if (mastermindResult.value.status === 'succeeded' && mastermindResult.value.persisted) {
      await refreshAfterMastermindReview()
    }
  } catch (e: any) {
    mastermindResult.value = null
    mastermindError.value = e.message || 'Browser AI Mastermind Review failed'
  } finally {
    mastermindExecuting.value = false
  }
}

async function previewControlledGate() {
  if (!task.value) return
  mastermindGateLoading.value = true
  mastermindGateError.value = ''
  try {
    mastermindGateResult.value = await previewMastermindReviewGate(task.value.id, buildMastermindGateRequest())
  } catch (e: any) {
    mastermindGateResult.value = null
    mastermindGateError.value = e.message || 'Controlled Mastermind Gate preview failed'
  } finally {
    mastermindGateLoading.value = false
  }
}

async function previewEvidenceRun() {
  const body = buildEvidenceRunRequest()
  if (!body) return
  multiAiLoading.value = true
  multiAiError.value = ''
  try {
    multiAiPreviewResult.value = await previewMultiAiEvidenceRun(body)
  } catch (e: any) {
    multiAiPreviewResult.value = null
    multiAiError.value = e.message || 'Multi-AI Evidence Run preview failed'
  } finally {
    multiAiLoading.value = false
  }
}

async function executeEvidenceRun() {
  const body = buildEvidenceRunRequest()
  if (!body) return
  multiAiLoading.value = true
  multiAiError.value = ''
  multiAiRefreshMessages.value = []
  try {
    multiAiExecuteResult.value = await executeMultiAiEvidenceRun(body)
    if (['succeeded', 'partial'].includes(multiAiExecuteResult.value.overall_status)) {
      await refreshAfterEvidenceRun()
    }
  } catch (e: any) {
    multiAiExecuteResult.value = null
    multiAiError.value = e.message || 'Multi-AI Evidence Run execute failed'
  } finally {
    multiAiLoading.value = false
  }
}

async function previewFailureEvidence() {
  const body = buildFailureEvidenceRequest()
  if (!body) return
  failureEvidenceLoading.value = true
  failureEvidenceError.value = ''
  try {
    failureEvidencePacket.value = await previewFailureEvidencePacket(body)
    repairPacketResult.value = null
  } catch (e: any) {
    failureEvidencePacket.value = null
    failureEvidenceError.value = e.message || 'Failure Evidence Packet preview failed'
  } finally {
    failureEvidenceLoading.value = false
  }
}

async function generateRepairPacketFromEvidence() {
  const body = buildRepairPacketRequest()
  if (!body) return
  repairPacketLoading.value = true
  repairPacketError.value = ''
  try {
    repairPacketResult.value = await generateRepairPacket(body)
    if (repairPacketResult.value.repair_packet_artifact_id) {
      repairHandoffForm.value.repair_packet_artifact_id = repairPacketResult.value.repair_packet_artifact_id
      repairAttemptForm.value.repair_packet_artifact_id = repairPacketResult.value.repair_packet_artifact_id
      repairHandoffResult.value = null
    }
    artifactRefreshKey.value += 1
    await loadAiHandoff()
  } catch (e: any) {
    repairPacketResult.value = null
    repairPacketError.value = e.message || 'Repair Packet generation failed'
  } finally {
    repairPacketLoading.value = false
  }
}

async function previewCodexRepairHandoff() {
  const body = buildRepairHandoffRequest()
  if (!body) return
  repairHandoffLoading.value = true
  repairHandoffError.value = ''
  repairHandoffCopyMessage.value = ''
  try {
    repairHandoffResult.value = await previewRepairHandoff(body)
  } catch (e: any) {
    repairHandoffResult.value = null
    repairHandoffError.value = e.message || 'Repair handoff preview failed'
  } finally {
    repairHandoffLoading.value = false
  }
}

async function loadRepairAttempts(id: number) {
  repairAttemptError.value = ''
  try {
    repairAttempts.value = await fetchRepairAttempts(id)
  } catch (e: any) {
    repairAttempts.value = []
    repairAttemptError.value = e.message || 'Repair attempts failed to load'
  }
}

async function loadRepairAttemptsForTask() {
  if (!task.value) return
  await loadRepairAttempts(task.value.id)
}

async function loadEvidenceSummary(id: number) {
  evidenceSummaryLoading.value = true
  evidenceSummaryError.value = ''
  evidenceBoardCopyMessage.value = ''
  try {
    const [timelineResult, boardResult] = await Promise.all([
      fetchTaskTimeline(id),
      fetchTaskEvidenceBoard(id),
    ])
    timeline.value = timelineResult
    evidenceBoard.value = boardResult
  } catch (e: any) {
    timeline.value = null
    evidenceBoard.value = null
    evidenceSummaryError.value = e.message || 'Evidence summary failed to load'
  } finally {
    evidenceSummaryLoading.value = false
  }
}

async function refreshEvidenceSummary() {
  if (!task.value) return
  await loadEvidenceSummary(task.value.id)
}

async function loadProjectMemory(projectId: number) {
  projectMemoryLoading.value = true
  projectMemoryError.value = ''
  projectMemoryCopyMessage.value = ''
  try {
    const [memoryResult, summaryResult] = await Promise.all([
      fetchProjectMemory(projectId),
      fetchProjectMemorySummary(projectId),
    ])
    projectMemory.value = memoryResult
    projectMemorySummary.value = summaryResult
  } catch (e: any) {
    projectMemory.value = null
    projectMemorySummary.value = null
    projectMemoryError.value = e.message || 'Project Memory failed to load'
  } finally {
    projectMemoryLoading.value = false
  }
}

async function refreshProjectMemory() {
  if (!task.value) return
  await loadProjectMemory(task.value.project_id)
}

function formatLinkedIds(ids: EvidenceLinkedIds) {
  const parts = [
    ['agent_run_id', ids.agent_run_id],
    ['artifact_id', ids.artifact_id],
    ['dispatch_batch_id', ids.dispatch_batch_id],
    ['dispatch_job_id', ids.dispatch_job_id],
    ['repair_attempt_id', ids.repair_attempt_id],
  ].filter(([, value]) => value !== null && value !== undefined)
  return parts.length ? parts.map(([key, value]) => `${key}: ${value}`).join(', ') : '-'
}

function formatEvidenceItemLinkedIds(item: EvidenceBoardItem) {
  return formatLinkedIds({
    agent_run_id: item.agent_run_id,
    artifact_id: item.artifact_id,
    dispatch_batch_id: item.dispatch_batch_id,
    dispatch_job_id: item.dispatch_job_id,
    repair_attempt_id: item.repair_attempt_id,
  })
}

function clearEvidenceBoardFilters() {
  evidenceBoardFilter.value = Object.fromEntries(evidenceBoardFilterFields.map((field) => [field, ''])) as Record<EvidenceBoardFilterField, string>
}

function evidenceItemHasArtifact(item: EvidenceBoardItem) {
  return item.artifact_id !== null && item.artifact_id !== undefined
}

function evidenceItemHasRisk(item: EvidenceBoardItem) {
  const riskText = [
    item.summary,
    item.raw_excerpt,
    ...(item.safety_notes || []),
  ].join(' ').toLowerCase()
  return ['risk', 'failed', 'blocked', 'warning', 'unsafe', 'human decision'].some((keyword) => riskText.includes(keyword))
}

function evidenceSafetyBoundary(item: EvidenceBoardItem) {
  const notes = item.safety_notes || []
  const boundary = notes.find((note) => /no |read-only|must|not |human/i.test(note))
  return boundary || 'none recorded'
}

function evidenceSummaryText(item: EvidenceBoardItem) {
  return [
    ...evidenceBoardFilterFields.map((field) => `${field}: ${item[field] || '-'}`),
    `linked ids: ${formatEvidenceItemLinkedIds(item)}`,
    `summary: ${item.summary || '-'}`,
    `has_artifact=${evidenceItemHasArtifact(item)}`,
    `has_risk=${evidenceItemHasRisk(item)}`,
    `safety_notes: ${(item.safety_notes || []).join('; ') || '-'}`,
  ].join('\n')
}

function evidenceDetailRows(item: EvidenceBoardItem) {
  return [
    ...evidenceBoardFilterFields.map((field) => `${field}: ${item[field] || '-'}`),
    `linked ids: ${formatEvidenceItemLinkedIds(item)}`,
    `summary: ${item.summary || '-'}`,
    `has_artifact=${evidenceItemHasArtifact(item)}`,
    `has_risk=${evidenceItemHasRisk(item)}`,
    `redaction_status: redaction_applied=${item.redaction_status.redaction_applied}, truncated=${item.redaction_status.truncated}, max_chars=${item.redaction_status.max_chars}`,
  ]
}

async function copyEvidenceText(text: string, successMessage: string) {
  try {
    await navigator.clipboard.writeText(text)
    evidenceBoardCopyMessage.value = successMessage
  } catch {
    evidenceBoardCopyMessage.value = 'copy failed; select the text manually'
  }
}

async function copyEvidenceSummary(item: EvidenceBoardItem) {
  await copyEvidenceText(evidenceSummaryText(item), 'evidence summary copied')
}

async function copyEvidenceLinkedIds(item: EvidenceBoardItem) {
  await copyEvidenceText(formatEvidenceItemLinkedIds(item), 'linked ids copied')
}

function clearProjectMemoryFilters() {
  projectMemoryFilter.value = Object.fromEntries(projectMemoryFilterFields.map((field) => [field, ''])) as Record<ProjectMemoryFilterField, string>
}

function formatProjectMemorySourceRefs(refs: ProjectMemorySourceRef[]) {
  if (!refs.length) return '-'
  return refs.map((ref) => {
    const parts = [
      ref.source_type,
      ref.path,
      ref.section ? `section=${ref.section}` : '',
      ref.pr_number ? `pr_number=${ref.pr_number}` : '',
      ref.note ? `note=${ref.note}` : '',
    ].filter(Boolean)
    return parts.join(':')
  }).join(', ')
}

function formatProjectMemoryContent(content: Record<string, unknown>) {
  return JSON.stringify(content || {}, null, 2)
}

function projectMemorySummaryText(item: ProjectMemoryItem) {
  return [
    `memory_type: ${item.memory_type}`,
    `title: ${item.title}`,
    `summary: ${item.summary || '-'}`,
    `confidence: ${item.confidence}`,
    `stale: ${item.stale}`,
    `updated_at: ${item.updated_at}`,
    `source_refs: ${formatProjectMemorySourceRefs(item.source_refs)}`,
  ].join('\n')
}

async function copyProjectMemoryText(text: string, successMessage: string) {
  try {
    await navigator.clipboard.writeText(text)
    projectMemoryCopyMessage.value = successMessage
  } catch {
    projectMemoryCopyMessage.value = 'copy failed; select the text manually'
  }
}

async function copyProjectMemorySummary(item: ProjectMemoryItem) {
  await copyProjectMemoryText(projectMemorySummaryText(item), 'memory summary copied')
}

async function copyProjectMemorySourceRefs(item: ProjectMemoryItem) {
  await copyProjectMemoryText(formatProjectMemorySourceRefs(item.source_refs), 'source refs copied')
}

function selectRepairAttempt(attempt: RepairAttemptResponse) {
  repairVerificationForm.value.attempt_id = attempt.repair_attempt_id
  repairAttemptForm.value.repair_packet_artifact_id = attempt.repair_packet_artifact_id
  repairAttemptForm.value.failure_evidence_artifact_id = attempt.failure_evidence_artifact_id
}

async function createRepairAttemptFromTimeline() {
  const body = buildRepairAttemptRequest()
  if (!body || !task.value) return
  repairAttemptLoading.value = true
  repairAttemptError.value = ''
  try {
    const attempt = await createRepairAttempt(body)
    selectRepairAttempt(attempt)
    await loadRepairAttempts(task.value.id)
  } catch (e: any) {
    repairAttemptError.value = e.message || 'Repair attempt creation failed'
  } finally {
    repairAttemptLoading.value = false
  }
}

async function markSelectedAttemptHandoffCreated() {
  if (!task.value || !repairVerificationForm.value.attempt_id) return
  repairAttemptLoading.value = true
  repairAttemptError.value = ''
  try {
    const attempt = await markRepairHandoffCreated(repairVerificationForm.value.attempt_id)
    selectRepairAttempt(attempt)
    await loadRepairAttempts(task.value.id)
  } catch (e: any) {
    repairAttemptError.value = e.message || 'Repair handoff status update failed'
  } finally {
    repairAttemptLoading.value = false
  }
}

async function importSelectedVerificationResult() {
  if (!task.value || !repairVerificationForm.value.attempt_id) return
  repairAttemptLoading.value = true
  repairAttemptError.value = ''
  try {
    const attempt = await importRepairVerificationResult(repairVerificationForm.value.attempt_id, buildRepairVerificationRequest())
    selectRepairAttempt(attempt)
    artifactRefreshKey.value += 1
    await loadRepairAttempts(task.value.id)
  } catch (e: any) {
    repairAttemptError.value = e.message || 'Verification result import failed'
  } finally {
    repairAttemptLoading.value = false
  }
}

async function stopSelectedRepairAttempt() {
  if (!task.value || !repairVerificationForm.value.attempt_id) return
  repairAttemptLoading.value = true
  repairAttemptError.value = ''
  try {
    const attempt = await stopRepairAttempt(repairVerificationForm.value.attempt_id)
    selectRepairAttempt(attempt)
    await loadRepairAttempts(task.value.id)
  } catch (e: any) {
    repairAttemptError.value = e.message || 'Repair attempt stop failed'
  } finally {
    repairAttemptLoading.value = false
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

async function refreshAfterBrowserAiRun() {
  if (!task.value) return
  const id = task.value.id
  const messages = ['Browser AI answer saved']
  agentRuns.value = await fetchAgentRuns(id)
  messages.push('AgentRuns refreshed')
  artifactRefreshKey.value += 1
  messages.push('Artifacts refreshed')
  agentReviews.value = await fetchAgentReviews(id)
  await loadDispatchBatches(id)
  await loadAnswerSynthesis(id, latestDispatchBatchId())
  if (answerSynthesis.value) {
    messages.push('Answer Synthesis refreshed')
  } else {
    messages.push(answerSynthesisError.value || 'Answer Synthesis not refreshed: no Browser AI artifact or dispatch source available')
  }
  await loadAiHandoff()
  sandboxResults.value = await fetchSandboxResults(id)
  await loadSandboxGate()
  browserAiRefreshMessages.value = messages
}

async function refreshAfterMastermindReview() {
  if (!task.value) return
  const id = task.value.id
  agentRuns.value = await fetchAgentRuns(id)
  artifactRefreshKey.value += 1
  await loadEvidenceSummary(id)
  if (mastermindResult.value?.artifact_id) {
    mastermindGateForm.value.source_artifact_id = mastermindResult.value.artifact_id
  }
  mastermindGateForm.value.current_head_commit = mastermindPacketForm.value.head_commit
  mastermindRefreshMessage.value = 'Mastermind Review saved; AgentRun, artifacts, Timeline, and Evidence Board refreshed'
  mastermindGateHint.value = 'Click Preview Controlled Gate to classify the review before human confirmation.'
}

async function refreshAfterEvidenceRun() {
  if (!task.value) return
  const id = task.value.id
  const messages = ['Multi-AI Evidence Run saved']
  agentRuns.value = await fetchAgentRuns(id)
  messages.push('AgentRuns refreshed')
  artifactRefreshKey.value += 1
  messages.push('Artifacts refreshed')
  await loadDispatchBatches(id)
  messages.push('DispatchBatches refreshed')
  if (multiAiExecuteResult.value?.dispatch_batch_id) {
    await loadAnswerSynthesis(id, multiAiExecuteResult.value.dispatch_batch_id)
  } else {
    await loadAnswerSynthesis(id, latestDispatchBatchId())
  }
  if (answerSynthesis.value || multiAiExecuteResult.value?.synthesis_refreshed) {
    messages.push('Answer Synthesis refreshed')
  } else {
    messages.push(answerSynthesisError.value || 'Answer Synthesis not refreshed: no successful evidence artifact available')
  }
  await loadAiHandoff()
  multiAiRefreshMessages.value = messages
}

async function loadDispatchBatches(id: number) {
  dispatchBatchError.value = ''
  try {
    dispatchBatches.value = await fetchDispatchBatches(id)
    await loadAnswerSynthesis(id, latestDispatchBatchId())
  } catch (e: any) {
    dispatchBatches.value = []
    answerSynthesis.value = null
    dispatchBatchError.value = e.message || '多 AI Dispatch 记录加载失败'
  }
}

async function loadAnswerSynthesis(taskId: number, dispatchBatchId?: number | null) {
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
    const message = e.message || '多 AI 综合结论加载失败'
    answerSynthesisError.value = message === 'dispatch_batch_not_found' ? '' : message
  } finally {
    answerSynthesisLoading.value = false
  }
}

async function refreshAnswerSynthesis() {
  if (!task.value) return
  await loadAnswerSynthesis(task.value.id, latestDispatchBatchId())
}

function latestDispatchBatchId() {
  const latestBatch = dispatchBatches.value[dispatchBatches.value.length - 1]
  return latestBatch?.dispatch_batch_id || null
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

async function copyRepairHandoffPrompt() {
  if (!repairHandoffResult.value?.handoff_prompt) return
  try {
    await navigator.clipboard.writeText(repairHandoffResult.value.handoff_prompt)
    repairHandoffCopyMessage.value = 'repair handoff prompt 已复制'
  } catch {
    repairHandoffCopyMessage.value = '复制失败，请手动选择文本'
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
.browser-ai-run { border-left: 3px solid #00897b; }
.multi-ai-evidence-run { border-left: 3px solid #6a1b9a; }
.failure-evidence-preview { border-left: 3px solid #ad5700; }
.repair-packet-generation { border-left: 3px solid #2e7d32; }
.repair-handoff-preview { border-left: 3px solid #2563eb; }
.repair-attempt-timeline { border-left: 3px solid #455a64; }
.browser-ai-help { margin: 8px 0 0; color: var(--color-text-secondary); font-size: 12px; line-height: 1.5; }
.browser-ai-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; margin-top: 12px; }
.browser-ai-form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.browser-ai-form .wide { grid-column: 1 / -1; }
.browser-ai-form textarea { min-height: 90px; resize: vertical; }
.multi-ai-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: start; margin-top: 12px; }
.multi-ai-form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.multi-ai-form .wide { grid-column: 1 / -1; }
.multi-ai-form textarea { min-height: 90px; resize: vertical; }
.failure-evidence-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: start; margin-top: 12px; }
.failure-evidence-form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.failure-evidence-form .wide { grid-column: 1 / -1; }
.failure-evidence-result pre { max-height: 420px; overflow: auto; }
.repair-packet-form,
.repair-handoff-form,
.repair-attempt-form,
.repair-verification-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: start; margin-top: 12px; }
.repair-packet-form label,
.repair-handoff-form label,
.repair-attempt-form label,
.repair-verification-form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.repair-packet-form .wide,
.repair-attempt-form .wide,
.repair-verification-form .wide { grid-column: 1 / -1; }
.repair-attempt-list { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.repair-attempt-item { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.evidence-summary-panel { border-left: 3px solid #00695c; }
.evidence-summary-flags,
.evidence-filters { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 12px; }
.evidence-summary-flags span,
.evidence-filters span { padding: 3px 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; font-size: 12px; color: var(--color-text-secondary); }
.evidence-summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
.timeline-panel,
.evidence-board-panel { min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.evidence-board-controls { display: grid; grid-template-columns: repeat(5, minmax(96px, 1fr)); gap: 8px; align-items: end; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.evidence-board-controls label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--color-text-secondary); }
.evidence-board-controls button,
.evidence-board-controls .workspace-readonly { align-self: end; }
.evidence-board-controls .workspace-readonly { grid-column: 1 / -1; }
.timeline-list,
.evidence-board-list { display: flex; flex-direction: column; gap: 10px; }
.timeline-item,
.evidence-board-item { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.timeline-item-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 6px; }
.timeline-item-header strong { font-size: 13px; word-break: break-word; }
.evidence-item-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.evidence-excerpt { margin-top: 8px; }
.evidence-excerpt summary { cursor: pointer; color: var(--color-text-secondary); font-size: 12px; }
.evidence-excerpt pre { margin-top: 6px; max-height: 160px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--color-text-secondary); padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.project-memory-panel { border-left: 3px solid #4e6f1f; }
.project-memory-flags,
.project-memory-filters { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 12px; }
.project-memory-flags span,
.project-memory-filters span { padding: 3px 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; font-size: 12px; color: var(--color-text-secondary); }
.project-memory-summary,
.project-memory-item { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.project-memory-controls { display: grid; grid-template-columns: repeat(3, minmax(120px, 1fr)) auto; gap: 8px; align-items: end; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; margin: 12px 0; }
.project-memory-controls label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--color-text-secondary); }
.project-memory-controls .workspace-readonly { grid-column: 1 / -1; }
.project-memory-list { display: flex; flex-direction: column; gap: 10px; }
.project-memory-content { margin-top: 8px; }
.project-memory-content summary { cursor: pointer; color: var(--color-text-secondary); font-size: 12px; }
.project-memory-content pre { margin-top: 6px; max-height: 180px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--color-text-secondary); padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.mastermind-review-panel { border-left: 3px solid #7b4e12; }
.mastermind-review-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr); gap: 12px; align-items: start; }
.mastermind-review-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.mastermind-review-form label,
.mastermind-review-subgrid label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.mastermind-review-form .wide { grid-column: 1 / -1; }
.mastermind-review-form textarea { min-height: 86px; resize: vertical; }
.mastermind-review-subgrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.mastermind-checkboxes { display: flex; flex-wrap: wrap; gap: 8px; }
.mastermind-review-results { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.mastermind-result-card { padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.mastermind-detail { margin-top: 8px; }
.mastermind-detail summary { cursor: pointer; color: var(--color-text-secondary); font-size: 12px; }
.mastermind-detail pre { margin-top: 6px; max-height: 260px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--color-text-secondary); padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fff; }
.controlled-gate-panel { display: flex; flex-direction: column; gap: 10px; padding: 10px; border: 1px solid #d6c18f; border-radius: var(--radius); background: #fffdf7; }
.gate-status-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; font-family: monospace; }
.gate-status-badge.gate_advisory_approved { background: #e8f5e9; color: #2e7d32; }
.gate-status-badge.gate_request_changes,
.gate-status-badge.gate_blocked_by_safety { background: #ffebee; color: #c62828; }
.gate-status-badge.gate_stale_review,
.gate-status-badge.gate_invalid_review,
.gate-status-badge.gate_needs_human { background: #fff3e0; color: #9a5b00; }
.gate-status-badge.gate_not_ready { background: #f5f5f5; color: #616161; }
.gate-advisory-message { display: block; }
.gate-status-taxonomy { display: flex; flex-wrap: wrap; gap: 6px; border-top: 1px solid var(--color-border); padding-top: 8px; font-size: 12px; color: var(--color-text-secondary); }
.repair-list { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.repair-list span { padding: 3px 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; font-size: 12px; color: var(--color-text-secondary); }
.provider-picker { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.checkbox-row { display: inline-flex !important; flex-direction: row !important; align-items: center; gap: 6px !important; }
.routed-roles { display: flex; flex-direction: column; gap: 8px; }
.section-header.compact { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
.routed-role-row { display: grid; grid-template-columns: 140px 180px minmax(0, 1fr) auto; gap: 8px; align-items: end; padding: 10px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; }
.role-prompt { min-width: 0; }
.selector-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding: 10px 0; }
.evidence-result { border-color: #d8c5e8; }
.browser-ai-steps { display: flex; flex-direction: column; gap: 8px; }
.browser-ai-steps ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.browser-ai-step { display: grid; grid-template-columns: minmax(120px, 1fr) 76px minmax(0, 2fr); gap: 8px; align-items: center; padding: 7px 8px; border: 1px solid var(--color-border); border-radius: var(--radius); background: #fafafa; font-size: 12px; }
.browser-ai-step.failed { border-color: #f5b5b5; background: #fff5f5; color: #b71c1c; }
.browser-ai-step.passed { border-color: #b7dfc3; background: #f5fbf7; }
.browser-ai-step.running { border-color: #bbd4f6; background: #f5f9ff; }
.browser-ai-step.skipped { color: var(--color-text-secondary); background: #f5f5f5; }
.browser-ai-step .step-name { font-weight: 600; word-break: break-word; }
.browser-ai-step .step-status { font-family: monospace; }
.browser-ai-step .step-message { word-break: break-word; }
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
.label-warn { background: #fff3e0; color: #8a3000; }
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

@media (max-width: 900px) {
  .evidence-summary-grid,
  .evidence-board-controls,
  .project-memory-controls,
  .mastermind-review-grid,
  .mastermind-review-form,
  .mastermind-review-subgrid { grid-template-columns: 1fr; }
}

.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-approve { background: #4caf50; color: #fff; border-color: #4caf50; }
.btn-reject { background: #f44336; color: #fff; border-color: #f44336; }
.btn-warn { background: #ff9800; color: #fff; border-color: #ff9800; }
.btn-archive { background: #607d8b; color: #fff; border-color: #607d8b; }
.btn-sm { padding: 6px 14px; font-size: 13px; }
</style>
