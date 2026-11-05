// Static UI options (not backend data).
import type { Voice } from '@/types'

// Kokoro voice ids understood by the backend's `voice_model` field.
export const voices: Voice[] = [
  { id: 'af_heart', label: 'Heart', accent: 'American · Female' },
  { id: 'af_bella', label: 'Bella', accent: 'American · Female' },
  { id: 'am_michael', label: 'Michael', accent: 'American · Male' },
  { id: 'bf_emma', label: 'Emma', accent: 'British · Female' },
  { id: 'bm_george', label: 'George', accent: 'British · Male' },
]

export const examplePrompts: string[] = [
  'Interesting facts about octopuses',
  'A short story about a lighthouse keeper who finds a message in a bottle',
  'The history of the printing press in five minutes',
  'A bedtime story about a dragon who is afraid of fire',
]
