<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

defineProps<{ position: number; busy?: boolean }>()
const emit = defineEmits<{ apply: [instruction: string]; cancel: [] }>()
const instruction = ref('')
const quick = ['Make it funnier', 'Make it shorter', 'More dramatic', 'Simpler language']
</script>

<template>
  <BaseModal :title="'Revise section ' + position" description="Tell the writer what you want to change." @close="!busy && emit('cancel')">
    <textarea v-model="instruction" rows="4" :disabled="busy" placeholder="e.g. Open with a surprising fact and make the tone more conversational…" class="modal-textarea" />
    <div class="modal-suggestions"><button v-for="q in quick" :key="q" :disabled="busy" @click="instruction = q">{{ q }}</button></div>
    <template #footer>
      <button class="modal-cancel" :disabled="busy" @click="emit('cancel')">Cancel</button>
      <button :disabled="!instruction.trim() || busy" class="modal-confirm" @click="emit('apply', instruction.trim())">
        <AppIcon v-if="busy" name="loader" :size="14" class="animate-spin" />{{ busy ? 'Revising…' : 'Apply revision' }}
      </button>
    </template>
  </BaseModal>
</template>
