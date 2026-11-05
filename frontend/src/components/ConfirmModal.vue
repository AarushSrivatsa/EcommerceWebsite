<script setup lang="ts">
import BaseModal from './BaseModal.vue'

withDefaults(
  defineProps<{ title: string; message: string; confirmLabel?: string; danger?: boolean }>(),
  { confirmLabel: 'Confirm', danger: false },
)
const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <BaseModal :title="title" width-class="max-w-md" @close="emit('cancel')">
    <p class="text-sm leading-relaxed text-zinc-300">{{ message }}</p>
    <template #footer>
      <button class="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-300 transition hover:bg-white/5" @click="emit('cancel')">Cancel</button>
      <button
        class="rounded-lg px-3.5 py-2 text-sm font-semibold text-white transition"
        :class="danger ? 'bg-rose-600 hover:bg-rose-500' : 'bg-brand-600 hover:bg-brand-500'"
        @click="emit('confirm')"
      >
        {{ confirmLabel }}
      </button>
    </template>
  </BaseModal>
</template>
