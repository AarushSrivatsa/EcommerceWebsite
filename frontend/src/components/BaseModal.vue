<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import AppIcon from './AppIcon.vue'

withDefaults(defineProps<{ title: string; description?: string; widthClass?: string }>(), {
  widthClass: 'max-w-lg',
})
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" :aria-label="title">
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" @click="emit('close')" />
      <div
        class="fade-up relative flex max-h-[90vh] w-full flex-col rounded-t-2xl border border-white/10 bg-ink-850 shadow-2xl sm:rounded-2xl"
        :class="widthClass"
      >
        <header class="flex items-start justify-between gap-4 border-b border-white/5 px-5 py-4">
          <div>
            <h2 class="text-base font-semibold text-white">{{ title }}</h2>
            <p v-if="description" class="mt-0.5 text-sm text-zinc-400">{{ description }}</p>
          </div>
          <button class="rounded-lg p-1.5 text-zinc-400 transition hover:bg-white/5 hover:text-white" aria-label="Close" @click="emit('close')">
            <AppIcon name="x" />
          </button>
        </header>
        <div class="overflow-y-auto px-5 py-4"><slot /></div>
        <footer v-if="$slots.footer" class="flex flex-wrap justify-end gap-2 border-t border-white/5 px-5 py-3">
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>
