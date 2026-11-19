// YouTube endpoints (routers/youtube.py) and their response shapes.
import { api } from './api'

export type Privacy = 'private' | 'unlisted' | 'public'
export type UploadStatus = 'none' | 'uploading' | 'done' | 'failed'

export interface YoutubeChannel {
  id: string
  name: string
  isSelected: boolean
}

export interface YoutubeUpload {
  status: UploadStatus
  url: string | null
  error: string | null
}

interface ChannelDto {
  id: string
  name: string
  is_selected: boolean
}

const toChannel = (c: ChannelDto): YoutubeChannel => ({ id: c.id, name: c.name, isSelected: c.is_selected })

export const youtubeService = {
  async listChannels(): Promise<YoutubeChannel[]> {
    return (await api.get<ChannelDto[]>('/youtube/channels')).map(toChannel)
  },
  async addChannel(name: string, clientId: string, clientSecret: string, refreshToken: string): Promise<YoutubeChannel> {
    return toChannel(await api.post<ChannelDto>('/youtube/channels', { name, client_id: clientId, client_secret: clientSecret, refresh_token: refreshToken }))
  },
  async selectChannel(id: string): Promise<YoutubeChannel[]> {
    return (await api.post<ChannelDto[]>(`/youtube/channels/${id}/select`)).map(toChannel)
  },
  deleteChannel: (id: string) => api.delete(`/youtube/channels/${id}`),

  getUpload: (scriptId: string) => api.get<YoutubeUpload>(`/scripts/${scriptId}/youtube`),
  upload: (scriptId: string, body: { title?: string; description: string; privacy: Privacy }) =>
    api.post<YoutubeUpload>(`/scripts/${scriptId}/youtube`, body),
}
