<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { usePolling } from '@/lib/usePolling'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'
import type { Project } from '@/types'

const router = useRouter()
const { push } = useToast()

type Filter = 'all' | 'draft' | 'generating' | 'ready' | 'failed'
const filter = ref<Filter>('all')
const query = ref('')
const toDelete = ref<Project | null>(null)
const loading = ref(!projectsStore.state.loaded)
const loadError = ref<string | null>(null)

async function load() {
  loadError.value = null
  try {
    await projectsStore.loadProjects()
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

// keep progress bars fresh while something is generating
const poller = usePolling(async () => {
  await projectsStore.loadProjects()
  if (!projectsStore.projects.value.some((p) => p.generationStatus === 'generating')) poller.stop()
}, 4000)

onMounted(async () => {
  await load()
  if (projectsStore.projects.value.some((p) => p.generationStatus === 'generating')) poller.start()
})

const filters: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Drafts' },
  { value: 'generating', label: 'Generating' },
  { value: 'ready', label: 'Ready' },
  { value: 'failed', label: 'Failed' },
]

const visible = computed(() =>
  projectsStore.projects.value.filter(
    (p) =>
      (filter.value === 'all' || p.generationStatus === filter.value) &&
      p.userPrompt.toLowerCase().includes(query.value.trim().toLowerCase()),
  ),
)

function open(p: Project) {
  if (p.generationStatus === 'draft') router.push({ name: 'review', params: { id: p.id } })
  else if (p.generationStatus === 'generating' || p.finalVideoStatus === 'processing')
    router.push({ name: 'progress', params: { id: p.id } })
  else router.push({ name: 'project', params: { id: p.id } })
}

async function confirmDelete() {
  const target = toDelete.value
  if (!target) return
  toDelete.value = null
  try {
    await projectsStore.deleteProject(target.id)
    push('Project deleted', 'success')
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  }
}
</script>

<template>
  <div class="fade-up">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-white sm:text-3xl">Projects</h1>
        <p class="mt-1 text-sm text-zinc-400">Every script you’ve turned (or are turning) into a video.</p>
      </div>
      <RouterLink
        to="/new"
        class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition hover:brightness-110"
      >
        <AppIcon name="plus" /> New project
      </RouterLink>
    </div>

    <div class="mt-8 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div class="overflow-x-auto"><SegmentedControl v-model="filter" :options="filters" aria-label="Filter projects" /></div>
      <label class="relative block md:w-72">
        <span class="sr-only">Search projects</span>
        <AppIcon name="search" :size="16" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          v-model="query"
          type="search"
          placeholder="Search projects…"
          class="w-full rounded-xl border border-white/10 bg-black/20 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-zinc-500 focus:border-brand-400/60 focus:outline-none"
        />
      </label>
    </div>

    <div v-if="loading" class="mt-10 grid gap-5 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
      <div v-for="n in 3" :key="n" class="shimmer h-72 rounded-2xl border border-white/8 bg-ink-850/70" />
    </div>

    <div v-else-if="loadError" class="mt-10 rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] px-6 py-12 text-center">
      <div class="mx-auto grid size-12 place-items-center rounded-xl bg-rose-500/10 text-rose-300"><AppIcon name="alert" :size="22" /></div>
      <h2 class="mt-4 text-base font-semibold text-white">Couldn’t load projects</h2>
      <p class="mx-auto mt-1 max-w-md text-sm text-zinc-400">{{ loadError }}</p>
      <button class="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500" @click="load">
        <AppIcon name="refresh" /> Try again
      </button>
    </div>

    <div v-else-if="visible.length" class="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
      <ProjectCard v-for="p in visible" :key="p.id" :project="p" @open="open(p)" @remove="toDelete = p" />
    </div>

    <div v-else class="mt-10 rounded-2xl border border-dashed border-white/10 px-6 py-16 text-center">
      <div class="mx-auto grid size-12 place-items-center rounded-xl bg-white/5 text-zinc-400"><AppIcon name="film" :size="22" /></div>
      <h2 class="mt-4 text-base font-semibold text-white">{{ projectsStore.projects.value.length ? 'No projects match' : 'No projects yet' }}</h2>
      <p class="mx-auto mt-1 max-w-sm text-sm text-zinc-400">
        {{ projectsStore.projects.value.length ? 'Try a different filter or search term.' : 'Describe an idea and we’ll draft a story for you to review.' }}
      </p>
      <RouterLink to="/new" class="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500">
        <AppIcon name="plus" /> New project
      </RouterLink>
    </div>

    <ConfirmModal
      v-if="toDelete"
      title="Delete this project?"
      :message="`“${toDelete.userPrompt}”, its sections and its videos will be permanently deleted.`"
      confirm-label="Delete"
      danger
      @confirm="confirmDelete"
      @cancel="toDelete = null"
    />
  </div>
</template>
