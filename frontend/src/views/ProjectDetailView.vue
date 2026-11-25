<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AddSectionModal from '@/components/AddSectionModal.vue'
import AppIcon from '@/components/AppIcon.vue'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import RewriteModal from '@/components/RewriteModal.vue'
import SectionImage from '@/components/SectionImage.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import YoutubeUploadPanel from '@/components/YoutubeUploadPanel.vue'
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
  poller.stop()
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
watch(id, load, { immediate: true })

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
const canBuild = computed(() => !busy.value && !writing.value && !rendering.value && sections.value.length > 0 && videoStatus.value !== 'processing')
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
const similarity = ref(88)
const renderMode = ref<'image' | 'cinematic'>('cinematic')
const renderModeOptions: { value: 'image' | 'cinematic'; label: string }[] = [
  { value: 'image', label: 'Image' },
  { value: 'cinematic', label: 'Cinematic Skill' },
]
watch(
  () => project.value?.id,
  () => {
    const p = project.value
    if (!p) return
    voice.value = p.voiceModel
    wpm.value = p.wordsPerMinute
    similarity.value = Math.round(p.similarityThreshold * 100)
    renderMode.value = p.renderMode
  },
  { immediate: true },
)
const mediaSettingsChanged = computed(() => !!project.value && (
  voice.value !== project.value.voiceModel ||
  wpm.value !== project.value.wordsPerMinute ||
  renderMode.value !== project.value.renderMode
))
const settingsChanged = computed(() => !!project.value && (
  mediaSettingsChanged.value || similarity.value !== Math.round(project.value.similarityThreshold * 100)
))

async function saveSettings() {
  const needsRerender = mediaSettingsChanged.value
  const message = needsRerender
    ? 'Video settings saved. Press Generate video to rebuild the scenes.'
    : 'Similarity limit saved. It applies to future sections and AI rewrites.'
  if (await run(() => projectsStore.updateSettings(id.value, voice.value, wpm.value, similarity.value / 100, renderMode.value), message)) {
    if (needsRerender) watchRender()
  }
}

const deleting = ref(false)
async function removeProject() {
  deleting.value = false
  if (await run(() => projectsStore.deleteProject(id.value), 'Project deleted')) router.push({ name: 'projects' })
}
</script>

<template>
  <div v-if="project" class="fade-up project-page">
    <RouterLink to="/" class="back-link"><AppIcon name="chevron-left" :size="15" /> All projects</RouterLink>

    <header class="project-hero">
      <div class="project-hero-copy">
        <p class="eyebrow">PROJECT WORKSPACE</p>
        <h1 class="project-title">{{ project.userPrompt }}</h1>
        <p class="project-meta-line">
          <span>{{ formatDate(project.createdAt) }}</span>
          <span>{{ sections.length }} {{ sections.length === 1 ? 'section' : 'sections' }}</span>
          <span>{{ totalWords.toLocaleString() }} words</span>
          <span>{{ runtime }} estimated</span>
        </p>
      </div>
      <div class="project-statuses">
        <StatusBadge :status="project.generationStatus" />
        <StatusBadge :status="project.finalVideoStatus" />
      </div>
    </header>

    <div v-if="project.generationStatus === 'failed'" class="project-alert project-alert-danger">
      <div><strong>Script generation paused</strong><p>Completed {{ project.sectionsCompleted }} of {{ project.totalSections || 'the planned' }} sections.<template v-if="project.generationError"> {{ project.generationError }}</template></p></div>
      <button :disabled="busy" class="secondary-action" @click="continueWriting"><AppIcon name="refresh" :size="15" /> Continue writing</button>
    </div>
    <div v-else-if="writing" class="project-alert project-alert-info" role="status">
      <AppIcon name="loader" :size="17" class="animate-spin" />
      <div>
        <strong>{{ project.researchStatus === 'pending' ? 'Researching your topic' : 'Writing your script' }}</strong>
        <p v-if="project.researchStatus === 'pending'">Finding useful sources and planning the sections before drafting begins.</p>
        <p v-else>{{ project.sectionsCompleted }} of {{ project.totalSections || 'the planned' }} sections completed. New sections will appear below.</p>
      </div>
    </div>

    <div v-if="project.researchStatus === 'unavailable' && project.researchError" class="project-alert project-alert-info">
      <AppIcon name="info" :size="17" />
      <div><strong>External research could not be loaded</strong><p>{{ project.researchError }}</p></div>
    </div>

    <div v-if="loading" class="project-loading" aria-busy="true">
      <div v-for="n in 3" :key="n" class="shimmer project-loading-card" />
    </div>
    <div v-else-if="loadError" class="project-error">
      <AppIcon name="alert" :size="22" /><strong>Couldn’t load this project</strong><p>{{ loadError }}</p>
      <button class="primary-action mt-4" @click="load"><AppIcon name="refresh" :size="15" /> Try again</button>
    </div>

    <template v-if="!loading && !loadError">
      <div class="project-tabs"><SegmentedControl v-model="tab" :options="tabs" aria-label="Project sections" /></div>

      <section v-if="tab === 'sections'" class="project-section-page">
        <div class="project-content-heading">
          <div><h2>Script & scenes</h2><p>{{ project.renderMode === 'cinematic' ? 'Cinematic Skill finds visuals and creates the film automatically.' : 'Upload one image for each section, then generate the film.' }}</p></div>
          <button v-if="!writing" class="secondary-action" @click="adding = true"><AppIcon name="plus" :size="15" /> Add section</button>
        </div>

        <ul class="project-sections">
          <li v-for="s in sections" :key="s.position" class="section-card">
            <div class="section-card-top">
              <div class="section-heading-left">
                <span class="section-number">{{ String(s.position).padStart(2, '0') }}</span>
                <div><strong>Section {{ s.position }}</strong><StatusBadge :status="s.videoStatus" /></div>
              </div>
              <span class="section-word-count">{{ s.wordCount }} words</span>
            </div>
            <p class="section-copy">{{ s.text }}</p>

            <div class="section-quality-row">
              <span v-if="s.similarityScore !== null" :class="{ 'section-quality-warning': s.similarityThreshold !== null && s.similarityScore >= s.similarityThreshold }">
                Similarity <strong>{{ Math.round(s.similarityScore * 100) }}%</strong>
              </span>
              <span v-if="s.similarityThreshold !== null">Limit <strong>{{ Math.round(s.similarityThreshold * 100) }}%</strong></span>
              <span v-if="s.groundingScore !== null">Evidence check <strong>{{ Math.round(s.groundingScore * 100) }}%</strong></span>
              <span v-if="s.sources.length">Sources <strong>{{ s.sources.length }}</strong></span>
            </div>

            <details v-if="s.renderMode === 'cinematic' && s.visualPlan.length" class="visual-beats">
              <summary>Visual direction · {{ s.visualPlan.length }} beats</summary>
              <p class="cinematic-free-note">Cinematic Skill automatically finds relevant, reusable photos for each narration beat and builds the complete film. Nothing needs to be uploaded.</p>
              <ol>
                <li v-for="(beat, beatIndex) in s.visualPlan" :key="beatIndex">
                  <div class="visual-beat-heading">
                    <strong>Beat {{ String(beatIndex + 1).padStart(2, '0') }}</strong>
                    <small>{{ beat.camera }}</small>
                  </div>
                  <p>{{ beat.visual }}</p>
                  <small v-if="beat.onScreenText">On-screen text: {{ beat.onScreenText }}</small>
                  <img v-if="beat.imageUrl && beat.imageOrigin === 'commons'" :src="beat.imageUrl" :alt="`Visual for section ${s.position}, beat ${beatIndex + 1}`" class="visual-beat-image" loading="lazy" />
                  <div v-if="beat.imageOrigin === 'commons' && beat.imageTitle" class="visual-beat-credit">
                    <small>ARCHIVE IMAGE</small>
                    <a v-if="beat.imageSourceUrl" :href="beat.imageSourceUrl" target="_blank" rel="noopener noreferrer">{{ beat.imageTitle }}</a>
                    <strong v-else>{{ beat.imageTitle }}</strong>
                    <span v-if="beat.imageCredit">Credit: {{ beat.imageCredit }}</span>
                    <span v-if="beat.imageLicense">
                      Licence:
                      <a v-if="beat.imageLicenseUrl" :href="beat.imageLicenseUrl" target="_blank" rel="noopener noreferrer">{{ beat.imageLicense }}</a>
                      <strong v-else>{{ beat.imageLicense }}</strong>
                    </span>
                  </div>
                </li>
              </ol>
            </details>

            <details v-if="s.sources.length" class="section-sources">
              <summary>Research sources · {{ s.sources.length }}</summary>
              <a
                v-for="source in s.sources"
                :key="source.url"
                :href="source.url"
                target="_blank"
                rel="noopener noreferrer"
              >{{ source.title }}</a>
            </details>

            <details v-if="s.groundingFeedback" class="grounding-notes">
              <summary>Evidence review notes</summary>
              <p>{{ s.groundingFeedback }}</p>
              <small>The evidence check is an AI-assisted assessment, not a statistical guarantee of factual accuracy.</small>
            </details>
            <p v-if="s.videoStatus === 'failed' && s.videoError" class="section-error">{{ s.videoError }}</p>
            <SectionImage v-if="project.renderMode === 'image'" :project-id="id" :section="s" @changed="watchRender" />

            <video
              v-if="s.videoUrl && s.videoStatus === 'ready'"
              :src="s.videoUrl"
              controls
              playsinline
              preload="metadata"
              class="section-video-player"
            />
            <div v-if="s.videoStatus === 'ready' && (s.creditsUrl || s.subtitleUrl)" class="section-media-downloads">
              <a v-if="s.creditsUrl" :href="s.creditsUrl" target="_blank" rel="noopener noreferrer" download>Image credits and licences</a>
              <a v-if="s.subtitleUrl" :href="s.subtitleUrl" target="_blank" rel="noopener noreferrer" download>Download subtitles (.srt)</a>
            </div>

            <p v-else-if="s.videoStatus === 'processing'" class="section-video-note"><AppIcon name="loader" :size="14" class="animate-spin" /> {{ s.renderMode === 'cinematic' ? 'Rendering with Cinematic Skill…' : 'Building the single-image scene…' }}</p>
            <p v-else-if="s.videoStatus === 'pending'" class="section-video-note">{{ s.renderMode === 'cinematic' ? 'This Cinematic Skill scene has not been rendered yet.' : 'This single-image scene has not been rendered yet.' }}</p>

            <div class="section-actions">
              <button @click="startEdit(s.position)"><AppIcon name="pencil" :size="14" /> Edit script</button>
              <button @click="changeTarget = s.position"><AppIcon name="wand" :size="14" /> Ask AI to revise</button>
              <button class="section-delete-action" @click="sectionToDelete = s.position"><AppIcon name="trash" :size="14" /> Delete</button>
            </div>
          </li>

          <li v-if="!sections.length && writing" class="shimmer project-loading-card" />
          <li v-if="!writing && !sections.length" class="project-empty-sections">
            <strong>No sections yet</strong><p>Your script will appear here as it is written.</p>
          </li>
        </ul>

        <div v-if="sections.length" class="build-panel">
          <div class="build-panel-copy">
            <span class="build-panel-icon"><AppIcon name="film" :size="18" /></span>
            <div><strong>Generate your video</strong>
              <p>{{ project.renderMode === 'cinematic' ? 'Automatically finds images, renders every section and joins everything into one film.' : 'Uses each section’s image, renders every scene and joins everything into one film.' }}</p>
            </div>
          </div>
          <div class="build-panel-actions">
            <button :disabled="!canBuild" class="primary-action" @click="buildVideo">
              <AppIcon :name="videoStatus === 'processing' ? 'loader' : 'sparkles'" :size="15" :class="{ 'animate-spin': videoStatus === 'processing' }" />
              {{ videoStatus === 'ready' ? 'Regenerate video' : 'Generate video' }}
            </button>
          </div>
        </div>
      </section>

      <section v-else-if="tab === 'video'" class="final-video-page">
        <div v-if="videoStatus === 'ready' && project.finalVideoUrl" class="final-video-card">
          <div class="final-video-topline"><div><p class="eyebrow">YOUR FINISHED VIDEO</p><h2>Ready to watch</h2></div><StatusBadge status="ready" /></div>
          <video :src="project.finalVideoUrl" controls playsinline preload="metadata" class="final-video-player" />
          <div class="final-video-actions">
            <p>Your final video is ready. Watch it here or save a copy.</p>
            <div>
              <a :href="project.finalVideoUrl" download target="_blank" rel="noopener" class="secondary-action"><AppIcon name="download" :size="15" /> Download video</a>
              <button :disabled="busy" class="text-danger-action" @click="removeVideo">Delete video</button>
            </div>
          </div>
        </div>

        <div v-else class="video-empty-state">
          <span class="video-empty-icon"><AppIcon :name="videoStatus === 'processing' ? 'loader' : videoStatus === 'failed' ? 'alert' : 'film'" :size="27" :class="{ 'animate-spin': videoStatus === 'processing' }" /></span>
          <p class="eyebrow">FINAL VIDEO</p>
          <h2>{{ { none: 'Your video is not built yet', processing: 'Putting it all together', outdated: 'Your video needs an update', failed: 'The final video could not be built', ready: 'The video link is unavailable' }[videoStatus] }}</h2>
          <p>
            <template v-if="videoStatus === 'none'">Press Generate video. The app will render every section and join them automatically.</template>
            <template v-else-if="videoStatus === 'processing'">Your sections are being rendered and joined into one film.</template>
            <template v-else-if="videoStatus === 'outdated'">The script or settings changed. {{ pendingSections }} scene(s) will be rebuilt.</template>
            <template v-else>{{ project.finalVideoError ?? 'The video assembly step failed.' }}</template>
          </p>
          <button v-if="videoStatus !== 'processing'" :disabled="!canBuild" class="primary-action mt-5" @click="buildVideo">
            <AppIcon name="refresh" :size="15" /> {{ videoStatus === 'none' ? 'Generate video' : videoStatus === 'outdated' ? 'Regenerate video' : 'Try again' }}
          </button>
        </div>
        <YoutubeUploadPanel v-if="videoStatus === 'ready'" :project-id="id" />
      </section>

      <section v-else class="project-settings-page">
        <div class="settings-card">
          <div class="project-content-heading"><div><h2>Video settings</h2><p>Choose one visual mode for the entire project and set the narrator.</p></div></div>
          <div class="settings-fields">
            <div>
              <span class="field-label">Visual mode</span>
              <SegmentedControl v-model="renderMode" :options="renderModeOptions" aria-label="Visual mode" />
              <p class="field-hint">{{ renderMode === 'cinematic' ? 'Cinematic Skill automatically finds relevant images. No uploads required.' : 'Upload one still image for each section.' }}</p>
            </div>
            <div><label for="voice" class="field-label">Narrator voice</label>
              <select id="voice" v-model="voice">
                <option v-for="v in voices" :key="v.id" :value="v.id">{{ v.label }} — {{ v.accent }}</option>
              </select>
            </div>
            <div><div class="settings-range-heading"><label for="s-wpm" class="field-label">Speaking speed</label><strong>{{ wpm }} words per minute</strong></div>
              <input id="s-wpm" v-model.number="wpm" type="range" min="60" max="300" step="10" />
            </div>

            <div class="similarity-setting">
              <div class="settings-range-heading">
                <label for="s-similarity" class="field-label">Section similarity limit</label>
                <strong>{{ similarity }}%</strong>
              </div>
              <input id="s-similarity" v-model.number="similarity" type="range" min="60" max="100" step="1" />
              <div class="range-ends"><span>Stricter</span><span>More permissive</span></div>
              <p class="field-hint">This is semantic embedding similarity, not an exact text-match score. A section at or above the limit is retried up to three times. The score and limit used remain visible on each section. Existing videos are not affected.</p>
            </div>
          </div>
          <div class="settings-footer"><span>Current runtime: {{ runtime }}</span><button :disabled="!settingsChanged || busy || writing" class="primary-action" @click="saveSettings">Save settings</button></div>
        </div>
        <div class="danger-zone">
          <div><strong>Delete this project</strong><p>This permanently removes the project, its sections and generated files.</p></div>
          <button class="text-danger-action" @click="deleting = true">Delete project</button>
        </div>
      </section>
    </template>

    <BaseModal v-if="editing !== null" :title="'Edit section ' + editing" width-class="max-w-2xl" @close="editing = null">
      <textarea v-model="editText" rows="8" class="modal-textarea" aria-label="Section text" />
      <p class="modal-hint">{{ countWords(editText) }} words · Saving makes this scene video out of date.</p>
      <template #footer>
        <button class="secondary-action" @click="editing = null">Cancel</button>
        <button :disabled="!editText.trim() || busy" class="primary-action" @click="saveEdit">Save script</button>
      </template>
    </BaseModal>

    <RewriteModal v-if="changeTarget !== null" :position="changeTarget" :busy="rewriting" @apply="applyChange" @cancel="changeTarget = null" />
    <AddSectionModal v-if="adding" :position="sections.length + 1" :busy="busy" @add="addSection" @cancel="adding = false" />

    <ConfirmModal
      v-if="sectionToDelete !== null"
      :title="'Delete section ' + sectionToDelete + '?'"
      message="The section and its video will be removed. Later sections move up by one."
      confirm-label="Delete section"
      danger
      @confirm="confirmDeleteSection"
      @cancel="sectionToDelete = null"
    />
    <ConfirmModal v-if="deleting" title="Delete this project?" message="This can’t be undone." confirm-label="Delete project" danger @confirm="removeProject" @cancel="deleting = false" />
  </div>
</template>
