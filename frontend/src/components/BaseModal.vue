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
    <div class="modal-overlay" role="dialog" aria-modal="true" :aria-label="title">
      <button class="modal-backdrop" aria-label="Close dialog" @click="emit('close')" />
      <div class="modal-panel fade-up" :class="widthClass">
        <header class="modal-header">
          <div><h2>{{ title }}</h2><p v-if="description">{{ description }}</p></div>
          <button class="modal-close" aria-label="Close" @click="emit('close')"><AppIcon name="x" :size="18" /></button>
        </header>
        <div class="modal-body"><slot /></div>
        <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
      </div>
    </div>
  </Teleport>
</template>
