<script setup lang="ts">
import { ref } from 'vue'
import { countWords } from '@/lib/format'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

defineProps<{ position: number; busy?: boolean }>()
const emit = defineEmits<{ add: [text: string]; cancel: [] }>()
const text = ref('')
</script>

<template>
  <BaseModal :title="'Add section ' + position" description="Write the narration for this new scene." width-class="max-w-2xl" @close="emit('cancel')">
    <textarea v-model="text" rows="7" autofocus aria-label="New section text" placeholder="Write the narration for this scene…" class="modal-textarea" />
    <p class="modal-hint">{{ countWords(text) }} words</p>
    <template #footer>
      <button class="modal-cancel" @click="emit('cancel')">Cancel</button>
      <button :disabled="!text.trim() || busy" class="modal-confirm" @click="emit('add', text.trim())">
        <AppIcon v-if="busy" name="loader" :size="14" class="animate-spin" />{{ busy ? 'Adding…' : 'Add section' }}
      </button>
    </template>
  </BaseModal>
</template>
