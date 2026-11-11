<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AddSectionModal from '@/components/AddSectionModal.vue'
import AppIcon from '@/components/AppIcon.vue'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import RewriteModal from '@/components/RewriteModal.vue'
import SectionImage from '@/components/SectionImage.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { voices } from '@/data/options'
import { countWords, formatDate, formatDuration, speakingSeconds } from '@/lib/format'
import { useToast } from '@/lib/toast'
import { usePolling } from '@/lib/usePolling'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'

const route = useRoute()
const router = useRouter()
const { push } = useToast()

const id = computed(() => String(route.params.id))
const project = computed(() => projectsStore.getProject(id.value))
const sections = computed(() => projectsStore.getSections(id.value))
const totalWords = computed(() => projectsStore.totalWords(id.value))
const runtime = computed(() => formatDuration(speakingSeconds(totalWords.value, project.value?.wordsPerMinute ?? 150)))

const loading = ref(true)
const loadError = ref<string | null>(null)
const busy = ref(false)

type Tab = 'sections' | 'video' | 'settings'
const tab = ref<Tab>('sections')
const tabs: { value: Tab; label: string }[] = [
  { value: 'sections', label: 'Sections' },
  { value: 'video', label: 'Final video' },
  { value: 'settings', label: 'Settings' },
]

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

// ---- loading + polling (while videos are being built) ----
const working = computed(
  () =>
    project.value?.generationStatus === 'generating' ||
    project.value?.finalVideoStatus === 'processing' ||
    sections.value.some((s) => s.videoStatus === 'processing'),
)

// After an edit the backend needs a moment before it reports "processing": keep looking for a while.
let lookUntil = 0
function watchRender() {
  lookUntil = Date.now() + 20000
  poller.start()
}

const poller = usePolling(async () => {
  await projectsStore.refreshProject(id.value)
  await projectsStore.loadSections(id.value)
  if (!working.value && Date.now() > lookUntil) poller.stop()
}, 3000)

watch(working, (w) => w && poller.start()) // the poller stops itself once nothing is running

async function load() {
  loading.value = true
  loadError.value = null
  try {
    await projectsStore.refreshProject(id.value)
    await projectsStore.loadSections(id.value)
    if (working.value) poller.start()
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// ---- sections ----
const editing = ref<number | null>(null)
const editText = ref('')
const sectionToDelete = ref<number | null>(null)

function startEdit(position: number) {
  editing.value = position
  editText.value = sections.value.find((s) => s.position === position)?.text ?? ''
}
async function saveEdit() {
  const position = editing.value
  if (position === null || !editText.value.trim()) return
  if (await run(() => projectsStore.updateSectionText(id.value, position, editText.value.trim()), `Section ${position} saved`)) {
    editing.value = null
    await projectsStore.refreshProject(id.value).catch(() => {})
    watchRender()
  }
}
async function confirmDeleteSection() {
  const position = sectionToDelete.value
  sectionToDelete.value = null
  if (position !== null) await run(() => projectsStore.removeSection(id.value, position))
}
async function rerender(position: number) {
  await run(() => projectsStore.rerenderSection(id.value, position))
  watchRender()
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
    await projectsStore.refreshProject(id.value)
    push(`Section ${position} rewritten`, 'success')
    changeTarget.value = null
    watchRender()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    rewriting.value = false
  }
}

// ---- add a section at the end ----
const adding = ref(false)
async function addSection(text: string) {
  if (await run(() => projectsStore.addSection(id.value, text), 'Section added')) {
    adding.value = false
    watchRender()
  }
}

// ---- writing stopped half way (error, server restart): carry on where it stopped ----
async function continueWriting() {
  if (await run(() => projectsStore.resumeGeneration(id.value))) watchRender()
}

// ---- videos: nothing is built until you press a button ----
const writing = computed(() => project.value?.generationStatus === 'generating')
const videoStatus = computed(() => project.value?.finalVideoStatus ?? 'none')
const pendingSections = computed(() => sections.value.filter((s) => s.videoStatus !== 'ready').length)
const rendering = computed(() => sections.value.some((s) => s.videoStatus === 'processing'))
const canBuild = computed(() => !busy.value && !writing.value && sections.value.length > 0 && videoStatus.value !== 'processing')

async function buildSections() {
  if (await run(() => projectsStore.buildSectionVideos(id.value))) watchRender()
}
async function buildVideo() {
  if (await run(() => projectsStore.convertIntoVideo(id.value))) {
    tab.value = 'video'
    watchRender()
  }
}
async function removeVideo() {
  await run(() => projectsStore.deleteFinalVideo(id.value), 'Final video deleted')
}

// ---- settings ----
const voice = ref('')
const wpm = ref(150)
watch(
  project,
  (p) => {
    if (!p) return
    voice.value = p.voiceModel
    wpm.value = p.wordsPerMinute
  },
  { immediate: true },
)
const settingsChanged = computed(() => !!project.value && (voice.value !== project.value.voiceModel || wpm.value !== project.value.wordsPerMinute))

async function saveSettings() {
  if (await run(() => projectsStore.updateSettings(id.value, voice.value, wpm.value), 'Settings saved. The section videos are out of date: build them again')) {
    watchRender()
  }
}

const deleting = ref(false)
async function removeProject() {
  deleting.value = false
  if (await run(() => projectsStore.deleteProject(id.value), 'Project deleted')) router.push({ name: 'projects' })
}
</script>

<template>
  <div v-if="project" class="fade-up">
    <RouterLink to="/" class="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white">
      <AppIcon name="chevron-left" :size="16" /> Projects
    </RouterLink>

    <div class="mt-3 flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-2xl font-semibold tracking-tight text-white sm:text-3xl">{{ project.userPrompt }}</h1>
        <p class="mt-1 text-sm text-zinc-400">Created {{ formatDate(project.createdAt) }} · {{ sections.length }} {{ sections.length === 1 ? 'section' : 'sections' }} · {{ totalWords }} words · {{ runtime }}</p>
      </div>
      <div class="flex items-center gap-2">
        <StatusBadge :status="project.generationStatus" />
        <StatusBadge :status="project.finalVideoStatus" />
      </div>
    </div>

    <div v-if="project.generationStatus === 'failed'" class="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-500/25 bg-rose-500/[0.06] px-5 py-4">
      <p class="min-w-0 text-sm text-rose-100">
        <span class="font-semibold">Writing stopped</span> after {{ project.sectionsCompleted }} of {{ project.totalSections || '…' }} sections<template v-if="project.generationError">: {{ project.generationError }}</template>
      </p>
      <button :disabled="busy" class="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500 disabled:opacity-50" @click="continueWriting">
        <AppIcon name="refresh" :size="15" /> Continue writing
      </button>
    </div>
    <div v-else-if="writing" class="mt-6 flex items-center gap-2 rounded-2xl border border-sky-400/20 bg-sky-500/[0.06] px-5 py-4 text-sm text-sky-100" role="status">
      <AppIcon name="loader" :size="15" class="animate-spin" /> Writing the script… {{ project.sectionsCompleted }} of {{ project.totalSections || '…' }} sections. They appear below as they are written.
    </div>

    <div v-if="loading" class="mt-8 space-y-4" aria-busy="true">
      <div v-for="n in 3" :key="n" class="shimmer h-32 rounded-2xl border border-white/8 bg-ink-850/70" />
    </div>
    <div v-else-if="loadError" class="mt-8 rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] px-6 py-10 text-center">
      <p class="text-sm text-rose-200">{{ loadError }}</p>
      <button class="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-500" @click="load"><AppIcon name="refresh" :size="15" /> Try again</button>
    </div>

    <div v-if="!loading && !loadError" class="mt-8 overflow-x-auto"><SegmentedControl v-model="tab" :options="tabs" aria-label="Project sections" /></div>

    <!-- SECTIONS -->
    <template v-if="!loading && !loadError">
    <ul v-if="tab === 'sections'" class="mt-6 space-y-4">
      <li v-for="s in sections" :key="s.position" class="rounded-2xl border border-white/8 bg-ink-850/70 p-4 sm:p-5">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="grid size-7 place-items-center rounded-lg bg-brand-500/15 text-xs font-semibold text-brand-400">{{ s.position }}</span>
            <StatusBadge :status="s.videoStatus" />
          </div>
          <span class="text-xs text-zinc-500">{{ s.wordCount }} words</span>
        </div>
        <p class="mt-3 text-sm leading-relaxed text-zinc-200">{{ s.text }}</p>
        <p v-if="s.videoStatus === 'failed' && s.videoError" class="mt-2 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{{ s.videoError }}</p>
        <div class="mt-4"><SectionImage :project-id="id" :section="s" @changed="watchRender" /></div>

        <video v-if="s.videoUrl && s.videoStatus === 'ready'" :src="s.videoUrl" controls preload="metadata" class="mt-3 aspect-video w-full max-w-sm rounded-lg bg-black ring-1 ring-white/10" />
        <p v-else-if="s.videoStatus === 'processing'" class="mt-3 flex items-center gap-2 text-xs text-sky-300"><AppIcon name="loader" :size="14" class="animate-spin" /> Building this section’s video…</p>
        <p v-else-if="s.videoStatus === 'pending'" class="mt-3 text-xs text-zinc-500">Video not built yet. Add the image, then build it.</p>

        <div class="mt-3 flex flex-wrap gap-1">
          <button class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-300 hover:bg-white/5 hover:text-white" @click="startEdit(s.position)">
            <AppIcon name="pencil" :size="14" /> Edit text
          </button>
          <button class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-300 hover:bg-white/5 hover:text-white" @click="changeTarget = s.position">
            <AppIcon name="wand" :size="14" /> Request changes
          </button>
          <button
            :disabled="busy || writing || s.videoStatus === 'processing'"
            class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-brand-400 hover:bg-brand-500/10 disabled:opacity-40"
            @click="rerender(s.position)"
          >
            <AppIcon name="film" :size="14" /> {{ s.videoStatus === 'ready' ? 'Rebuild video' : s.videoStatus === 'failed' ? 'Retry video' : 'Build video' }}
          </button>
          <button class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-400 hover:bg-rose-500/10 hover:text-rose-300" @click="sectionToDelete = s.position">
            <AppIcon name="trash" :size="14" /> Delete
          </button>
        </div>
      </li>
      <li v-if="!sections.length && writing" class="shimmer h-32 rounded-2xl border border-white/8 bg-ink-850/70" />
      <li v-if="!writing">
        <button
          class="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 py-4 text-sm font-medium text-zinc-400 transition hover:border-brand-400/50 hover:text-white"
          @click="adding = true"
        >
          <AppIcon name="plus" /> Add section
        </button>
      </li>
    </ul>

    <!-- The two build buttons: nothing is rendered until one of them is pressed -->
    <div v-if="tab === 'sections' && sections.length" class="sticky bottom-4 z-10 mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-ink-900/95 px-5 py-4 shadow-xl shadow-black/40 backdrop-blur">
      <p class="text-sm text-zinc-300">
        <span class="font-semibold text-white">{{ sections.length - pendingSections }} of {{ sections.length }}</span> section videos built
        <span v-if="rendering" class="ml-1 text-sky-300">· building…</span>
      </p>
      <div class="flex flex-wrap gap-2">
        <button :disabled="!canBuild || rendering || pendingSections === 0" class="inline-flex items-center gap-2 rounded-xl bg-white/5 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-40" @click="buildSections">
          <AppIcon :name="rendering ? 'loader' : 'film'" :size="16" :class="{ 'animate-spin': rendering }" /> Build section videos
        </button>
        <button :disabled="!canBuild" class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 hover:brightness-110 disabled:opacity-40" @click="buildVideo">
          <AppIcon name="sparkles" :size="16" /> Generate final video
        </button>
      </div>
    </div>

    <!-- FINAL VIDEO -->
    <section v-else-if="tab === 'video'" class="mt-6">
      <div class="overflow-hidden rounded-2xl border border-white/8 bg-ink-850/70">
        <!-- ready: placeholder player -->
        <div v-if="videoStatus === 'ready'">
          <video v-if="project.finalVideoUrl" :src="project.finalVideoUrl" controls preload="metadata" class="aspect-video w-full bg-black" />
          <div class="flex flex-wrap items-center justify-between gap-3 p-4">
            <p class="text-sm text-zinc-300">Final video is up to date.</p>
            <div class="flex gap-2">
              <a v-if="project.finalVideoUrl" :href="project.finalVideoUrl" download target="_blank" rel="noopener" class="inline-flex items-center gap-2 rounded-lg bg-white/5 px-3.5 py-2 text-sm font-medium text-white hover:bg-white/10">
                <AppIcon name="download" :size="16" /> Download
              </a>
              <button :disabled="busy" class="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-400 hover:bg-rose-500/10 hover:text-rose-300 disabled:opacity-50" @click="removeVideo">Delete video</button>
            </div>
          </div>
        </div>

        <!-- other states -->
        <div v-else class="grid place-items-center px-6 py-16 text-center">
          <div
            class="grid size-14 place-items-center rounded-2xl"
            :class="{
              'bg-white/5 text-zinc-400': videoStatus === 'none',
              'bg-sky-500/10 text-sky-300': videoStatus === 'processing',
              'bg-amber-500/10 text-amber-300': videoStatus === 'outdated',
              'bg-rose-500/10 text-rose-300': videoStatus === 'failed',
            }"
          >
            <AppIcon :name="videoStatus === 'processing' ? 'loader' : videoStatus === 'none' ? 'film' : 'alert'" :size="26" :class="{ 'animate-spin': videoStatus === 'processing' }" />
          </div>
          <h2 class="mt-4 text-base font-semibold text-white">
            {{ { none: 'No final video yet', processing: 'Assembling your video…', outdated: 'Final video is out of date', failed: 'Final video failed' }[videoStatus] }}
          </h2>
          <p class="mt-1 max-w-md text-sm text-zinc-400">
            <template v-if="videoStatus === 'none'">Builds any section video that is missing, then joins all {{ sections.length }} into one video.</template>
            <template v-else-if="videoStatus === 'processing'">This takes a moment. You can leave this page.</template>
            <template v-else-if="videoStatus === 'outdated'">Sections or settings changed since the last build. {{ pendingSections }} section video(s) will be rebuilt first.</template>
            <template v-else>{{ project.finalVideoError ?? 'The stitching step failed.' }}</template>
          </p>
          <div v-if="videoStatus !== 'processing'" class="mt-5">
            <button
              class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 hover:brightness-110 disabled:opacity-50"
              :disabled="busy"
              @click="buildVideo"
            >
              <AppIcon :name="videoStatus === 'none' ? 'film' : 'refresh'" />
              {{ videoStatus === 'none' ? 'Generate final video' : videoStatus === 'outdated' ? 'Rebuild final video' : 'Try again' }}
            </button>
          </div>
          <div v-else class="mt-5 h-1.5 w-56 overflow-hidden rounded-full bg-white/5"><div class="shimmer h-full w-full bg-brand-500/50" /></div>
        </div>
      </div>
    </section>

    <!-- SETTINGS -->
    <section v-else class="mt-6 max-w-2xl space-y-6">
      <div class="rounded-2xl border border-white/8 bg-ink-850/70 p-5">
        <h2 class="text-sm font-semibold text-white">Narration</h2>
        <p class="mt-1 text-xs text-zinc-500">Changing the voice or speed makes every section video out of date. You build them again yourself.</p>

        <div class="mt-4 grid gap-5 sm:grid-cols-2">
          <div>
            <label for="voice" class="text-sm font-medium text-zinc-200">Voice</label>
            <select id="voice" v-model="voice" class="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white focus:border-brand-400/60 focus:outline-none">
              <option v-for="v in voices" :key="v.id" :value="v.id">{{ v.label }} — {{ v.accent }}</option>
            </select>
          </div>
          <div>
            <div class="flex items-baseline justify-between">
              <label for="s-wpm" class="text-sm font-medium text-zinc-200">Speaking speed</label>
              <span class="text-sm font-semibold text-white">{{ wpm }} wpm</span>
            </div>
            <input id="s-wpm" v-model.number="wpm" type="range" min="60" max="300" step="10" class="mt-4 w-full accent-brand-500" />
          </div>
        </div>
        <div class="mt-5 flex justify-end">
          <button
            :disabled="!settingsChanged || busy"
            class="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition enabled:hover:bg-brand-500 disabled:opacity-40"
            @click="saveSettings"
          >
            Save changes
          </button>
        </div>
      </div>

      <div class="rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] p-5">
        <h2 class="text-sm font-semibold text-rose-200">Danger zone</h2>
        <p class="mt-1 text-xs text-zinc-400">Deleting removes the project, its sections and all of its files.</p>
        <button class="mt-4 rounded-xl border border-rose-500/30 px-4 py-2.5 text-sm font-medium text-rose-300 hover:bg-rose-500/10" @click="deleting = true">Delete project</button>
      </div>
    </section>

    </template>

    <!-- Edit section -->
    <BaseModal v-if="editing !== null" :title="`Edit section ${editing}`" width-class="max-w-2xl" @close="editing = null">
      <textarea
        v-model="editText"
        rows="8"
        class="w-full resize-y rounded-xl border border-white/10 bg-black/20 p-3 text-[15px] leading-relaxed text-white focus:border-brand-400/60 focus:outline-none"
        aria-label="Section text"
      />
      <p class="mt-2 text-xs text-zinc-500">{{ countWords(editText) }} words · saving makes this section’s video out of date.</p>
      <template #footer>
        <button class="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-300 hover:bg-white/5" @click="editing = null">Cancel</button>
        <button :disabled="!editText.trim() || busy" class="rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white enabled:hover:bg-brand-500 disabled:opacity-40" @click="saveEdit">Save</button>
      </template>
    </BaseModal>

    <RewriteModal v-if="changeTarget !== null" :position="changeTarget" :busy="rewriting" @apply="applyChange" @cancel="changeTarget = null" />
    <AddSectionModal v-if="adding" :position="sections.length + 1" :busy="busy" @add="addSection" @cancel="adding = false" />

    <ConfirmModal
      v-if="sectionToDelete !== null"
      :title="`Delete section ${sectionToDelete}?`"
      message="The section and its video will be removed. Later sections move up by one."
      confirm-label="Delete section"
      danger
      @confirm="confirmDeleteSection"
      @cancel="sectionToDelete = null"
    />
    <ConfirmModal
      v-if="deleting"
      title="Delete this project?"
      message="This can’t be undone."
      confirm-label="Delete project"
      danger
      @confirm="removeProject"
      @cancel="deleting = false"
    />
  </div>
</template>
