<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AddSectionModal from '@/components/AddSectionModal.vue'
import AppIcon from '@/components/AppIcon.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import RewriteModal from '@/components/RewriteModal.vue'
import SectionEditor from '@/components/SectionEditor.vue'
import { formatDuration, speakingSeconds } from '@/lib/format'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'

const route = useRoute()
const router = useRouter()
const { push } = useToast()

const id = computed(() => String(route.params.id))
const project = computed(() => projectsStore.getProject(id.value))
const sections = computed(() => projectsStore.getSections(id.value))
const totalWords = computed(() => projectsStore.totalWords(id.value))
const duration = computed(() => formatDuration(speakingSeconds(totalWords.value, project.value?.wordsPerMinute ?? 150)))
const canApprove = computed(() => sections.value.length > 0 && !busy.value && savingPosition.value === null)

const loading = ref(true)
const loadError = ref<string | null>(null)
const busy = ref(false)
const savingPosition = ref<number | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    await projectsStore.refreshProject(id.value)
    const p = project.value
    // Not a draft any more (approved, still writing, ...): send the user to the right screen.
    if (p?.generationStatus === 'generating') return router.replace({ name: 'progress', params: { id: id.value } })
    if (p && p.generationStatus !== 'draft') return router.replace({ name: 'project', params: { id: id.value } })
    await projectsStore.loadSections(id.value)
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function run<T>(fn: () => Promise<T>, ok?: string): Promise<boolean> {
  busy.value = true
  try {
    await fn()
    if (ok) push(ok, 'success')
    return true
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
    return false
  } finally {
    busy.value = false
  }
}

async function saveText(position: number, text: string) {
  savingPosition.value = position
  try {
    await projectsStore.updateSectionText(id.value, position, text)
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
    await projectsStore.loadSections(id.value).catch(() => {})
  } finally {
    savingPosition.value = null
  }
}

// ---- request changes (AI rewrite) ----
const changeTarget = ref<number | null>(null)
const rewriting = ref(false)

async function applyChange(instruction: string) {
  const position = changeTarget.value
  if (position === null) return
  rewriting.value = true
  try {
    await projectsStore.rewriteSection(id.value, position, instruction)
    push(`Section ${position} rewritten`, 'success')
    changeTarget.value = null
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    rewriting.value = false
  }
}

// ---- add / delete section ----
const addAt = ref<number | null>(null) // position the new section will take
async function addSection(text: string) {
  if (addAt.value === null) return
  if (await run(() => projectsStore.addSection(id.value, text, addAt.value!), 'Section added')) addAt.value = null
}

const sectionToDelete = ref<number | null>(null)
async function confirmDeleteSection() {
  const position = sectionToDelete.value
  sectionToDelete.value = null
  if (position !== null) await run(() => projectsStore.removeSection(id.value, position))
}

// ---- discard / approve ----
const discarding = ref(false)
async function discard() {
  discarding.value = false
  if (await run(() => projectsStore.deleteProject(id.value), 'Draft discarded')) router.push({ name: 'projects' })
}

async function approve() {
  if (!canApprove.value) return
  if (await run(() => projectsStore.approveDraft(id.value))) router.push({ name: 'progress', params: { id: id.value } })
}
</script>

<template>
  <div v-if="project" class="fade-up pb-28">
    <RouterLink to="/" class="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white">
      <AppIcon name="chevron-left" :size="16" /> Projects
    </RouterLink>

    <div class="mt-3 flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <p class="text-xs font-medium uppercase tracking-wider text-brand-400">Step 2 of 3 · Review story</p>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight text-white sm:text-3xl">{{ project.userPrompt }}</h1>
        <p class="mt-1 text-sm text-zinc-400">Edit anything you like. Videos are only built after you approve.</p>
      </div>
      <dl class="grid grid-cols-3 gap-4 rounded-2xl border border-white/8 bg-ink-850/70 px-5 py-3 text-center">
        <div><dt class="text-[11px] uppercase tracking-wide text-zinc-500">Sections</dt><dd class="text-lg font-semibold text-white">{{ sections.length }}</dd></div>
        <div><dt class="text-[11px] uppercase tracking-wide text-zinc-500">Words</dt><dd class="text-lg font-semibold text-white">{{ totalWords }}</dd></div>
        <div><dt class="text-[11px] uppercase tracking-wide text-zinc-500">Runtime</dt><dd class="text-lg font-semibold text-white">{{ duration }}</dd></div>
      </dl>
    </div>

    <div v-if="loading" class="mt-8 space-y-4" aria-busy="true">
      <div v-for="n in 3" :key="n" class="shimmer h-40 rounded-2xl border border-white/8 bg-ink-850/70" />
    </div>

    <div v-else-if="loadError" class="mt-8 rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] px-6 py-10 text-center">
      <p class="text-sm text-rose-200">{{ loadError }}</p>
      <button class="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-500" @click="load"><AppIcon name="refresh" :size="15" /> Try again</button>
    </div>

    <template v-else>
      <ol class="mt-8 space-y-4">
        <SectionEditor
          v-for="s in sections"
          :key="s.position"
          :project-id="id"
          :section="s"
          :total="sections.length"
          :saving="savingPosition === s.position"
          @save="saveText(s.position, $event)"
          @request-change="changeTarget = s.position"
          @insert-below="addAt = s.position + 1"
          @remove="sectionToDelete = s.position"
        />
      </ol>

      <button
        class="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 py-4 text-sm font-medium text-zinc-400 transition hover:border-brand-400/50 hover:text-white"
        @click="addAt = sections.length + 1"
      >
        <AppIcon name="plus" /> Add section
      </button>
    </template>

    <!-- Sticky action bar -->
    <div class="fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-ink-900/90 backdrop-blur">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-10">
        <button class="rounded-xl px-3.5 py-2 text-sm font-medium text-zinc-400 transition hover:bg-rose-500/10 hover:text-rose-300" :disabled="busy" @click="discarding = true">
          Discard draft
        </button>
        <button
          :disabled="!canApprove || loading"
          class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          @click="approve"
        >
          <AppIcon v-if="busy" name="loader" :size="16" class="animate-spin" />
          Approve &amp; generate <AppIcon v-if="!busy" name="arrow-right" :size="16" />
        </button>
      </div>
    </div>

    <RewriteModal v-if="changeTarget !== null" :position="changeTarget" :busy="rewriting" @apply="applyChange" @cancel="changeTarget = null" />

    <AddSectionModal v-if="addAt !== null" :position="addAt" :busy="busy" @add="addSection" @cancel="addAt = null" />

    <ConfirmModal
      v-if="sectionToDelete !== null"
      :title="`Delete section ${sectionToDelete}?`"
      message="This section will be removed from the story. Later sections move up by one."
      confirm-label="Delete section"
      danger
      @confirm="confirmDeleteSection"
      @cancel="sectionToDelete = null"
    />
    <ConfirmModal
      v-if="discarding"
      title="Discard this draft?"
      message="The story and your edits will be permanently deleted."
      confirm-label="Discard"
      danger
      @confirm="discard"
      @cancel="discarding = false"
    />
  </div>
</template>
