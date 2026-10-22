<script setup lang="ts">
// 首页（06 第 6.1 节）：主角是“始发站”；下面是正在运行、最近任务两栏；底部是模型条。
import { CircleCheck, Ban, Pause, Play } from "@lucide/vue"
import { computed, onMounted } from "vue"
import { useRouter } from "vue-router"
import { jobsApi } from "@/api/endpoints"
import type { JobSummary, TaskType } from "@/api/types"
import { TASK_TYPE_LABEL } from "@/api/types"
import Button from "@/components/base/Button.vue"
import IconButton from "@/components/base/IconButton.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import LineProgress from "@/components/metro/LineProgress.vue"
import { usePasteToStart } from "@/composables/useFileIntake"
import { useJobsStore } from "@/stores/jobs"
import { isDemoModel, useModelsStore } from "@/stores/models"
import { useNewJobStore } from "@/stores/newJob"
import { formatDurationMs, formatEta, formatRelativeDate } from "@/utils/format"
import { notify, notifyError } from "@/utils/toast"
import StartStation from "./StartStation.vue"

const router = useRouter()
const jobs = useJobsStore()
const models = useModelsStore()
const newJob = useNewJobStore()

usePasteToStart()

onMounted(() => {
  if (!jobs.loaded) void jobs.load().catch(() => undefined)
})

function openPaste() {
  newJob.reset()
  void router.push({ path: "/new", query: { paste: "1" } })
}

async function togglePause(job: JobSummary) {
  const pausing = job.status === "running" || job.status === "queued"
  const previous = job
  jobs.upsert({
    ...job,
    status: pausing ? "paused" : "running",
    status_reason: pausing ? "已手动暂停" : "",
    status_reason_code: pausing ? "user_pause" : null,
  })
  try {
    const next = pausing ? await jobsApi.pause(job.id) : await jobsApi.resume(job.id)
    jobs.upsert(next)
    notify(pausing ? "已暂停" : "已继续")
  } catch (e) {
    jobs.upsert(previous)
    notifyError(e)
  }
}

const defaults = computed(() =>
  (["classify", "summarize"] as TaskType[]).map((task) => ({ task, model: models.defaultFor(task) })),
)

const usingDemo = computed(() => defaults.value.every((d) => !d.model || isDemoModel(d.model)))
</script>

<template>
  <div class="ws-home">
    <StartStation @paste="openPaste" />

    <div class="ws-home__columns">
      <section class="ws-home__panel" aria-labelledby="home-running">
        <h2 id="home-running" class="ws-home__heading">正在运行</h2>
        <div v-if="!jobs.loaded && jobs.loading" class="ws-home__skeleton">
          <Skeleton height="18px" width="80%" />
          <Skeleton height="18px" width="60%" />
        </div>
        <p v-else-if="jobs.active.length === 0" class="ws-home__muted">没有正在运行的任务</p>
        <ul v-else class="ws-home__list">
          <li v-for="job in jobs.active" :key="job.id" class="ws-home__run">
            <RouterLink :to="`/jobs/${job.id}`" class="ws-home__run-name">{{ job.name }}</RouterLink>
            <div class="ws-home__run-line">
              <LineProgress :progress="job.progress" :status="job.status" :width="220" />
              <span class="ws-home__eta">
                <template v-if="job.status === 'paused'">已暂停</template>
                <template v-else-if="job.progress.eta_seconds !== null">{{ formatEta(job.progress.eta_seconds) }}</template>
              </span>
              <IconButton
                :label="job.status === 'paused' ? '继续' : '暂停'"
                size="sm"
                @click="togglePause(job)"
              >
                <Play v-if="job.status === 'paused'" :size="16" :stroke-width="1.75" />
                <Pause v-else :size="16" :stroke-width="1.75" />
              </IconButton>
            </div>
          </li>
        </ul>
      </section>

      <section class="ws-home__panel" aria-labelledby="home-recent">
        <h2 id="home-recent" class="ws-home__heading">最近任务</h2>
        <div v-if="!jobs.loaded && jobs.loading" class="ws-home__skeleton">
          <Skeleton height="18px" width="70%" />
          <Skeleton height="18px" width="50%" />
        </div>
        <p v-else-if="jobs.recentFinished.length === 0" class="ws-home__muted">还没有已结束的任务</p>
        <ul v-else class="ws-home__list">
          <li v-for="job in jobs.recentFinished" :key="job.id">
            <RouterLink :to="`/jobs/${job.id}`" class="ws-home__recent">
              <CircleCheck v-if="job.status === 'completed'" class="is-ok" :size="16" :stroke-width="2" aria-hidden="true" />
              <Ban v-else class="is-muted" :size="16" :stroke-width="2" aria-hidden="true" />
              <span class="sr-only">{{ job.status === "completed" ? "已完成" : "已取消" }}</span>
              <span class="ws-home__recent-name">{{ job.name }}</span>
              <span class="ws-home__recent-time">{{ formatRelativeDate(job.finished_at ?? job.updated_at) }}</span>
            </RouterLink>
          </li>
        </ul>
      </section>
    </div>

    <footer class="ws-home__models">
      <template v-if="usingDemo">
        <span class="ws-home__demo">现在用的是演示模型，结果是模拟的</span>
        <Button variant="primary" size="sm" @click="router.push(models.connectRealModelRoute)">接入真实模型</Button>
      </template>
      <template v-else>
        <span v-for="d in defaults" :key="d.task" class="ws-home__model">
          <span class="ws-home__model-task">{{ TASK_TYPE_LABEL[d.task] }}默认</span>
          <span class="ws-home__model-name">{{ d.model?.name ?? "未设置" }}</span>
          <span v-if="d.model?.avg_latency_ms" class="ws-home__model-latency">{{ formatDurationMs(d.model.avg_latency_ms) }}</span>
        </span>
        <Button variant="text" size="sm" @click="router.push('/models')">管理</Button>
      </template>
    </footer>
  </div>
</template>

<style scoped>
.ws-home {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  max-width: 1280px;
  padding-top: var(--space-2);
}

.ws-home__columns {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: var(--space-10);
}

.ws-home__heading {
  margin: 0 0 var(--space-3);
  font-size: var(--text-base);
  font-weight: 500;
}

.ws-home__muted {
  margin: 0;
  color: var(--ink-2);
}

.ws-home__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-home__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-home__run {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border);
}

.ws-home__run:last-child {
  border-bottom: 0;
}

.ws-home__run-name {
  overflow: hidden;
  color: var(--ink);
  font-weight: 500;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-home__run-name:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.ws-home__run-line {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.ws-home__eta {
  min-width: 72px;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-home__recent {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  min-height: 32px;
  padding: 0 var(--space-2);
  margin: 0 calc(-1 * var(--space-2));
  border-radius: var(--radius-control);
  color: var(--ink);
  text-decoration: none;
}

.ws-home__recent:hover {
  background: var(--surface-2);
}

.ws-home__recent .is-ok {
  color: var(--status-ok);
}

.ws-home__recent .is-muted {
  color: var(--status-muted);
}

.ws-home__recent-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-home__recent-time {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-home__models {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3) var(--space-8);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-home__demo {
  color: var(--ink);
}

.ws-home__model {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-2);
}

.ws-home__model-name {
  color: var(--ink);
  font-weight: 500;
}

.ws-home__model-latency {
  color: var(--ink-2);
}
</style>
