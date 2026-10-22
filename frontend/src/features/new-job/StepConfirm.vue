<script setup lang="ts">
// 第四站“开始”（确认）：一句话加几行要点，不用表格；warnings 逐条显示，前面加警告图标。
// 点击“开始处理”后按钮进入加载状态，创建成功后跳到任务详情。
import { TriangleAlert } from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { ApiError, jobsApi } from "@/api/endpoints"
import { TASK_TYPE_LABEL } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import { withViewTransition } from "@/design/motion"
import { useJobsStore } from "@/stores/jobs"
import { useModelsStore } from "@/stores/models"
import { useNewJobStore } from "@/stores/newJob"
import { formatNumber, formatSecondsRange, formatWan } from "@/utils/format"
import { notify, notifyError } from "@/utils/toast"

const props = defineProps<{ register: (fn?: () => void) => void }>()

const router = useRouter()
const store = useNewJobStore()
const models = useModelsStore()
const jobs = useJobsStore()

const creating = ref(false)
const createError = ref<string | null>(null)

const model = computed(() => models.byId(store.modelId))
const estimate = computed(() => store.estimate)
const tokens = computed(() => (estimate.value ? estimate.value.est_prompt_tokens + estimate.value.est_completion_tokens : 0))
const estimateMessage = computed(() => {
  const e = store.estimateError
  return e instanceof ApiError ? e.message : e ? "预估没有完成，请返回上一站检查设置" : null
})

async function start() {
  const body = store.buildBody()
  if (!body || creating.value) return
  creating.value = true
  createError.value = null
  try {
    const job = await jobsApi.create(body)
    jobs.upsert(job)
    notify("已开始处理")
    await withViewTransition(async () => {
      await router.push(`/jobs/${job.id}`)
    })
    store.reset()
  } catch (e) {
    if (e instanceof ApiError && (e.code === "NO_ITEMS" || e.code === "MODEL_DISABLED" || e.code === "VALIDATION_ERROR")) {
      createError.value = e.message
    } else {
      notifyError(e)
    }
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  void store.refreshEstimate()
  props.register(() => void start())
})

onBeforeUnmount(() => props.register(undefined))
</script>

<template>
  <div class="ws-confirm">
    <template v-if="store.file && model">
      <p class="ws-confirm__lead">
        用 <strong>{{ model.name }}</strong>（<span class="mono">{{ model.model }}</span>）对
        <strong>{{ store.file.original_name }}</strong> 的
        <span v-if="estimate" class="num">{{ formatNumber(estimate.item_count) }}</span><span v-else>…</span>
        行做{{ TASK_TYPE_LABEL[store.taskType] }}
      </p>

      <div v-if="store.estimating && !estimate" class="ws-confirm__skeleton">
        <Skeleton height="18px" width="50%" />
        <Skeleton height="18px" width="70%" />
      </div>

      <ul v-else-if="estimate" class="ws-confirm__points">
        <li>预计 {{ formatSecondsRange(estimate.est_seconds) }}，约 {{ formatWan(tokens) }} tokens</li>
        <li>
          并发 {{ store.concurrency }}，失败自动重试 {{ store.maxRetries }} 次，
          <template v-if="store.dedupe">相同文本只调用一次（省 {{ formatNumber(estimate.duplicate_count) }} 次）</template>
          <template v-else>相同文本也分别调用</template>
        </li>
        <li v-if="estimate.skipped_empty > 0">有 {{ formatNumber(estimate.skipped_empty) }} 行文本为空，会跳过</li>
        <li v-for="(w, i) in estimate.warnings" :key="i" class="is-warn">
          <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
          <span>{{ w }}</span>
        </li>
      </ul>

      <p v-if="estimateMessage" class="ws-confirm__error" role="alert">{{ estimateMessage }}</p>
      <p v-if="createError" class="ws-confirm__error" role="alert">{{ createError }}</p>
    </template>
    <p v-else class="ws-confirm__error">还没有选好文件或模型，请回到前面的站点。</p>

    <div class="ws-confirm__actions">
      <Button variant="secondary" @click="store.step = 2">上一站</Button>
      <Button
        variant="primary"
        :loading="creating"
        :disabled="!estimate || !!estimateMessage"
        data-testid="start-job"
        @click="start"
      >
        开始处理
      </Button>
    </div>
  </div>
</template>

<style scoped>
.ws-confirm {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: var(--form-max);
}

.ws-confirm__lead {
  margin: 0;
  font-size: var(--text-lg);
  line-height: 1.6;
}

.ws-confirm__lead strong {
  font-weight: 500;
}

.ws-confirm__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-confirm__points {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--ink);
}

.ws-confirm__points li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.ws-confirm__points li.is-warn {
  color: var(--ink);
}

.ws-confirm__points li.is-warn svg {
  flex-shrink: 0;
  color: var(--status-warn);
}

.ws-confirm__error {
  margin: 0;
  color: var(--status-danger);
}

.ws-confirm__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
</style>
