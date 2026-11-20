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
    <p class="modal-message">{{ message }}</p>
    <template #footer>
      <button class="modal-cancel" @click="emit('cancel')">Cancel</button>
      <button class="modal-confirm" :class="{ 'modal-confirm-danger': danger }" @click="emit('confirm')">{{ confirmLabel }}</button>
    </template>
  </BaseModal>
</template>
