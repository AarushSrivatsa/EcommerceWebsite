<script setup lang="ts">
import { computed } from 'vue'
import { formatDate } from '@/lib/format'
import { voices } from '@/data/options'
import type { Project } from '@/types'
import AppIcon from './AppIcon.vue'
import SceneThumb from './SceneThumb.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ project: Project }>()
const emit = defineEmits<{ open: []; remove: [] }>()

const percent = computed(() =>
  props.project.totalSections ? Math.round((props.project.sectionsCompleted / props.project.totalSections) * 100) : 0,
)
const voice = computed(() => voices.find((v) => v.id === props.project.voiceModel)?.label ?? props.project.voiceModel)
const seed = computed(() => props.project.userPrompt.length)
const typeLabel = computed(() => (props.project.videoType === 'auto' ? 'Auto' : props.project.videoType === 'story' ? 'Story' : 'Facts'))
</script>

<template>
  <article
    class="group relative flex cursor-pointer flex-col gap-4 rounded-2xl border border-white/8 bg-ink-850/70 p-4 transition hover:-translate-y-0.5 hover:border-brand-400/40 hover:bg-ink-800/80"
    tabindex="0"
    role="link"
    @click="emit('open')"
    @keydown.enter="emit('open')"
  >
    <SceneThumb :seed="seed" :label="`${project.estimatedDurationInMinutes} min`" />

    <div class="flex items-start justify-between gap-3">
      <h3 class="line-clamp-2 text-[15px] font-semibold leading-snug text-white">{{ project.userPrompt }}</h3>
      <StatusBadge :status="project.generationStatus" class="shrink-0" />
    </div>

    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-400">
      <span class="inline-flex items-center gap-1.5"><AppIcon name="book" :size="14" />{{ typeLabel }}</span>
      <span class="inline-flex items-center gap-1.5"><AppIcon name="mic" :size="14" />{{ voice }}</span>
      <span class="inline-flex items-center gap-1.5"><AppIcon name="layers" :size="14" />{{ project.totalSections }} sections</span>
    </div>

    <div v-if="project.generationStatus !== 'draft'">
      <div class="mb-1.5 flex justify-between text-xs text-zinc-500">
        <span>{{ project.sectionsCompleted }} / {{ project.totalSections }} sections</span>
        <span>{{ percent }}%</span>
      </div>
      <div class="h-1.5 overflow-hidden rounded-full bg-white/5">
        <div
          class="h-full rounded-full transition-all"
          :class="project.generationStatus === 'failed' ? 'bg-rose-500' : 'bg-gradient-to-r from-brand-500 to-accent-500'"
          :style="{ width: `${percent}%` }"
        />
      </div>
    </div>
    <p v-else class="text-xs text-zinc-500">Story written — waiting for your approval.</p>

    <div class="mt-auto flex items-center justify-between border-t border-white/5 pt-3 text-xs text-zinc-500">
      <span>Updated {{ formatDate(project.updatedAt) }}</span>
      <button
        class="rounded-lg p-1.5 text-zinc-500 opacity-100 transition hover:bg-rose-500/10 hover:text-rose-300 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
        aria-label="Delete project"
        @click.stop="emit('remove')"
      >
        <AppIcon name="trash" :size="16" />
      </button>
    </div>
  </article>
</template>
