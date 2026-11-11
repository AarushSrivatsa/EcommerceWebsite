// Shared UI state backed by the real API (src/services/projectService.ts).
// Views call these actions; actions throw on API errors so views can toast them.
import { computed, reactive, readonly } from 'vue'
import * as service from '@/services/projectService'
import { ApiError } from '@/services/api'
import type { Project, Section } from '@/types'

interface State {
  loaded: boolean
  projects: Project[]
  sections: Record<string, Section[]>
}

const state = reactive<State>({ loaded: false, projects: [], sections: {} })

function upsert(p: Project) {
  const i = state.projects.findIndex((x) => x.id === p.id)
  if (i === -1) state.projects.push(p)
  else state.projects[i] = p
}

function setSection(id: string, section: Section) {
  const list = state.sections[id] ?? (state.sections[id] = [])
  const i = list.findIndex((s) => s.position === section.position)
  if (i === -1) list.push(section)
  else list[i] = section
  list.sort((a, b) => a.position - b.position)
}

export const projectsStore = {
  state: readonly(state),
  projects: computed(() => [...state.projects].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))),

  getProject: (id: string) => state.projects.find((p) => p.id === id),
  getSections: (id: string): Section[] => state.sections[id] ?? [],
  totalWords: (id: string) => (state.sections[id] ?? []).reduce((sum, s) => sum + s.wordCount, 0),

  // ---- loading ----
  async loadProjects() {
    state.projects = await service.listProjects()
    state.loaded = true
  },

  async refreshProject(id: string) {
    upsert(await service.getProject(id))
  },

  async loadSections(id: string) {
    state.sections[id] = await service.listSections(id)
  },

  /** Makes sure the project is in the store. Returns false when it doesn't exist (404). */
  async ensureProject(id: string): Promise<boolean> {
    if (state.projects.some((p) => p.id === id)) return true
    try {
      await this.refreshProject(id)
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return false
      throw e
    }
  },

  // ---- projects ----
  async createProject(form: Parameters<typeof service.createProject>[0]): Promise<Project> {
    const project = await service.createProject(form)
    state.sections[project.id] = []
    upsert(project)
    return project
  },

  async resumeGeneration(id: string) {
    upsert(await service.resumeGeneration(id))
  },

  async deleteProject(id: string) {
    await service.deleteProject(id)
    state.projects = state.projects.filter((p) => p.id !== id)
    delete state.sections[id]
  },

  async updateSettings(id: string, voiceModel: string, wordsPerMinute: number) {
    upsert(await service.updateSettings(id, voiceModel, wordsPerMinute))
    await this.loadSections(id)
  },

  // ---- sections ----
  // Editing a section only marks its video out of date; videos are built by the buttons (buildSectionVideos / convertIntoVideo).
  async updateSectionText(id: string, position: number, text: string) {
    setSection(id, await service.updateSectionText(id, position, text))
  },

  async rewriteSection(id: string, position: number, instruction: string) {
    setSection(id, await service.rewriteSection(id, position, instruction))
  },

  async setSectionImage(id: string, position: number, file: File) {
    setSection(id, await service.setSectionImage(id, position, file))
    await this.refreshProject(id)
  },

  async removeSectionImage(id: string, position: number) {
    setSection(id, await service.removeSectionImage(id, position))
    await this.refreshProject(id)
  },

  async addSection(id: string, text: string, position?: number) {
    await service.addSection(id, text, position)
    await this.loadSections(id) // positions of later sections shifted
    await this.refreshProject(id)
  },

  async removeSection(id: string, position: number) {
    await service.deleteSection(id, position)
    await this.loadSections(id)
    await this.refreshProject(id)
  },

  async rerenderSection(id: string, position: number) {
    setSection(id, await service.rerenderSection(id, position))
  },

  // ---- videos ----
  async buildSectionVideos(id: string) {
    upsert(await service.buildSectionVideos(id))
  },

  async convertIntoVideo(id: string) {
    upsert(await service.convertIntoVideo(id))
  },

  async deleteFinalVideo(id: string) {
    await service.deleteFinalVideo(id)
    await this.refreshProject(id)
  },
}
