<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { youtubeService, type YoutubeChannel } from '@/services/youtubeService'

const { push } = useToast()

const channels = ref<YoutubeChannel[]>([])
const loading = ref(true)
const busy = ref(false)
const toDelete = ref<YoutubeChannel | null>(null)

const name = ref('')
const clientJson = ref('')
const refreshToken = ref('')

async function load() {
  try {
    channels.value = await youtubeService.listChannels()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function add() {
  let parsed: unknown
  try {
    parsed = JSON.parse(clientJson.value)
  } catch {
    push('The client JSON is not valid JSON', 'error', 6000)
    return
  }
  busy.value = true
  try {
    await youtubeService.addChannel(name.value.trim(), parsed, refreshToken.value.trim())
    name.value = clientJson.value = refreshToken.value = ''
    push('Channel added', 'success')
    await load()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    busy.value = false
  }
}

async function select(channel: YoutubeChannel) {
  try {
    channels.value = await youtubeService.selectChannel(channel.id)
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  }
}

async function remove() {
  const channel = toDelete.value
  toDelete.value = null
  if (!channel) return
  try {
    await youtubeService.deleteChannel(channel.id)
    await load()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  }
}
</script>

<template>
  <div class="fade-up max-w-2xl">
    <RouterLink to="/" class="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white">
      <AppIcon name="chevron-left" :size="16" /> Projects
    </RouterLink>
    <h1 class="mt-3 text-2xl font-semibold tracking-tight text-white sm:text-3xl">YouTube channels</h1>
    <p class="mt-1 text-sm text-zinc-400">The selected channel is where videos get uploaded.</p>

    <div v-if="loading" class="shimmer mt-6 h-20 rounded-2xl border border-white/8 bg-ink-850/70" aria-busy="true" />
    <ul v-else-if="channels.length" class="mt-6 space-y-3">
      <li v-for="c in channels" :key="c.id" class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/8 bg-ink-850/70 px-5 py-4">
        <div class="flex min-w-0 items-center gap-3">
          <span class="truncate text-sm font-medium text-white">{{ c.name }}</span>
          <span v-if="c.isSelected" class="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-300 ring-1 ring-inset ring-emerald-400/20">Selected</span>
        </div>
        <div class="flex gap-1">
          <button v-if="!c.isSelected" class="rounded-lg px-3 py-1.5 text-sm font-medium text-brand-400 hover:bg-brand-500/10" @click="select(c)">Use this channel</button>
          <button class="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-zinc-400 hover:bg-rose-500/10 hover:text-rose-300" @click="toDelete = c">
            <AppIcon name="trash" :size="14" /> Remove
          </button>
        </div>
      </li>
    </ul>
    <p v-else class="mt-6 text-sm text-zinc-400">No channels yet. Add one below.</p>

    <form class="mt-8 rounded-2xl border border-white/8 bg-ink-850/70 p-5" @submit.prevent="add">
      <h2 class="text-sm font-semibold text-white">Add a channel</h2>
      <p class="mt-1 text-xs text-zinc-500">Google checks the details before they are stored. They are saved encrypted and never shown again.</p>
      <div class="mt-4 grid gap-4">
        <div>
          <label for="ch-name" class="text-sm font-medium text-zinc-200">Name</label>
          <input id="ch-name" v-model="name" required maxlength="100" placeholder="e.g. My channel" class="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white placeholder:text-zinc-600 focus:border-brand-400/60 focus:outline-none" />
        </div>
        <div>
          <label for="ch-json" class="text-sm font-medium text-zinc-200">Client JSON</label>
          <textarea id="ch-json" v-model="clientJson" required rows="6" spellcheck="false" placeholder="The client_secret JSON from Google Cloud" class="mt-2 w-full resize-y rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 font-mono text-xs text-white placeholder:text-zinc-600 focus:border-brand-400/60 focus:outline-none" />
        </div>
        <div>
          <label for="ch-token" class="text-sm font-medium text-zinc-200">Refresh token</label>
          <input id="ch-token" v-model="refreshToken" required type="password" autocomplete="off" placeholder="Of the Google account that owns the channel" class="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white placeholder:text-zinc-600 focus:border-brand-400/60 focus:outline-none" />
        </div>
      </div>
      <div class="mt-5 flex justify-end">
        <button type="submit" :disabled="busy" class="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white enabled:hover:bg-brand-500 disabled:opacity-40">
          <AppIcon :name="busy ? 'loader' : 'plus'" :size="16" :class="{ 'animate-spin': busy }" /> Add channel
        </button>
      </div>
    </form>

    <ConfirmModal
      v-if="toDelete"
      :title="`Remove ${toDelete.name}?`"
      message="The stored credentials are deleted. Videos already on YouTube are not affected."
      confirm-label="Remove"
      danger
      @confirm="remove"
      @cancel="toDelete = null"
    />
  </div>
</template>
