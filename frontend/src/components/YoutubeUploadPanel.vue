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
  <section class="youtube-upload-card">
    <div class="youtube-upload-heading">
      <div><p class="eyebrow">PUBLISH</p><h2>Upload to YouTube</h2><p>Send your finished video to your channel.</p></div>
      <span class="youtube-upload-icon"><AppIcon name="upload" :size="18" /></span>
    </div>

    <div v-if="loading" class="shimmer youtube-upload-loading" aria-busy="true" />
    <p v-else-if="!channels.length" class="youtube-upload-empty">
      No YouTube channel connected yet.
      <RouterLink to="/youtube">Connect a channel</RouterLink> to publish this video.
    </p>

    <template v-else>
      <div class="youtube-upload-channel">
        <label for="yt-channel" class="field-label">Upload destination</label>
        <div><select id="yt-channel" :value="selected?.id" :disabled="uploading" @change="pickChannel">
          <option v-for="c in channels" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select><RouterLink to="/youtube">Manage channels</RouterLink></div>
      </div>

      <div v-if="uploading" class="upload-status upload-status-info" role="status">
        <AppIcon name="loader" :size="15" class="animate-spin" /> Uploading to {{ selected?.name }}… You can leave this page.
      </div>
      <div v-else-if="upload.status === 'done' && upload.url" class="upload-status upload-status-success">
        <strong>Upload complete</strong><a :href="upload.url" target="_blank" rel="noopener">{{ upload.url }}</a>
        <small>YouTube may still be processing your video.</small>
      </div>
      <div v-else-if="upload.status === 'failed'" class="upload-status upload-status-error">
        <strong>Upload failed</strong><span>{{ upload.error }}</span>
      </div>

      <div class="youtube-upload-fields">
        <div><label for="yt-title" class="field-label">Video title</label><input id="yt-title" v-model="title" maxlength="100" placeholder="Leave empty to use the script’s title" /></div>
        <div><label for="yt-description" class="field-label">Description</label><textarea id="yt-description" v-model="description" rows="3" maxlength="5000" placeholder="Add a description for your video…" /></div>
        <div><label for="yt-privacy" class="field-label">Visibility</label><select id="yt-privacy" v-model="privacy"><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></div>
      </div>
      <div class="youtube-upload-footer"><p>Choose visibility carefully. You can change it later on YouTube.</p>
        <button :disabled="busy || !selected" class="primary-action" @click="send"><AppIcon name="upload" :size="15" /> {{ busy ? 'Starting upload…' : upload.status === 'done' ? 'Upload again' : 'Upload video' }}</button>
      </div>
    </template>
  </section>
</template>
