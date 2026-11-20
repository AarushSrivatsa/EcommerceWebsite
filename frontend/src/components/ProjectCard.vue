<script setup lang="ts">
import { computed } from 'vue'
import { formatDate } from '@/lib/format'
import { voices } from '@/data/options'
import type { Project } from '@/types'
import AppIcon from './AppIcon.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ project: Project }>()
const emit = defineEmits<{ open: []; remove: [] }>()

const percent = computed(() =>
  props.project.totalSections
    ? Math.round((props.project.sectionsCompleted / props.project.totalSections) * 100)
    : 0,
)
const voice = computed(() => voices.find((v) => v.id === props.project.voiceModel)?.label ?? props.project.voiceModel)
const typeLabel = computed(() =>
  props.project.videoType === 'auto' ? 'Auto format' : props.project.videoType === 'story' ? 'Story' : 'Facts',
)
const hasFinalVideo = computed(() => props.project.finalVideoStatus === 'ready' && !!props.project.finalVideoUrl)
</script>

<template>
  <article
    class="project-card"
    tabindex="0"
    role="link"
    :aria-label="'Open project: ' + project.userPrompt"
    @click="emit('open')"
    @keydown.enter="emit('open')"
    @keydown.space.prevent="emit('open')"
  >
    <div class="project-card-topline">
      <span class="project-type-pill">{{ typeLabel }}</span>
      <span class="project-updated">Updated {{ formatDate(project.updatedAt) }}</span>
    </div>

    <div v-if="hasFinalVideo" class="project-video-preview">
      <video
        :src="project.finalVideoUrl ?? undefined"
        controls
        playsinline
        preload="metadata"
        aria-label="Preview final video"
        @click.stop
      />
      <span class="project-video-label"><AppIcon name="check" :size="12" /> Final video</span>
    </div>

    <div class="project-card-content">
      <div class="project-card-title-row">
        <h3>{{ project.userPrompt }}</h3>
        <StatusBadge :status="project.generationStatus" />
      </div>

      <div class="project-card-meta">
        <span><AppIcon name="mic" :size="15" />{{ voice }}</span>
        <span><AppIcon name="layers" :size="15" />{{ project.totalSections }} sections</span>
        <span><AppIcon name="clock" :size="15" />{{ project.estimatedDurationInMinutes }} min</span>
      </div>

      <div class="project-card-progress">
        <div class="project-card-progress-label">
          <span>{{ project.sectionsCompleted }} of {{ project.totalSections }} sections written</span>
          <strong>{{ percent }}%</strong>
        </div>
        <div class="progress-track">
          <div
            class="progress-fill"
            :class="{ 'progress-fill-failed': project.generationStatus === 'failed' }"
            :style="{ width: percent + '%' }"
          />
        </div>
      </div>

      <div class="project-card-footer">
        <span>{{ hasFinalVideo ? 'Finished video available' : project.generationStatus === 'generating' ? 'Script is being written' : 'Open to continue editing' }}</span>
        <div class="project-card-footer-actions">
          <span class="open-project-hint">Open project <AppIcon name="arrow-right" :size="14" /></span>
          <button
            class="project-card-delete"
            aria-label="Delete project"
            title="Delete project"
            @click.stop="emit('remove')"
          >
            <AppIcon name="trash" :size="16" />
          </button>
        </div>
      </div>
    </div>
  </article>
</template>
