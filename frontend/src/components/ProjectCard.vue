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
    class="project-card"
    tabindex="0"
    role="link"
    :aria-label="'Open project: ' + project.userPrompt"
    @click="emit('open')"
    @keydown.enter="emit('open')"
    @keydown.space.prevent="emit('open')"
  >
    <div class="project-card-art">
      <SceneThumb :seed="seed" :label="project.estimatedDurationInMinutes + ' min'" />
      <div class="project-card-art-overlay">
        <span class="project-card-type">{{ typeLabel }} VIDEO</span>
        <span class="project-card-open"><AppIcon name="arrow-right" :size="17" /></span>
      </div>
    </div>

    <div class="project-card-content">
      <div class="project-card-title-row">
        <h3>{{ project.userPrompt }}</h3>
        <StatusBadge :status="project.generationStatus" />
      </div>

      <div class="project-card-meta">
        <span><AppIcon name="mic" :size="14" />{{ voice }}</span>
        <span><AppIcon name="layers" :size="14" />{{ project.totalSections }} sections</span>
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
        <span>Updated {{ formatDate(project.updatedAt) }}</span>
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
  </article>
</template>
