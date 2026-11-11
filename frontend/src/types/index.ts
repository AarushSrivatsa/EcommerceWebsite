// UI-side shapes (camelCase). The raw backend shapes live in src/services/projectService.ts
// and are mapped here in one place.

export type VideoType = 'auto' | 'facts' | 'story'

export type GenerationStatus = 'generating' | 'ready' | 'failed'

export type FinalVideoStatus = 'none' | 'processing' | 'ready' | 'outdated' | 'failed'

export type SectionVideoStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface Voice {
  id: string
  label: string
  accent: string
}

export interface Section {
  position: number
  text: string
  wordCount: number
  imagePrompt: string | null
  imageUrl: string | null
  videoUrl: string | null
  videoStatus: SectionVideoStatus
  videoError: string | null
}

export interface Project {
  id: string
  userPrompt: string
  videoType: VideoType
  voiceModel: string
  wordsPerMinute: number
  estimatedDurationInMinutes: number
  totalSections: number
  sectionsCompleted: number
  generationStatus: GenerationStatus
  generationError: string | null
  finalVideoStatus: FinalVideoStatus
  finalVideoUrl: string | null
  finalVideoError: string | null
  createdAt: string
  updatedAt: string
}

/** Values collected by the "New project" form. */
export interface NewProjectForm {
  userPrompt: string
  videoType: VideoType
  estimatedDurationInMinutes: number
  wordsPerMinute: number
  totalSections: number | null // null = let the model decide
  voiceModel: string
}
