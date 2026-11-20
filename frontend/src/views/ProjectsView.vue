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

type Filter = 'all' | 'generating' | 'ready' | 'failed'
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
  { value: 'generating', label: 'Generating' },
  { value: 'ready', label: 'Ready' },
  { value: 'failed', label: 'Failed' },
]

const stats = computed(() => ({
  total: projectsStore.projects.value.length,
  generating: projectsStore.projects.value.filter((p) => p.generationStatus === 'generating').length,
  ready: projectsStore.projects.value.filter((p) => p.generationStatus === 'ready').length,
}))

const visible = computed(() =>
  projectsStore.projects.value.filter(
    (p) =>
      (filter.value === 'all' || p.generationStatus === filter.value) &&
      p.userPrompt.toLowerCase().includes(query.value.trim().toLowerCase()),
  ),
)

function open(p: Project) {
  router.push({ name: 'project', params: { id: p.id } })
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
  <div class="fade-up projects-page">
    <div class="projects-intro">
      <div>
        <p class="eyebrow">YOUR WORKSPACE</p>
        <h1 class="page-title mt-3">Your next video starts here.</h1>
        <p class="page-subtitle mt-2">Keep your ideas, scripts and finished videos organised in one place.</p>
      </div>
      <RouterLink to="/new" class="primary-action">
        <AppIcon name="plus" :size="17" /> Create a video
      </RouterLink>
    </div>

    <div class="project-stats">
      <div class="project-stat">
        <span class="project-stat-icon"><AppIcon name="folder" :size="18" /></span>
        <div><span class="project-stat-label">All projects</span><strong>{{ stats.total }}</strong></div>
      </div>
      <div class="project-stat">
        <span class="project-stat-icon stat-icon-live"><AppIcon name="clock" :size="18" /></span>
        <div><span class="project-stat-label">In progress</span><strong>{{ stats.generating }}</strong></div>
      </div>
      <div class="project-stat">
        <span class="project-stat-icon stat-icon-ready"><AppIcon name="check" :size="18" /></span>
        <div><span class="project-stat-label">Scripts ready</span><strong>{{ stats.ready }}</strong></div>
      </div>
    </div>

    <div class="projects-toolbar">
      <div>
        <h2 class="section-heading">Projects</h2>
        <p class="section-description">Pick up where you left off.</p>
      </div>
      <div class="projects-tools">
        <div class="overflow-x-auto"><SegmentedControl v-model="filter" :options="filters" aria-label="Filter projects" /></div>
        <label class="search-field">
          <span class="sr-only">Search projects</span>
          <AppIcon name="search" :size="16" />
          <input v-model="query" type="search" placeholder="Search projects…" />
        </label>
      </div>
    </div>

    <div v-if="loading" class="project-grid" aria-busy="true">
      <div v-for="n in 3" :key="n" class="shimmer loading-project-card" />
    </div>

    <div v-else-if="loadError" class="empty-state error-state">
      <div class="empty-state-icon error-state-icon"><AppIcon name="alert" :size="23" /></div>
      <h2>We couldn’t load your projects</h2>
      <p>{{ loadError }}</p>
      <button class="primary-action mt-5" @click="load"><AppIcon name="refresh" /> Try again</button>
    </div>

    <div v-else-if="visible.length" class="project-grid">
      <ProjectCard v-for="p in visible" :key="p.id" :project="p" @open="open(p)" @remove="toDelete = p" />
    </div>

    <div v-else class="empty-state">
      <div class="empty-state-icon"><AppIcon name="film" :size="23" /></div>
      <h2>{{ projectsStore.projects.value.length ? 'Nothing found' : 'Your studio is ready' }}</h2>
      <p>{{ projectsStore.projects.value.length ? 'Try another search or switch the status filter.' : 'Start with an idea. We’ll help turn it into a script you can edit and bring to life.' }}</p>
      <RouterLink v-if="!projectsStore.projects.value.length" to="/new" class="primary-action mt-5">
        <AppIcon name="sparkles" /> Create your first video
      </RouterLink>
    </div>

    <ConfirmModal
      v-if="toDelete"
      title="Delete this project?"
      :message="'“' + toDelete.userPrompt + '”, its sections and its videos will be permanently deleted.'"
      confirm-label="Delete"
      danger
      @confirm="confirmDelete"
      @cancel="toDelete = null"
    />
  </div>
</template>
