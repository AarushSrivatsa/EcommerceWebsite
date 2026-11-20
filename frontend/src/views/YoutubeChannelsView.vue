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
const clientId = ref('')
const clientSecret = ref('')
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
  busy.value = true
  try {
    await youtubeService.addChannel(name.value.trim(), clientId.value.trim(), clientSecret.value.trim(), refreshToken.value.trim())
    name.value = clientId.value = clientSecret.value = refreshToken.value = ''
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
  <div class="fade-up youtube-page">
    <div class="youtube-heading">
      <div>
        <p class="eyebrow">PUBLISHING</p>
        <h1 class="page-title mt-3">YouTube channels</h1>
        <p class="page-subtitle mt-2">Connect the channel you want your finished videos uploaded to.</p>
      </div>
      <span class="youtube-heading-icon"><AppIcon name="upload" :size="23" /></span>
    </div>

    <div class="youtube-layout">
      <div class="youtube-main-column">
        <section class="youtube-panel">
          <div class="youtube-panel-heading">
            <div><h2>Connected channels</h2><p>Choose one channel as the default upload destination.</p></div>
            <span class="channel-count">{{ channels.length }} {{ channels.length === 1 ? 'channel' : 'channels' }}</span>
          </div>

          <div v-if="loading" class="shimmer channel-loading" aria-busy="true" />
          <ul v-else-if="channels.length" class="channel-list">
            <li v-for="c in channels" :key="c.id" class="channel-row">
              <span class="channel-avatar"><AppIcon name="play" :size="16" /></span>
              <div class="channel-info"><strong>{{ c.name }}</strong><small>{{ c.isSelected ? 'Default upload destination' : 'Connected channel' }}</small></div>
              <span v-if="c.isSelected" class="channel-selected"><AppIcon name="check" :size="13" /> Default</span>
              <div class="channel-actions">
                <button v-if="!c.isSelected" class="channel-use" @click="select(c)">Set as default</button>
                <button class="channel-remove" aria-label="Remove channel" title="Remove channel" @click="toDelete = c"><AppIcon name="trash" :size="15" /></button>
              </div>
            </li>
          </ul>
          <div v-else class="channel-empty">
            <span class="empty-state-icon"><AppIcon name="upload" :size="22" /></span>
            <strong>No channels connected</strong>
            <p>Add your YouTube channel details below to enable uploads.</p>
          </div>
        </section>

        <form class="youtube-panel add-channel-panel" @submit.prevent="add">
          <div class="youtube-panel-heading">
            <div><h2>Connect a channel</h2><p>Add the Google API credentials for the channel you own.</p></div>
            <span class="panel-step">01</span>
          </div>
          <div class="channel-form-grid">
            <div class="channel-field">
              <label for="ch-name" class="field-label">Channel name</label>
              <input id="ch-name" v-model="name" required maxlength="100" placeholder="e.g. My channel" />
            </div>
            <div class="channel-field">
              <label for="ch-id" class="field-label">Google client ID</label>
              <input id="ch-id" v-model="clientId" required autocomplete="off" spellcheck="false" placeholder="Your OAuth client ID" />
            </div>
            <div class="channel-field">
              <label for="ch-secret" class="field-label">Client secret</label>
              <input id="ch-secret" v-model="clientSecret" required type="password" autocomplete="off" placeholder="Your OAuth client secret" />
            </div>
            <div class="channel-field channel-field-full">
              <label for="ch-token" class="field-label">Refresh token</label>
              <input id="ch-token" v-model="refreshToken" required type="password" autocomplete="off" placeholder="Refresh token for the Google account that owns the channel" />
              <small>Use the refresh token generated for the same Google account as this YouTube channel.</small>
            </div>
          </div>
          <div class="channel-form-footer">
            <p><AppIcon name="check" :size="14" /> Credentials are checked by Google and stored encrypted.</p>
            <button type="submit" :disabled="busy" class="primary-action">
              <AppIcon :name="busy ? 'loader' : 'plus'" :size="16" :class="{ 'animate-spin': busy }" />
              {{ busy ? 'Connecting…' : 'Connect channel' }}
            </button>
          </div>
        </form>
      </div>

      <aside class="youtube-help-card">
        <span class="youtube-help-icon"><AppIcon name="upload" :size="18" /></span>
        <h2>One default destination</h2>
        <p>When you upload a finished video, it will go to the channel marked as Default. You can change that choice any time.</p>
        <div class="youtube-help-divider"></div>
        <strong>Your credentials stay private</strong>
        <p>Credentials are used only to connect to YouTube. They are encrypted before being stored and are not displayed again.</p>
      </aside>
    </div>

    <ConfirmModal
      v-if="toDelete"
      :title="'Remove ' + toDelete.name + '?'"
      message="The stored credentials are deleted. Videos already on YouTube are not affected."
      confirm-label="Remove channel"
      danger
      @confirm="remove"
      @cancel="toDelete = null"
    />
  </div>
</template>
