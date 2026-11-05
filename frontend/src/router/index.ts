import { createRouter, createWebHistory } from 'vue-router'
import { useToast } from '@/lib/toast'
import { errorMessage } from '@/services/api'
import { projectsStore } from '@/stores/projectsStore'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', name: 'projects', component: () => import('@/views/ProjectsView.vue'), meta: { title: 'Projects' } },
    { path: '/new', name: 'new', component: () => import('@/views/NewProjectView.vue'), meta: { title: 'New project' } },
    { path: '/projects/:id', name: 'project', component: () => import('@/views/ProjectDetailView.vue'), meta: { title: 'Project' } },
    { path: '/projects/:id/review', name: 'review', component: () => import('@/views/StoryReviewView.vue'), meta: { title: 'Review story' } },
    { path: '/projects/:id/progress', name: 'progress', component: () => import('@/views/GenerationProgressView.vue'), meta: { title: 'Generation progress' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// Project routes: make sure the project exists on the backend before showing the page.
router.beforeEach(async (to) => {
  const id = to.params.id
  if (typeof id !== 'string') return
  try {
    if (!(await projectsStore.ensureProject(id))) return { name: 'projects' }
  } catch (e) {
    useToast().push(errorMessage(e), 'error', 6000)
    return { name: 'projects' }
  }
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? 'Script to Video'} · Script to Video`
})

export default router
