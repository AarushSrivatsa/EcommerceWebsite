<script setup lang="ts">
import { computed } from 'vue'

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'
const props = defineProps<{ status: string }>()

const map: Record<string, { label: string; tone: Tone; pulse?: boolean }> = {
  generating: { label: 'Writing', tone: 'info', pulse: true },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Needs attention', tone: 'danger' },
  none: { label: 'Not built', tone: 'neutral' },
  processing: { label: 'Building video', tone: 'info', pulse: true },
  outdated: { label: 'Needs rebuild', tone: 'warning' },
  pending: { label: 'Not built', tone: 'neutral' },
}
const meta = computed(() => map[props.status] ?? { label: props.status, tone: 'neutral' as Tone })
</script>

<template>
  <span class="status-pill" :class="'status-' + meta.tone">
    <span class="status-dot" :class="{ 'status-pulse': meta.pulse }" />
    {{ meta.label }}
  </span>
</template>
