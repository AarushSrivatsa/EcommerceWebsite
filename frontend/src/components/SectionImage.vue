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
  <div class="flex flex-col gap-3 sm:flex-row">
    <div class="relative w-full shrink-0 sm:w-44">
      <img v-if="section.imageUrl" :src="section.imageUrl" :alt="`Image for section ${section.position}`" class="aspect-video w-full rounded-lg object-cover ring-1 ring-white/10" loading="lazy" />
      <button
        v-else
        type="button"
        :disabled="busy"
        class="grid aspect-video w-full place-items-center rounded-lg border border-dashed border-white/20 bg-black/20 text-zinc-400 transition hover:border-brand-400/60 hover:text-white disabled:opacity-60"
        @click="input?.click()"
      >
        <span class="flex flex-col items-center gap-1 text-xs font-medium"><AppIcon name="upload" :size="20" /> Add image</span>
      </button>
      <div v-if="busy" class="absolute inset-0 grid place-items-center rounded-lg bg-black/60"><AppIcon name="loader" class="animate-spin text-white" /></div>
    </div>

    <div class="min-w-0 flex-1">
      <div v-if="section.imagePrompt" class="rounded-xl border border-brand-400/20 bg-brand-500/[0.07] p-3">
        <p class="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-brand-400"><AppIcon name="image" :size="13" /> Suggested image</p>
        <p class="mt-1.5 text-sm leading-relaxed text-zinc-100">{{ section.imagePrompt }}</p>
        <button type="button" class="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-white" @click="copyIdea"><AppIcon name="copy" :size="13" /> Copy</button>
      </div>
      <p v-else class="text-xs text-zinc-500">No image suggestion for this section.</p>

      <div class="mt-2 flex flex-wrap gap-1">
        <button type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-300 hover:bg-white/5 hover:text-white disabled:opacity-50" @click="input?.click()">
          <AppIcon name="upload" :size="14" /> {{ section.imageUrl ? 'Replace image' : 'Upload image' }}
        </button>
        <button v-if="section.imageUrl" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-400 hover:bg-rose-500/10 hover:text-rose-300 disabled:opacity-50" @click="remove">
          <AppIcon name="trash" :size="14" /> Remove image
        </button>
      </div>
      <input ref="input" type="file" :accept="ALLOWED.join(',')" class="hidden" @change="upload" />
    </div>
  </div>
</template>
