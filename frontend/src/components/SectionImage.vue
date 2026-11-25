<script setup lang="ts">
import { ref } from 'vue'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'
import type { Section } from '@/types'
import AppIcon from './AppIcon.vue'

const props = defineProps<{
  projectId: string
  section: Section
  headingLabel: string
}>()
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
  await run(() => projectsStore.setSectionImage(props.projectId, props.section.position, file), 'Custom image saved')
}

async function reroll() {
  await run(() => projectsStore.rerollSectionImage(props.projectId, props.section.position), 'New public image found')
}

async function run(fn: () => Promise<void>, success: string) {
  busy.value = true
  try {
    await fn()
    push(success, 'success')
    emit('changed')
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="section-image-card">
    <div class="section-image-preview section-image-preview-large">
      <img v-if="section.imageUrl" :src="section.imageUrl" :alt="'Image for section ' + section.position" loading="lazy" />
      <div v-if="section.imageUrl" class="section-image-title-overlay">
        <span>{{ headingLabel }}</span>
        <strong>{{ section.title || 'Untitled' }}</strong>
      </div>
      <div v-if="!section.imageUrl" class="section-image-empty">
        <AppIcon name="image" :size="24" />
        <span>No image selected yet</span>
      </div>
      <div v-if="busy" class="section-image-busy"><AppIcon name="loader" :size="18" class="animate-spin" /> Updating image</div>
    </div>
    <div class="section-image-details">
      <div class="section-image-heading"><AppIcon name="image" :size="14" /> SECTION IMAGE</div>
      <p v-if="section.imageMetadata?.origin === 'commons'">
        <a v-if="section.imageMetadata.sourceUrl" :href="section.imageMetadata.sourceUrl" target="_blank" rel="noopener noreferrer">
          {{ section.imageMetadata.title || 'Open image source' }}
        </a>
        <strong v-else>{{ section.imageMetadata.title || 'Wikimedia Commons image' }}</strong>
      </p>
      <p v-else-if="section.imageMetadata?.origin === 'user'">Your custom image</p>
      <p v-else-if="section.imageMetadata?.origin === 'none'">No suitable public image was found automatically.</p>
      <p v-else-if="section.imageUrl">Image attached</p>
      <p v-else>No image selected yet.</p>
      <div v-if="section.imageMetadata?.origin === 'commons'" class="section-image-credit">
        <span v-if="section.imageMetadata.credit">Credit: {{ section.imageMetadata.credit }}</span>
        <span v-if="section.imageMetadata.license">
          Licence:
          <a v-if="section.imageMetadata.licenseUrl" :href="section.imageMetadata.licenseUrl" target="_blank" rel="noopener noreferrer">{{ section.imageMetadata.license }}</a>
          <strong v-else>{{ section.imageMetadata.license }}</strong>
        </span>
      </div>
      <div class="section-image-actions">
        <button type="button" :disabled="busy || section.videoStatus === 'processing'" @click="reroll">
          <AppIcon name="refresh" :size="14" /> {{ section.imageUrl ? 'Reroll image' : 'Find image' }}
        </button>
        <button type="button" :disabled="busy || section.videoStatus === 'processing'" @click="input?.click()">
          <AppIcon name="upload" :size="14" /> {{ section.imageMetadata?.origin === 'user' ? 'Replace custom image' : 'Add custom image' }}
        </button>
      </div>
      <input ref="input" type="file" :accept="ALLOWED.join(',')" class="hidden" :disabled="busy || section.videoStatus === 'processing'" @change="upload" />
    </div>
  </div>
</template>