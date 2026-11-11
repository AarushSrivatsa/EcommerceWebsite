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
  voiceModel: 'af_heart',
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
  <div class="fade-up mx-auto max-w-3xl">
    <RouterLink to="/" class="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white">
      <AppIcon name="chevron-left" :size="16" /> Projects
    </RouterLink>
    <h1 class="mt-3 text-2xl font-semibold tracking-tight text-white sm:text-3xl">New project</h1>
    <p class="mt-1 text-sm text-zinc-400">Describe your idea. The story is written first; you edit it, add images and build the videos yourself.</p>

    <form class="mt-8 space-y-8" @submit.prevent="submit">
      <!-- Prompt -->
      <section class="rounded-2xl border border-white/8 bg-ink-850/70 p-5">
        <label for="prompt" class="text-sm font-semibold text-white">What’s your video about?</label>
        <textarea
          id="prompt"
          v-model="form.userPrompt"
          rows="4"
          :disabled="generating"
          placeholder="e.g. Interesting facts about octopuses"
          class="mt-3 w-full resize-none rounded-xl border border-white/10 bg-black/20 p-3.5 text-sm leading-relaxed text-white placeholder:text-zinc-500 focus:border-brand-400/60 focus:outline-none disabled:opacity-60"
        />
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="p in examplePrompts"
            :key="p"
            type="button"
            :disabled="generating"
            class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-zinc-300 transition hover:border-brand-400/40 hover:text-white"
            @click="form.userPrompt = p"
          >
            {{ p }}
          </button>
        </div>
      </section>

      <!-- Format -->
      <section class="rounded-2xl border border-white/8 bg-ink-850/70 p-5">
        <h2 class="text-sm font-semibold text-white">Format</h2>
        <div class="mt-3"><SegmentedControl v-model="form.videoType" :options="typeOptions" aria-label="Video type" /></div>
        <p class="mt-2 text-xs text-zinc-500">{{ typeHint[form.videoType] }}</p>

        <div class="mt-6 grid gap-6 sm:grid-cols-2">
          <div>
            <div class="flex items-baseline justify-between">
              <label for="duration" class="text-sm font-medium text-zinc-200">Target length</label>
              <span class="text-sm font-semibold text-white">{{ form.estimatedDurationInMinutes }} min</span>
            </div>
            <input id="duration" v-model.number="form.estimatedDurationInMinutes" type="range" min="1" max="30" step="1" class="mt-3 w-full accent-brand-500" />
          </div>
          <div>
            <div class="flex items-baseline justify-between">
              <label for="wpm" class="text-sm font-medium text-zinc-200">Speaking speed</label>
              <span class="text-sm font-semibold text-white">{{ form.wordsPerMinute }} wpm</span>
            </div>
            <input id="wpm" v-model.number="form.wordsPerMinute" type="range" min="60" max="300" step="10" class="mt-3 w-full accent-brand-500" />
          </div>
        </div>
        <p class="mt-4 text-xs text-zinc-500">≈ {{ estimatedWords.toLocaleString() }} words in total</p>

        <div class="mt-6 border-t border-white/5 pt-5">
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-zinc-200">Number of sections</p>
              <p class="text-xs text-zinc-500">Let the writer decide, or set it yourself.</p>
            </div>
            <label class="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-300">
              <input v-model="autoSections" type="checkbox" class="size-4 accent-brand-500" /> Automatic
            </label>
          </div>
          <input
            v-if="!autoSections"
            v-model.number="sectionCount"
            type="number"
            min="1"
            max="200"
            aria-label="Number of sections"
            class="mt-3 w-28 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white focus:border-brand-400/60 focus:outline-none"
          />
        </div>
      </section>

      <!-- Voice -->
      <section class="rounded-2xl border border-white/8 bg-ink-850/70 p-5">
        <h2 class="text-sm font-semibold text-white">Narrator voice</h2>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label
            v-for="v in voices"
            :key="v.id"
            class="flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition"
            :class="form.voiceModel === v.id ? 'border-brand-400/60 bg-brand-500/10' : 'border-white/10 hover:border-white/20'"
          >
            <input v-model="form.voiceModel" type="radio" name="voice" :value="v.id" class="sr-only" />
            <span class="grid size-9 place-items-center rounded-lg bg-white/5 text-brand-400"><AppIcon name="mic" :size="16" /></span>
            <span class="leading-tight">
              <span class="block text-sm font-medium text-white">{{ v.label }}</span>
              <span class="block text-xs text-zinc-500">{{ v.accent }}</span>
            </span>
          </label>
        </div>
      </section>

      <div class="flex flex-wrap items-center justify-end gap-3">
        <RouterLink to="/" class="rounded-xl px-4 py-2.5 text-sm font-medium text-zinc-300 hover:bg-white/5">Cancel</RouterLink>
        <button
          type="submit"
          :disabled="!canSubmit"
          class="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <AppIcon :name="generating ? 'loader' : 'sparkles'" :class="{ 'animate-spin': generating }" />
          {{ generating ? 'Starting…' : 'Generate story' }}
        </button>
      </div>
    </form>
  </div>
</template>
