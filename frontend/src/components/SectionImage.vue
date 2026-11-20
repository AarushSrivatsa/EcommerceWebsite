<script setup lang="ts">
import { ref } from 'vue'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'
import type { Section } from '@/types'
import AppIcon from './AppIcon.vue'

// The picture of one section: shows it, lets you upload / replace / remove it, and shows the
// suggested image idea (what to look for or generate) as a readable card instead of fine print.
const props = defineProps<{ projectId: string; section: Section }>()
const emit = defineEmits<{ changed: [] }>()

const { push } = useToast()
const input = ref<HTMLInputElement | null>(null)
const busy = ref(false)

const ALLOWED = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'] // same list as the backend
const MAX_MB = 15

async function upload(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = '' // so choosing the same file again still fires
  if (!file) return
  if (!ALLOWED.some((ext) => file.name.toLowerCase().endsWith(ext))) return push(`Use one of: ${ALLOWED.join(' ')}`, 'error', 5000)
  if (file.size > MAX_MB * 1024 * 1024) return push(`The image is larger than ${MAX_MB} MB`, 'error', 5000)
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

async function copyIdea() {
  try {
    await navigator.clipboard.writeText(props.section.imagePrompt ?? '')
    push('Image idea copied', 'success')
  } catch {
    push('Couldn’t copy. Select the text and copy it by hand.', 'error')
  }
}
</script>

<template>
  <div class="section-image-row">
    <div class="section-image-preview">
      <img v-if="section.imageUrl" :src="section.imageUrl" :alt="'Image for section ' + section.position" loading="lazy" />
      <button v-else type="button" :disabled="busy" class="section-image-empty" @click="input?.click()">
        <AppIcon name="image" :size="21" /><span>Add a scene image</span>
      </button>
      <div v-if="busy" class="section-image-busy"><AppIcon name="loader" :size="18" class="animate-spin" /> Uploading</div>
    </div>

    <div class="section-image-details">
      <div v-if="section.imagePrompt && !section.visualPlan.length" class="image-prompt-card">
        <div class="image-prompt-heading"><AppIcon name="sparkles" :size="14" /> IMAGE IDEA</div>
        <p>{{ section.imagePrompt }}</p>
        <button type="button" class="image-prompt-copy" @click="copyIdea"><AppIcon name="copy" :size="13" /> Copy prompt</button>
      </div>
      <p v-else class="section-image-no-prompt">
        {{ section.visualPlan.length ? 'Shared fallback image for storyboard beats without their own visual.' : 'No suggested image for this scene.' }}
      </p>
      <p class="cinematic-render-hint">Free cinematic animation is generated from your storyboard. Upload a photo to feature it in the moving scene; no AI video API key is required.</p>
      <div class="section-image-actions">
        <button type="button" :disabled="busy" @click="input?.click()"><AppIcon name="upload" :size="14" /> {{ section.imageUrl ? 'Replace image' : 'Upload image' }}</button>
        <button v-if="section.imageUrl" type="button" :disabled="busy" class="remove-image-action" @click="remove"><AppIcon name="trash" :size="14" /> Remove</button>
      </div>
      <input ref="input" type="file" :accept="ALLOWED.join(',')" class="hidden" @change="upload" />
    </div>
  </div>
</template>
