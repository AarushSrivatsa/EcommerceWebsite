# Research, section quality, and cinematic storyboard workflow

## Generation pipeline

1. **Research planning** — LangGraph asks the manager model for focused searches covering core facts, context, and a counterpoint or primary source.
2. **Source discovery** — Tavily retrieves web snippets. The snippets are split into overlapping passages, embedded with the existing BGE-small FastEmbed model, and stored in Postgres/pgvector under the project.
3. **Section retrieval** — each section brief retrieves the most semantically relevant passages from that project's research index.
4. **Relevance grading** — the model checks whether the retrieved passages support the section. If not, it rewrites the search query, searches again, and re-ranks once.
5. **Grounded writing and review** — the writer receives the selected excerpts. A separate check scores factual support and lists unsupported claims. Low support triggers a rewrite attempt; the score and feedback are retained with the section.
6. **Cinematic planning** — the script is split into narration paragraphs and the planner writes one visual beat per paragraph, with a visual subject, optional short on-screen text, and a camera cue.
7. **Timed rendering** — the voice engine measures the audio duration of every paragraph. Each beat image is shown for the duration of its matching paragraph. A section-wide image is used as the fallback for beats without a custom image.

The section editor exposes research links and the visual plan. Upload a different image on each beat to create a multi-visual section; rebuilding that section applies the image changes. A beat image takes precedence over the shared section image.

## Similarity setting

- **Range:** 60–100%.
- **Metric:** sentence/section embeddings are compared with cosine similarity. The displayed percentage is the nearest earlier section's cosine similarity, clamped to 0–100%.
- **Default:** 88% for facts and 92% for stories. In Auto format, the matching default is selected after the generator identifies the format.
- **Behavior:** a draft at or above the threshold is sent back for a rewrite. The current generator makes up to three rewrite attempts; if it still exceeds the limit, it is saved with its score and applied threshold visible on the section.
- **Where to edit:** set it during project creation, or in Project Settings for future generation and AI rewrites. It cannot be changed while the project is actively generating. Changing it does not invalidate existing rendered videos.

This is a repetition-control heuristic, not an exact text-match or plagiarism measurement. The threshold and measured value are retained separately so the decision is inspectable.

## Configuration

`TAVILY_API_KEY` is optional. Without it the client uses Tavily's rate-limited keyless search mode; configure a key in the deployment environment for more reliable production research. The script generation flow degrades gracefully if web search or indexing is unavailable and clearly marks the project as research-unavailable.

## Reliability and limitations

- Research retrieval is project-scoped; one project's source passages are not searched for another project.
- Search result snippets are evidence inputs, not complete article archives. Important claims should still be checked against the linked source.
- Grounding scores are model assessments, not calibrated probabilities or a guarantee of factual accuracy.
- The renderer currently cuts between beat images on measured paragraph boundaries. The camera cue is storyboard guidance; it is not yet a generated camera-motion effect.
- AI-generated imagery, where used, should be treated as illustration rather than documentary evidence.
