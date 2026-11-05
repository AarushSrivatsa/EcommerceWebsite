<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useToast } from '@/lib/toast'
import { usePolling } from '@/lib/usePolling'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'
import type { GenerationStage } from '@/types'

const route = useRoute()
const router = useRouter()
const { push } = useToast()

const id = computed(() => String(route.params.id))
const project = computed(() => projectsStore.getProject(id.value))
const sections = computed(() => projectsStore.getSections(id.value))
const retrying = ref(false)
const loadError = ref<string | null>(null)

// ---- derive the stages from real backend state ----
const stages = computed<GenerationStage[]>(() => {
  const p = project.value
  if (!p) return []
  const list = sections.value
  const total = list.length
  const ready = list.filter((s) => s.videoStatus === 'ready').length
  const failedSections = list.filter((s) => s.videoStatus === 'failed')
  const scriptDone = p.generationStatus === 'ready' || p.generationStatus === 'draft'

  const script: GenerationStage = {
    key: 'script',
    label: 'Writing the script',
    description: 'Splitting the story into sections',
    state: p.generationStatus === 'generating' ? 'active' : p.generationStatus === 'failed' ? 'failed' : 'done',
    detail:
      p.generationStatus === 'failed'
        ? (p.generationError ?? 'Writing failed')
        : `${scriptDone ? total || p.totalSections : p.sectionsCompleted} of ${p.totalSections || '…'} sections written`,
  }

  const videos: GenerationStage = {
    key: 'videos',
    label: 'Rendering section videos',
    description: 'Narration and visuals for every section',
    state: !scriptDone ? 'pending' : failedSections.length ? 'failed' : total > 0 && ready === total ? 'done' : 'active',
    detail: !scriptDone
      ? undefined
      : failedSections.length
        ? `Section ${failedSections[0].position} failed${failedSections[0].videoError ? `: ${failedSections[0].videoError}` : ''}`
        : `${ready} of ${total} section videos ready`,
  }

  const finalVideo: GenerationStage = {
    key: 'final',
    label: 'Assembling final video',
    description: 'Joining all sections together',
    state:
      p.finalVideoStatus === 'ready' ? 'done' : p.finalVideoStatus === 'processing' ? 'active' : p.finalVideoStatus === 'failed' ? 'failed' : 'pending',
    detail: p.finalVideoStatus === 'failed' ? (p.finalVideoError ?? 'Final video failed') : undefined,
  }

  return [script, videos, finalVideo]
})

const failedStage = computed(() => stages.value.find((s) => s.state === 'failed'))
const isComplete = computed(() => stages.value.length > 0 && stages.value.every((s) => s.state === 'done'))
const overall = computed<'running' | 'failed' | 'complete'>(() => (failedStage.value ? 'failed' : isComplete.value ? 'complete' : 'running'))

const percent = computed(() => {
  const list = stages.value
  if (!list.length) return 0
  const score = list.reduce((sum, s) => sum + (s.state === 'done' ? 1 : 0), 0)
  // give the active stage a little credit so the bar moves
  const active = list.find((s) => s.state === 'active')
  return Math.min(100, Math.round(((score + (active ? 0.4 : 0)) / list.length) * 100))
})

// ---- polling ----
async function refresh() {
  await projectsStore.refreshProject(id.value)
  await projectsStore.loadSections(id.value)
}

const poller = usePolling(async () => {
  await refresh()
  if (overall.value !== 'running') poller.stop()
}, 2000)

onMounted(async () => {
  try {
    await refresh()
  } catch (e) {
    loadError.value = errorMessage(e)
    return
  }
  // A draft that hasn't been approved belongs on the review screen.
  if (project.value?.generationStatus === 'draft') return router.replace({ name: 'review', params: { id: id.value } })
  if (overall.value === 'running') poller.start()
})

async function retry() {
  retrying.value = true
  try {
    if (project.value?.generationStatus === 'failed') await projectsStore.resumeGeneration(id.value)
    else await projectsStore.convertIntoVideo(id.value)
    await refresh()
    poller.start()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div v-if="project" class="fade-up mx-auto max-w-4xl">
    <RouterLink to="/" class="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white">
      <AppIcon name="chevron-left" :size="16" /> Projects
    </RouterLink>

    <div class="mt-3 flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <p class="text-xs font-medium uppercase tracking-wider text-brand-400">Step 3 of 3 · Generating</p>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight text-white sm:text-3xl">{{ project.userPrompt }}</h1>
      </div>
      <StatusBadge :status="overall === 'running' ? 'generating' : overall === 'failed' ? 'failed' : 'ready'" />
    </div>

    <p v-if="loadError" class="mt-6 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{{ loadError }}</p>

    <!-- Overall progress -->
    <section class="mt-6 rounded-2xl border border-white/8 bg-ink-850/70 p-5" role="status">
      <div class="flex items-baseline justify-between">
        <h2 class="text-sm font-semibold text-white">
          {{ overall === 'complete' ? 'Your video is ready' : overall === 'failed' ? 'Something went wrong' : 'Building your video' }}
        </h2>
        <span class="text-sm font-semibold text-white">{{ percent }}%</span>
      </div>
      <div class="mt-3 h-2 overflow-hidden rounded-full bg-white/5">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="overall === 'failed' ? 'bg-rose-500' : 'bg-gradient-to-r from-brand-500 to-accent-500'"
          :style="{ width: `${percent}%` }"
        />
      </div>
      <p v-if="failedStage" class="mt-3 flex items-start gap-2 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
        <AppIcon name="alert" :size="16" class="mt-0.5" /> {{ failedStage.detail }}
      </p>
    </section>

    <div class="mt-6 grid gap-6 lg:grid-cols-5">
      <!-- Stages -->
      <section class="rounded-2xl border border-white/8 bg-ink-850/70 p-5 lg:col-span-3">
        <h2 class="text-sm font-semibold text-white">Stages</h2>
        <ol class="mt-4 space-y-1">
          <li v-for="(s, i) in stages" :key="s.key" class="relative flex gap-3.5 pb-5 last:pb-0">
            <span v-if="i < stages.length - 1" class="absolute left-[13px] top-8 h-[calc(100%-2rem)] w-px" :class="s.state === 'done' ? 'bg-emerald-500/40' : 'bg-white/10'" />
            <span
              class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full ring-1 ring-inset"
              :class="{
                'bg-emerald-500/15 text-emerald-300 ring-emerald-400/30': s.state === 'done',
                'bg-brand-500/15 text-brand-400 ring-brand-400/40': s.state === 'active',
                'bg-rose-500/15 text-rose-300 ring-rose-400/40': s.state === 'failed',
                'bg-white/5 text-zinc-500 ring-white/10': s.state === 'pending',
              }"
            >
              <AppIcon v-if="s.state === 'done'" name="check" :size="14" />
              <AppIcon v-else-if="s.state === 'active'" name="loader" :size="14" class="animate-spin" />
              <AppIcon v-else-if="s.state === 'failed'" name="x" :size="14" />
              <span v-else class="size-1.5 rounded-full bg-current" />
            </span>
            <div class="min-w-0 pt-0.5">
              <p class="text-sm font-medium" :class="s.state === 'pending' ? 'text-zinc-500' : 'text-white'">{{ s.label }}</p>
              <p class="text-xs text-zinc-500">{{ s.detail ?? s.description }}</p>
            </div>
          </li>
        </ol>
      </section>

      <!-- Per-section status -->
      <section class="rounded-2xl border border-white/8 bg-ink-850/70 p-5 lg:col-span-2">
        <h2 class="text-sm font-semibold text-white">Sections</h2>
        <p v-if="!sections.length" class="mt-4 text-sm text-zinc-500">Sections appear as they are written.</p>
        <ul v-else class="mt-4 max-h-96 space-y-2 overflow-y-auto">
          <li v-for="s in sections" :key="s.position" class="flex items-center justify-between gap-3 rounded-lg bg-black/20 px-3 py-2">
            <span class="flex min-w-0 items-center gap-2.5 text-sm text-zinc-300">
              <span class="text-xs text-zinc-500">{{ s.position }}</span>
              <span class="truncate">{{ s.text.slice(0, 28) || 'Untitled section' }}…</span>
            </span>
            <StatusBadge :status="s.videoStatus" class="shrink-0" />
          </li>
        </ul>
      </section>
    </div>

    <!-- Actions -->
    <div class="mt-8 flex flex-wrap items-center justify-end gap-3">
      <button
        v-if="overall === 'failed'"
        :disabled="retrying"
        class="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-500 disabled:opacity-50"
        @click="retry"
      >
        <AppIcon name="refresh" :class="{ 'animate-spin': retrying }" /> Retry
      </button>
      <RouterLink
        v-if="overall === 'complete'"
        :to="{ name: 'project', params: { id } }"
        class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 hover:brightness-110"
      >
        Open project <AppIcon name="arrow-right" :size="16" />
      </RouterLink>
      <RouterLink v-if="overall === 'running'" to="/" class="rounded-xl px-4 py-2.5 text-sm font-medium text-zinc-300 hover:bg-white/5">
        Continue in background
      </RouterLink>
    </div>
  </div>
</template>
