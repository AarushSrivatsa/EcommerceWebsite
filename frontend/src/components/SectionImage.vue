<script setup lang="ts">
import { ref } from 'vue'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'
import type { Section } from '@/types'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ projectId: string; section: Section }>()
const emit = defineEmits<{ changed: [] }>()
const { push } = useToast()
const input = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const ALLOWED = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']
const MAX_MB = 15

async function upload(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  if (!ALLOWED.some((ext) => file.name.toLowerCase().endsWith(ext))) {
    push(`Use one of: ${ALLOWED.join(' ')}`, 'error', 5000)
    return
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    push(`The image is larger than ${MAX_MB} MB`, 'error', 5000)
    return
  }
  await run(() => projectsStore.setSectionImage(props.projectId, props.section.position, file))
}

async function remove() {
  await run(() => projectsStore.removeSectionImage(props.projectId, props.section.position))
}

async function run(fn: () => Promise<void>) {
  busy.value = true
  try {
    await fn()
    emit('changed')
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="section-image-row">
    <div class="section-image-preview">
      <img v-if="section.imageUrl" :src="section.imageUrl" :alt="'Image for section ' + section.position" loading="lazy" />
      <button v-else type="button" :disabled="busy || section.videoStatus === 'processing'" class="section-image-empty" @click="input?.click()">
        <AppIcon name="image" :size="21" />
        <span>Choose this section’s image</span>
      </button>
      <div v-if="busy" class="section-image-busy"><AppIcon name="loader" :size="18" class="animate-spin" /> Saving</div>
    </div>
    <div class="section-image-details">
      <div v-if="section.imagePrompt" class="image-prompt-card">
        <div class="image-prompt-heading"><AppIcon name="sparkles" :size="14" /> IMAGE IDEA</div>
        <p>{{ section.imagePrompt }}</p>
      </div>
      <p v-else class="section-image-no-prompt">Upload one still image for this section.</p>
      <div class="section-image-actions">
        <button type="button" :disabled="busy || section.videoStatus === 'processing'" @click="input?.click()">
          <AppIcon name="upload" :size="14" />
          {{ section.imageUrl ? 'Replace image' : 'Upload image' }}
        </button>
        <button v-if="section.imageUrl" type="button" :disabled="busy || section.videoStatus === 'processing'" class="remove-image-action" @click="remove">
          <AppIcon name="trash" :size="14" /> Remove
        </button>
      </div>
      <input ref="input" type="file" :accept="ALLOWED.join(',')" class="hidden" :disabled="section.videoStatus === 'processing'" @change="upload" />
    </div>
  </div>
</template>
