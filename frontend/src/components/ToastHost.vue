<script setup lang="ts">
import { useToast } from '@/lib/toast'
import AppIcon from './AppIcon.vue'

const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast-item" :class="'toast-' + t.tone">
      <AppIcon :name="t.tone === 'error' ? 'alert' : t.tone === 'success' ? 'check' : 'sparkles'" :size="17" />
      <span>{{ t.message }}</span>
      <button aria-label="Dismiss" @click="dismiss(t.id)"><AppIcon name="x" :size="14" /></button>
    </div>
  </div>
</template>
