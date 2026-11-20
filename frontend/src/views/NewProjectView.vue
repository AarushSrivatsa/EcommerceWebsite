<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import { examplePrompts, voices } from '@/data/options'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'
import type { NewProjectForm, VideoType } from '@/types'

const router = useRouter()
const { push } = useToast()

const form = reactive<NewProjectForm>({
  userPrompt: '',
  videoType: 'auto',
  estimatedDurationInMinutes: 3,
  wordsPerMinute: 150,
  totalSections: null,
  voiceModel: 'Zoey',
  similarityThreshold: null,
})
const autoSections = ref(true)
const sectionCount = ref(6)
const generating = ref(false)

const typeOptions: { value: VideoType; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'facts', label: 'Facts' },
  { value: 'story', label: 'Story' },
]

const typeHint: Record<VideoType, string> = {
  auto: 'We’ll decide whether your idea works best as facts or a story.',
  facts: 'A narrated list of interesting, self-contained facts.',
  story: 'A narrative with a beginning, a middle and an end.',
}

const estimatedWords = computed(() => Math.round(form.estimatedDurationInMinutes * form.wordsPerMinute))
const recommendedSimilarity = computed(() => form.videoType === 'story' ? 92 : 88)
const similarityValue = computed({
  get: () => form.similarityThreshold === null ? recommendedSimilarity.value : Math.round(form.similarityThreshold * 100),
  set: (value: number) => { form.similarityThreshold = value / 100 },
})
const canSubmit = computed(() => form.userPrompt.trim().length >= 3 && !generating.value)

async function submit() {
  if (!canSubmit.value) return
  generating.value = true
  try {
    form.totalSections = autoSections.value ? null : sectionCount.value
    const project = await projectsStore.createProject({ ...form })
    router.push({ name: 'project', params: { id: project.id } })      // the sections appear there as they are written
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
    generating.value = false
  }
}
</script>

<template>
  <div class="fade-up create-page">
    <div class="create-heading">
      <RouterLink to="/" class="back-link"><AppIcon name="chevron-left" :size="15" /> All projects</RouterLink>
      <p class="eyebrow mt-5">NEW PROJECT</p>
      <h1 class="page-title mt-2">Let’s make a video.</h1>
      <p class="page-subtitle mt-2">Start with your idea. You can edit the script before creating any videos.</p>
    </div>

    <div class="create-layout mt-7">
      <form class="create-form" @submit.prevent="submit">
        <section class="editor-panel">
          <div class="panel-heading">
            <span class="panel-step">01</span>
            <div><h2>Your idea</h2><p>What would you like your video to be about?</p></div>
          </div>
          <label for="prompt" class="field-label">Describe your video</label>
          <textarea
            id="prompt"
            v-model="form.userPrompt"
            rows="5"
            maxlength="2000"
            :disabled="generating"
            placeholder="Example: 7 strange things that happen in deep ocean…"
            class="prompt-input"
          />
          <div class="prompt-footer">
            <span>Be as specific as you like. You can refine the script later.</span>
            <span>{{ form.userPrompt.length }}/2000</span>
          </div>
          <div class="example-prompts">
            <span class="field-label">Need an idea?</span>
            <button
              v-for="p in examplePrompts"
              :key="p"
              type="button"
              :disabled="generating"
              class="example-chip"
              @click="form.userPrompt = p"
            >
              {{ p }}
            </button>
          </div>
        </section>

        <section class="editor-panel">
          <div class="panel-heading">
            <span class="panel-step">02</span>
            <div><h2>Choose your format</h2><p>Set the style and length of your video.</p></div>
          </div>
          <div class="field-group">
            <span class="field-label">Video style</span>
            <SegmentedControl v-model="form.videoType" :options="typeOptions" aria-label="Video type" />
            <p class="field-hint">{{ typeHint[form.videoType] }}</p>
          </div>

          <div class="range-grid">
            <div class="range-card">
              <div class="range-card-heading">
                <label for="duration" class="field-label">Video length</label>
                <strong>{{ form.estimatedDurationInMinutes }} min</strong>
              </div>
              <input id="duration" v-model.number="form.estimatedDurationInMinutes" type="range" min="1" max="30" step="1" class="range-input" />
              <div class="range-ends"><span>1 min</span><span>30 min</span></div>
            </div>
            <div class="range-card">
              <div class="range-card-heading">
                <label for="wpm" class="field-label">Narration speed</label>
                <strong>{{ form.wordsPerMinute }} wpm</strong>
              </div>
              <input id="wpm" v-model.number="form.wordsPerMinute" type="range" min="60" max="300" step="10" class="range-input" />
              <div class="range-ends"><span>Slow</span><span>Fast</span></div>
            </div>
          </div>
          <p class="estimate-note">That’s approximately <strong>{{ estimatedWords.toLocaleString() }} words</strong> of narration.</p>

          <div class="section-count-setting">
            <div><span class="field-label">Script sections</span><p class="field-hint">Let the writer choose, or set a number yourself.</p></div>
            <label class="toggle-label"><input v-model="autoSections" type="checkbox" /> Automatic</label>
          </div>
          <input
            v-if="!autoSections"
            v-model.number="sectionCount"
            type="number"
            min="1"
            max="200"
            aria-label="Number of sections"
            class="section-count-input"
          />

          <div class="similarity-setting">
            <div class="range-card-heading">
              <label for="similarity-threshold" class="field-label">Section similarity limit</label>
              <strong>{{ similarityValue }}%</strong>
            </div>
            <input
              id="similarity-threshold"
              v-model.number="similarityValue"
              type="range"
              min="60"
              max="100"
              step="1"
              class="range-input"
            />
            <div class="range-ends"><span>Stricter</span><span>More permissive</span></div>
            <p class="field-hint">
              A section at or above this similarity to an earlier section is rewritten. Lower values prevent more repetition.
              Recommended: {{ recommendedSimilarity }}% for this format.
            </p>
            <button
              v-if="form.similarityThreshold !== null"
              type="button"
              class="text-action similarity-reset"
              @click="form.similarityThreshold = null"
            >Use recommended {{ recommendedSimilarity }}%</button>
          </div>
        </section>

        <section class="editor-panel">
          <div class="panel-heading">
            <span class="panel-step">03</span>
            <div><h2>Pick a narrator</h2><p>Choose the voice that fits your video.</p></div>
          </div>
          <div class="voice-grid">
            <label
              v-for="v in voices"
              :key="v.id"
              class="voice-option"
              :class="{ 'voice-option-active': form.voiceModel === v.id }"
            >
              <input v-model="form.voiceModel" type="radio" name="voice" :value="v.id" />
              <span class="voice-icon"><AppIcon name="mic" :size="17" /></span>
              <span class="voice-copy"><strong>{{ v.label }}</strong><small>{{ v.accent }}</small></span>
              <AppIcon v-if="form.voiceModel === v.id" name="check" :size="16" class="voice-check" />
            </label>
          </div>
        </section>

        <div class="create-submit-row">
          <RouterLink to="/" class="secondary-action">Cancel</RouterLink>
          <button type="submit" :disabled="!canSubmit" class="primary-action">
            <AppIcon :name="generating ? 'loader' : 'sparkles'" :class="{ 'animate-spin': generating }" :size="17" />
            {{ generating ? 'Starting your project…' : 'Generate my script' }}
            <AppIcon v-if="!generating" name="arrow-right" :size="16" />
          </button>
        </div>
      </form>

      <aside class="create-aside">
        <div class="summary-card">
          <div class="summary-card-top"><span class="summary-spark"><AppIcon name="sparkles" :size="16" /></span><span>LIVE PREVIEW</span></div>
          <h2>{{ form.userPrompt.trim() || 'Your video idea' }}</h2>
          <p class="summary-caption">Your project at a glance</p>
          <div class="summary-details">
            <div><span>Format</span><strong>{{ form.videoType === 'auto' ? 'Smart format' : form.videoType === 'facts' ? 'Facts' : 'Story' }}</strong></div>
            <div><span>Length</span><strong>{{ form.estimatedDurationInMinutes }} minutes</strong></div>
            <div><span>Words</span><strong>{{ estimatedWords.toLocaleString() }} approx.</strong></div>
            <div><span>Sections</span><strong>{{ autoSections ? 'Automatic' : sectionCount }}</strong></div>
            <div><span>Narrator</span><strong>{{ voices.find((v) => v.id === form.voiceModel)?.label ?? form.voiceModel }}</strong></div>
            <div><span>Similarity limit</span><strong>{{ similarityValue }}%</strong></div>
          </div>
          <div class="summary-divider"></div>
          <p class="summary-caption">How it works</p>
          <ol class="workflow-list">
            <li><span>1</span><div><strong>Generate your script</strong><small>Your idea becomes a structured story.</small></div></li>
            <li><span>2</span><div><strong>Review and edit</strong><small>Make every section sound right.</small></div></li>
            <li><span>3</span><div><strong>Build and publish</strong><small>Create the videos and upload them.</small></div></li>
          </ol>
        </div>
        <p class="aside-footnote"><AppIcon name="check" :size="14" /> Nothing is rendered until you choose to build the video.</p>
      </aside>
    </div>
  </div>
</template>
