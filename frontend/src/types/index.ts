// UI-side shapes (camelCase). Raw API shapes are mapped in projectService.ts.

export type VideoType = 'auto' | 'facts' | 'story'
export type GenerationStatus = 'generating' | 'ready' | 'failed'
export type FinalVideoStatus = 'none' | 'processing' | 'ready' | 'outdated' | 'failed'
export type SectionVideoStatus = 'pending' | 'processing' | 'ready' | 'failed'
export type SectionRenderMode = 'image' | 'cinematic'

export interface Voice {
  id: string
  label: string
  accent: string
}

export interface ResearchSource {
  title: string
  url: string
  domain: string | null
  excerpt: string
  similarity: number
}

export interface VisualBeat {
  narration: string
  visual: string
  onScreenText: string
  camera: string
  imageUrl: string | null
  imageOrigin?: 'commons' | 'user' | null
  imageTitle?: string | null
  imageCredit?: string | null
  imageLicense?: string | null
  imageLicenseUrl?: string | null
  imageSourceUrl?: string | null
  imageSearchQuery?: string | null
}

export interface Section {
  position: number
  text: string
  wordCount: number
  imagePrompt: string | null
  imageUrl: string | null
  videoUrl: string | null
  creditsUrl: string | null
  subtitleUrl: string | null
  videoStatus: SectionVideoStatus
  renderMode: SectionRenderMode
  videoError: string | null
  sources: ResearchSource[]
  visualPlan: VisualBeat[]
  similarityScore: number | null
  similarityThreshold: number | null
  groundingScore: number | null
  groundingFeedback: string | null
}

export interface Project {
  id: string
  userPrompt: string
  videoType: VideoType
  voiceModel: string
  wordsPerMinute: number
  similarityThreshold: number
  researchStatus: 'pending' | 'ready' | 'unavailable'
  researchError: string | null
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

/** Values collected by the New project form. */
export interface NewProjectForm {
  userPrompt: string
  videoType: VideoType
  estimatedDurationInMinutes: number
  wordsPerMinute: number
  totalSections: number | null
  voiceModel: string
  similarityThreshold: number | null // null = automatic facts/story recommendation
}
