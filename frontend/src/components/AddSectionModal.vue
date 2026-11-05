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
  <BaseModal :title="`Add section ${position}`" description="Write the narration for the new section." width-class="max-w-2xl" @close="emit('cancel')">
    <textarea
      v-model="text"
      rows="6"
      autofocus
      aria-label="New section text"
      placeholder="Write this section…"
      class="w-full resize-y rounded-xl border border-white/10 bg-black/20 p-3 text-[15px] leading-relaxed text-white placeholder:text-zinc-500 focus:border-brand-400/60 focus:outline-none"
    />
    <p class="mt-2 text-xs text-zinc-500">{{ countWords(text) }} words</p>
    <template #footer>
      <button class="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-300 hover:bg-white/5" @click="emit('cancel')">Cancel</button>
      <button
        :disabled="!text.trim() || busy"
        class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white enabled:hover:bg-brand-500 disabled:opacity-40"
        @click="emit('add', text.trim())"
      >
        <AppIcon v-if="busy" name="loader" :size="14" class="animate-spin" />
        {{ busy ? 'Adding…' : 'Add section' }}
      </button>
    </template>
  </BaseModal>
</template>
