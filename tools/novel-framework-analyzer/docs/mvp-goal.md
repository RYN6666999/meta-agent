# MVP Goal

## Product statement

Novel Framework Analyzer is a system for splitting a Chinese novel into scenes and producing structured "局心欲變" framework cards for querying, reviewing, and comparison.

The system helps analysts answer deep questions about character strategy, negotiation dynamics, and psychological turning points — grounded in direct textual evidence.

---

## Core question

> Which negotiation scenes best represent Ning Fan's strength, and how does he regain control from a weaker position?

---

## MVP must answer

1. **Which scenes are Ning Fan's strongest negotiation scenes?**
   - Ranked by `is_negotiation_scene` + `negotiation_pattern_tags` + `confidence_score`
   - With supporting raw quotes from the source text

2. **In which scenes does Ning Fan show clear psychological or strategic turning points?**
   - `mind_shift_type` = strategy / identity / values
   - `change_intensity` ≥ 3
   - With before/after 局 description

3. **For a given chapter, what are the key scenes and their 局 / 心 / 欲 / 變 structure?**
   - Query by `chapter_index`
   - Return full `SceneFrameworkCard` per scene

---

## MVP scope

- Upload `.txt` novel
- Chapter split (regex-based)
- Scene split (boundary detection)
- Generate `SceneFrameworkCard` via LLM
- Mark `is_negotiation_scene` + `negotiation_pattern_tags`
- Query by character / chapter / negotiation flag / tags
- Manual review and correction (with diff snapshot)
- Mark golden examples for future fine-tuning

---

## Not in MVP

These features are deferred until after first full-book end-to-end validation:

| Feature | Reason deferred |
|---------|-----------------|
| MCP tools | Nice-to-have; not required for core analysis workflow |
| Multi-model routing (SmartRouter) | Cost optimization; not a correctness blocker |
| Ollama / local model path | Infrastructure complexity; OpenRouter is sufficient |
| Vector search (ChromaDB) | Keyword + SQL filter is enough at MVP scale |
| RAGFlow | Phase 3 capability |
| Dify workflow orchestration | Phase 3 capability |
| Nonfiction book support | Separate use case; different schema requirements |
| Cost dashboard | Useful but not blocking core analysis |
| Large analytics dashboard | Derivative of core data; revisit after data is stable |
| Character arc chart (advanced) | MVP only needs raw list view |
| Progress heatmap | Nice-to-have UI feature |
| Bookshelf management | Single-book workflow is sufficient for MVP |

---

## Success criteria

A successful MVP delivers all of the following:

1. **End-to-end pipeline works**: one full novel can be uploaded, split, analyzed, reviewed, and queried without manual intervention in the pipeline
2. **Negotiation surface is usable**: the system can surface the top 5–10 Ning Fan negotiation scenes with supporting quotes and `negotiation_pattern_tags`
3. **Framework cards are trustworthy**: `confidence_score` ≥ 0.7 in ≥ 70% of analyzed scenes
4. **Human correction works**: a reviewer can open any scene card in the frontend, correct the AI judgment, and the diff is recorded correctly
5. **Query is fast enough**: scene list filters by character + chapter + negotiation respond in < 1s on a full novel (500+ scenes)

---

## Non-goals (永遠不做)

- This is NOT a novel recommendation engine
- This is NOT a general-purpose chatbot over books
- This is NOT trying to replace human literary analysis
- This is NOT a social reading platform

---

## Review checkpoint

After MVP passes all success criteria above, revisit the deferred features table and prioritize Phase 2 items based on actual usage friction observed during full-book validation.
