<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import { useToast } from '@/lib/toast'
import { usePolling } from '@/lib/usePolling'
import { errorMessage } from '@/services/api'
import { youtubeService, type Privacy, type YoutubeChannel, type YoutubeUpload } from '@/services/youtubeService'

const props = defineProps<{ projectId: string }>()
const { push } = useToast()

const loading = ref(true)
const busy = ref(false)
const channels = ref<YoutubeChannel[]>([])
const upload = ref<YoutubeUpload>({ status: 'none', url: null, error: null })

const title = ref('')
const description = ref('')
const privacy = ref<Privacy>('private')

const selected = computed(() => channels.value.find((c) => c.isSelected) ?? null)
const uploading = computed(() => upload.value.status === 'uploading')

const poller = usePolling(async () => {
  upload.value = await youtubeService.getUpload(props.projectId)
  if (!uploading.value) poller.stop()
}, 3000)

onMounted(async () => {
  try {
    const [loadedChannels, currentUpload] = await Promise.all([
      youtubeService.listChannels(),
      youtubeService.getUpload(props.projectId),
    ])
    channels.value = loadedChannels
    upload.value = currentUpload
    if (uploading.value) poller.start()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    loading.value = false
  }
})

async function pickChannel(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  try {
    channels.value = await youtubeService.selectChannel(id)
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  }
}

async function send() {
  busy.value = true
  try {
    upload.value = await youtubeService.upload(props.projectId, {
      title: title.value.trim() || undefined, // empty: the backend uses the script's title
      description: description.value,
      privacy: privacy.value,
    })
    poller.start()
  } catch (e) {
    push(errorMessage(e), 'error', 6000)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mt-4 rounded-2xl border border-white/8 bg-ink-850/70 p-5">
    <h2 class="text-sm font-semibold text-white">Upload to YouTube</h2>

    <div v-if="loading" class="shimmer mt-4 h-20 rounded-xl border border-white/8" aria-busy="true" />

    <p v-else-if="!channels.length" class="mt-2 text-sm text-zinc-400">
      No YouTube channel yet.
      <RouterLink to="/youtube" class="font-medium text-brand-400 hover:text-brand-500">Add a channel</RouterLink>
      to upload this video.
    </p>

    <template v-else>
      <div class="mt-4">
        <label for="yt-channel" class="text-sm font-medium text-zinc-200">Channel</label>
        <div class="mt-2 flex flex-wrap items-center gap-3">
          <select id="yt-channel" :value="selected?.id" :disabled="uploading" class="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white focus:border-brand-400/60 focus:outline-none sm:max-w-xs" @change="pickChannel">
            <option v-for="c in channels" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <RouterLink to="/youtube" class="text-sm text-zinc-400 hover:text-white">Manage channels</RouterLink>
        </div>
      </div>

      <div v-if="uploading" class="mt-5 flex items-center gap-2 rounded-xl border border-sky-400/20 bg-sky-500/[0.06] px-4 py-3 text-sm text-sky-100" role="status">
        <AppIcon name="loader" :size="15" class="animate-spin" /> Uploading to {{ selected?.name }}… You can leave this page.
      </div>
      <template v-else>
        <div v-if="upload.status === 'done' && upload.url" class="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] px-4 py-3 text-sm text-emerald-100">
          Uploaded:
          <a :href="upload.url" target="_blank" rel="noopener" class="font-medium underline">{{ upload.url }}</a>
          <span class="block text-xs text-emerald-200/70">YouTube may still be processing it.</span>
        </div>
        <div v-else-if="upload.status === 'failed'" class="mt-5 rounded-xl border border-rose-500/25 bg-rose-500/[0.06] px-4 py-3 text-sm text-rose-100">
          Upload failed<template v-if="upload.error">: {{ upload.error }}</template>
        </div>

        <div class="mt-5 grid gap-4">
          <div>
            <label for="yt-title" class="text-sm font-medium text-zinc-200">Title</label>
            <input id="yt-title" v-model="title" maxlength="100" placeholder="Leave empty to use the script’s title" class="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white placeholder:text-zinc-600 focus:border-brand-400/60 focus:outline-none" />
          </div>
          <div>
            <label for="yt-description" class="text-sm font-medium text-zinc-200">Description</label>
            <textarea id="yt-description" v-model="description" rows="3" maxlength="5000" class="mt-2 w-full resize-y rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white focus:border-brand-400/60 focus:outline-none" />
          </div>
          <div>
            <label for="yt-privacy" class="text-sm font-medium text-zinc-200">Visibility</label>
            <select id="yt-privacy" v-model="privacy" class="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white focus:border-brand-400/60 focus:outline-none sm:max-w-xs">
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public">Public</option>
            </select>
          </div>
        </div>
        <div class="mt-5 flex justify-end">
          <button :disabled="busy || !selected" class="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white enabled:hover:bg-brand-500 disabled:opacity-40" @click="send">
            <AppIcon name="upload" :size="16" /> {{ upload.status === 'done' ? 'Upload again' : 'Upload' }}
          </button>
        </div>
      </template>
    </template>
  </div>
</template>
