<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { countWords } from '@/lib/format'
import type { Section } from '@/types'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ section: Section; total: number; saving?: boolean }>()
const emit = defineEmits<{
  save: [text: string]
  'request-change': []
  'insert-below': []
  remove: []
}>()

// Edits stay local until the field loses focus, so we don't hit the backend on every keystroke.
const text = ref(props.section.text)
watch(() => props.section.text, (t) => (text.value = t))

const words = computed(() => countWords(text.value))
const rows = computed(() => Math.max(3, Math.ceil(text.value.length / 90)))
const dirty = computed(() => text.value.trim() !== props.section.text.trim())

function commit() {
  const t = text.value.trim()
  if (!t) {
    text.value = props.section.text // backend rejects empty text: revert
    return
  }
  if (dirty.value) emit('save', t)
}
</script>

<template>
  <li class="rounded-2xl border border-white/8 bg-ink-850/70 p-4 transition focus-within:border-brand-400/40 sm:p-5">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <span class="grid size-7 place-items-center rounded-lg bg-brand-500/15 text-xs font-semibold text-brand-400">{{ section.position }}</span>
        <span class="text-xs text-zinc-500">Section {{ section.position }} of {{ total }}</span>
        <span v-if="saving" class="inline-flex items-center gap-1 text-xs text-brand-400"><AppIcon name="loader" :size="12" class="animate-spin" /> Saving…</span>
        <span v-else-if="dirty" class="text-xs text-amber-300">Unsaved</span>
      </div>
      <div class="flex items-center gap-1">
        <button class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-300 transition hover:bg-white/5 hover:text-white" @click="emit('request-change')">
          <AppIcon name="wand" :size="14" /> Request changes
        </button>
        <button class="rounded-lg p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-white" aria-label="Add section below" title="Add section below" @click="emit('insert-below')">
          <AppIcon name="plus" :size="16" />
        </button>
        <button class="rounded-lg p-1.5 text-zinc-500 transition hover:bg-rose-500/10 hover:text-rose-300" aria-label="Delete section" title="Delete section" @click="emit('remove')">
          <AppIcon name="trash" :size="16" />
        </button>
      </div>
    </div>

    <textarea
      v-model="text"
      :rows="rows"
      :disabled="saving"
      :aria-label="`Text of section ${section.position}`"
      placeholder="Write this section…"
      class="mt-3 w-full resize-y rounded-xl border border-transparent bg-black/20 p-3 text-[15px] leading-relaxed text-zinc-100 placeholder:text-zinc-600 focus:border-brand-400/50 focus:outline-none disabled:opacity-60"
      @blur="commit"
    />

    <div class="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
      <span v-if="section.imagePrompt" class="inline-flex min-w-0 items-center gap-1.5"><AppIcon name="image" :size="13" /><span class="truncate">{{ section.imagePrompt }}</span></span>
      <span v-else />
      <span>{{ words }} words</span>
    </div>
  </li>
</template>
