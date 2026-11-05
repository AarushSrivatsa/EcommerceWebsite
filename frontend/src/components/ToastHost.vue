<script setup lang="ts">
import { useToast } from '@/lib/toast'
import AppIcon from './AppIcon.vue'

const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4" aria-live="polite">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="fade-up pointer-events-auto flex max-w-md items-center gap-3 rounded-xl border border-white/10 bg-ink-800 px-4 py-3 text-sm text-zinc-100 shadow-xl"
    >
      <AppIcon
        :name="t.tone === 'error' ? 'alert' : t.tone === 'success' ? 'check' : 'sparkles'"
        :class="t.tone === 'error' ? 'text-rose-400' : t.tone === 'success' ? 'text-emerald-400' : 'text-brand-400'"
      />
      <span>{{ t.message }}</span>
      <button class="ml-1 text-zinc-500 hover:text-white" aria-label="Dismiss" @click="dismiss(t.id)"><AppIcon name="x" :size="14" /></button>
    </div>
  </div>
</template>
