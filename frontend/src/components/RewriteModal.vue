<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

// "Request changes": tell the writer how to redo one section.
defineProps<{ position: number; busy?: boolean }>()
const emit = defineEmits<{ apply: [instruction: string]; cancel: [] }>()

const instruction = ref('')
const quick = ['Make it funnier', 'Make it shorter', 'More dramatic', 'Simpler language']
</script>

<template>
  <BaseModal :title="`Request changes · Section ${position}`" description="Tell the writer what to change in this section." @close="!busy && emit('cancel')">
    <textarea
      v-model="instruction"
      rows="3"
      :disabled="busy"
      placeholder="e.g. Make it funnier"
      class="w-full resize-none rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white placeholder:text-zinc-500 focus:border-brand-400/60 focus:outline-none disabled:opacity-60"
    />
    <div class="mt-3 flex flex-wrap gap-2">
      <button v-for="q in quick" :key="q" :disabled="busy" class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-zinc-300 hover:border-brand-400/40 hover:text-white" @click="instruction = q">{{ q }}</button>
    </div>
    <template #footer>
      <button class="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-300 hover:bg-white/5" :disabled="busy" @click="emit('cancel')">Cancel</button>
      <button
        :disabled="!instruction.trim() || busy"
        class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white transition enabled:hover:bg-brand-500 disabled:opacity-40"
        @click="emit('apply', instruction.trim())"
      >
        <AppIcon v-if="busy" name="loader" :size="14" class="animate-spin" />
        {{ busy ? 'Rewriting…' : 'Apply changes' }}
      </button>
    </template>
  </BaseModal>
</template>
