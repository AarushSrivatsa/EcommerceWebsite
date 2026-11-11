<script setup lang="ts">
import { computed } from 'vue'

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

const props = defineProps<{ status: string }>()

const map: Record<string, { label: string; tone: Tone; pulse?: boolean }> = {
  // project generation
  generating: { label: 'Generating', tone: 'info', pulse: true },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
  // final video
  none: { label: 'Not built', tone: 'neutral' },
  processing: { label: 'Processing', tone: 'info', pulse: true },
  outdated: { label: 'Outdated', tone: 'warning' },
  // section video
  pending: { label: 'Not built', tone: 'neutral' },
}

const tones: Record<Tone, string> = {
  neutral: 'bg-white/5 text-zinc-300 ring-white/10',
  info: 'bg-sky-500/10 text-sky-300 ring-sky-400/20',
  success: 'bg-emerald-500/10 text-emerald-300 ring-emerald-400/20',
  warning: 'bg-amber-500/10 text-amber-300 ring-amber-400/20',
  danger: 'bg-rose-500/10 text-rose-300 ring-rose-400/20',
}

const meta = computed(() => map[props.status] ?? { label: props.status, tone: 'neutral' as Tone })
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset"
    :class="tones[meta.tone]"
  >
    <span class="size-1.5 rounded-full bg-current" :class="{ 'animate-pulse': meta.pulse }" />
    {{ meta.label }}
  </span>
</template>
