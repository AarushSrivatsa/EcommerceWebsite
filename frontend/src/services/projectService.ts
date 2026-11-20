// The only file that knows the backend's endpoints and snake_case response shapes.
import type { FinalVideoStatus, GenerationStatus, NewProjectForm, Project, Section, SectionRenderMode, SectionVideoStatus } from '@/types'
import { api } from './api'

// ---- raw backend shapes (routers/scripts.py, routers/sections.py) ----
interface FinalVideoDto {
  status: FinalVideoStatus
  url: string | null
  error: string | null
}

interface ScriptDto {
  id: string
  user_prompt: string
  video_type: 'facts' | 'story' | null
  voice_model: string | null
  words_per_minute: number
  similarity_threshold: number
  research_status: 'pending' | 'ready' | 'unavailable'
  research_error: string | null
  estimated_duration_in_hours: number
  total_sections: number | null
  sections_completed: number | null
  generation_status: GenerationStatus
  generation_error: string | null
  final_video: FinalVideoDto
  created_at: string | null
  updated_at: string | null
}

interface SectionDto {
  position: number
  text: string
  word_count: number
  image_prompt: string | null
  image_url: string | null
  audio_url: string | null
  video_url: string | null
  video_status: SectionVideoStatus
  render_mode: SectionRenderMode
  video_error: string | null
  updated_at: string | null
  sources: { title: string; url: string; domain: string | null; excerpt: string; similarity: number }[]
  visual_plan: { narration: string; visual: string; on_screen_text: string; camera: string; image_url?: string | null }[]
  similarity_score: number | null
  similarity_threshold: number | null
  grounding_score: number | null
  grounding_feedback: string | null
}

// ---- mappers ----
function toVoiceModel(value: string | null): string {
  if (!value) return 'Zoey'

  const legacyPrefixes = ['af_', 'am_', 'bf_', 'bm_']
  const legacyIds = ['default', 'en_us_zoey']
  const isLegacyVoice = legacyPrefixes.some((prefix) => value.startsWith(prefix)) || legacyIds.includes(value.toLowerCase())

  if (isLegacyVoice) return 'Zoey'

  return value
}

function toProject(s: ScriptDto): Project {
  const now = new Date().toISOString()
  return {
    id: s.id,
    userPrompt: s.user_prompt,
    videoType: s.video_type ?? 'auto',
    voiceModel: toVoiceModel(s.voice_model),
    wordsPerMinute: s.words_per_minute,
    similarityThreshold: s.similarity_threshold,
    researchStatus: s.research_status,
    researchError: s.research_error,
    estimatedDurationInMinutes: Math.round(s.estimated_duration_in_hours * 60 * 10) / 10,
    totalSections: s.total_sections ?? 0,
    sectionsCompleted: s.sections_completed ?? 0,
    generationStatus: s.generation_status,
    generationError: s.generation_error,
    finalVideoStatus: s.final_video.status,
    finalVideoUrl: s.final_video.url,
    finalVideoError: s.final_video.error,
    createdAt: s.created_at ?? now,
    updatedAt: s.updated_at ?? s.created_at ?? now,
  }
}

function toSection(s: SectionDto): Section {
  return {
    position: s.position,
    text: s.text,
    wordCount: s.word_count,
    imagePrompt: s.image_prompt,
    imageUrl: s.image_url,
    videoUrl: s.video_url,
    videoStatus: s.video_status,
    renderMode: s.render_mode ?? 'cinematic',
    videoError: s.video_error,
    sources: s.sources ?? [],
    visualPlan: (s.visual_plan ?? []).map((beat) => ({
      narration: beat.narration,
      visual: beat.visual,
      onScreenText: beat.on_screen_text,
      camera: beat.camera,
      imageUrl: beat.image_url ?? null,
    })),
    similarityScore: s.similarity_score,
    similarityThreshold: s.similarity_threshold,
    groundingScore: s.grounding_score,
    groundingFeedback: s.grounding_feedback,
  }
}

// ---- scripts ----
export async function listProjects(): Promise<Project[]> {
  return (await api.get<ScriptDto[]>('/scripts?limit=200')).map(toProject)
}

export async function getProject(id: string): Promise<Project> {
  return toProject(await api.get<ScriptDto>(`/scripts/${id}`))
}

/** Starts writing the script in the background. Nothing is rendered until you ask for it. */
export async function createProject(form: NewProjectForm): Promise<Project> {
  const dto = await api.post<ScriptDto>('/scripts', {
    user_prompt: form.userPrompt.trim(),
    estimated_duration_in_hours: form.estimatedDurationInMinutes / 60,
    words_per_minute: form.wordsPerMinute,
    total_sections: form.totalSections,
    voice_model: form.voiceModel,
    video_type: form.videoType === 'auto' ? null : form.videoType,
    similarity_threshold: form.similarityThreshold,
  })
  return toProject(dto)
}

export async function resumeGeneration(id: string): Promise<Project> {
  return toProject(await api.post<ScriptDto>(`/scripts/${id}/generate`))
}

export async function updateSettings(id: string, voiceModel: string, wordsPerMinute: number, similarityThreshold: number): Promise<Project> {
  return toProject(await api.patch<ScriptDto>(`/scripts/${id}`, {
    voice_model: voiceModel,
    words_per_minute: wordsPerMinute,
    similarity_threshold: similarityThreshold,
  }))
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/scripts/${id}`)
}

// ---- sections ----
export async function listSections(id: string): Promise<Section[]> {
  return (await api.get<SectionDto[]>(`/scripts/${id}/sections`)).map(toSection)
}

export async function updateSectionText(id: string, position: number, text: string): Promise<Section> {
  return toSection(await api.patch<SectionDto>(`/scripts/${id}/sections/${position}`, { text }))
}

/** Adds a section at `position` (others move down). Omit to append. */
export async function addSection(id: string, text: string, position?: number): Promise<Section> {
  return toSection(await api.post<SectionDto>(`/scripts/${id}/sections`, { text, position: position ?? null }))
}

export async function rewriteSection(id: string, position: number, instruction: string): Promise<Section> {
  return toSection(await api.post<SectionDto>(`/scripts/${id}/sections/${position}/rewrite`, { instruction }))
}

export async function setSectionImage(id: string, position: number, file: File): Promise<Section> {
  const form = new FormData()
  form.append('file', file)
  return toSection(await api.put<SectionDto>(`/scripts/${id}/sections/${position}/image`, form))
}

export async function removeSectionImage(id: string, position: number): Promise<Section> {
  return toSection(await api.delete<SectionDto>(`/scripts/${id}/sections/${position}/image`))
}

export async function setVisualBeatImage(id: string, position: number, beatIndex: number, file: File): Promise<Section> {
  const form = new FormData()
  form.append('file', file)
  return toSection(await api.put<SectionDto>(`/scripts/${id}/sections/${position}/image/beats/${beatIndex}`, form))
}

export async function removeVisualBeatImage(id: string, position: number, beatIndex: number): Promise<Section> {
  return toSection(await api.delete<SectionDto>(`/scripts/${id}/sections/${position}/image/beats/${beatIndex}`))
}

export async function setSectionRenderMode(id: string, position: number, renderMode: SectionRenderMode): Promise<Section> {
  return toSection(await api.patch<SectionDto>(`/scripts/${id}/sections/${position}/render-mode`, {
    render_mode: renderMode,
  }))
}

export async function rerenderSection(id: string, position: number): Promise<Section> {
  return toSection(await api.post<SectionDto>(`/scripts/${id}/sections/${position}/render`))
}

export async function deleteSection(id: string, position: number): Promise<void> {
  await api.delete(`/scripts/${id}/sections/${position}`)
}

// ---- videos (always started by a button: nothing renders on its own) ----
/** Builds the video of every section that has no up-to-date one. */
export async function buildSectionVideos(id: string): Promise<Project> {
  return toProject(await api.post<ScriptDto>(`/scripts/${id}/render_sections`))
}

export async function convertIntoVideo(id: string): Promise<Project> {
  return toProject(await api.post<ScriptDto>(`/convert_into_video/${id}`))
}

export async function deleteFinalVideo(id: string): Promise<void> {
  await api.delete(`/scripts/${id}/video`)
}
