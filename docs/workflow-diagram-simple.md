# Vivian LLM SpecGen – Pipeline Workflow (Miro-optimiert)

Dieses vereinfachte Diagramm ist für den Import in **Miro** optimiert:
- Keine verschachtelten Subgraphs
- Klare lineare Struktur mit deutlichen Retry-Pfaden
- Kurze Labels für bessere Lesbarkeit

**Import in Miro:** `/` drücken → "Mermaid" → Code einfügen.

```mermaid
flowchart TD
    START([START]) --> SCENE["Phase 1: Scene Analysis\n(scene_analysis_agent)"]

    SCENE --> CONFIRM{User bestätigt\nScene?}
    CONFIRM -- "Nein → Feedback" --> SCENE
    CONFIRM -- Ja --> PLAN

    PLAN["Phase 2: Interaction Planning\n(interaction_planner_agent)"] --> PLAN_OK{Plan\ngültig?}
    PLAN_OK -- Nein --> FALLBACK["Fallback: alle Steps aktiv"]
    PLAN_OK -- Ja --> ACTIVE["active_steps ableiten"]
    FALLBACK --> DIRTY
    ACTIVE --> DIRTY

    DIRTY["dirty_steps bestimmen\n(beim 1. Attempt = alle)"] --> GEN_IE

    GEN_IE["Phase 3a: Interaction Elements\ngenerieren & validieren"] --> IE_OK{Namen\nvalide?}
    IE_OK -- Nein --> RETRY_EARLY
    IE_OK -- Ja --> GEN_VE

    GEN_VE["Phase 3b: Visualization Elements\ngenerieren & validieren"] --> VE_OK{Namen\nvalide?}
    VE_OK -- Nein --> RETRY_EARLY
    VE_OK -- Ja --> GEN_ST

    GEN_ST["Phase 3c: States\ngenerieren & Cross-Refs prüfen"] --> ST_OK{Refs\nvalide?}
    ST_OK -- Nein --> RETRY_EARLY
    ST_OK -- Ja --> GEN_TR

    GEN_TR["Phase 3d: Transitions\ngenerieren & Cross-Refs prüfen"] --> TR_OK{Refs\nvalide?}
    TR_OK -- Nein --> RETRY_EARLY
    TR_OK -- Ja --> REVIEW

    RETRY_EARLY["Retry-Scope bestimmen\n(expand_dirty_steps)"] --> ATT1{Attempts\nübrig?}
    ATT1 -- Ja --> DIRTY
    ATT1 -- Nein --> FAILED

    REVIEW["Phase 4: Consistency Review\n(consistency_reviewer_agent)"] --> CONS_OK{Semantisch\nkonsistent?}
    CONS_OK -- Nein --> RETRY_CONS["Retry-Scope bestimmen\n(map consistency errors)"] --> ATT2{Attempts\nübrig?}
    ATT2 -- Ja --> DIRTY
    ATT2 -- Nein --> FAILED
    CONS_OK -- Ja --> VALIDATE

    VALIDATE["Phase 5: Unity Validation\n(strukturelle Prüfung)"] --> VAL_OK{Validierung\nbestanden?}

    VAL_OK -- Ja --> PUBLISH["Phase 6: Publishing\n(Final Output schreiben)"] --> COMPLETED([COMPLETED])

    VAL_OK -- Nein --> FIXER["Fix-Plan erstellen\n(fixer_agent)"] --> RETRY_FIX["Retry-Scope bestimmen\n(map errors + expand downstream)"] --> ATT3{Attempts\nübrig?}
    ATT3 -- Ja --> DIRTY
    ATT3 -- Nein --> FAILED([FAILED])

    style START fill:#4CAF50,color:#fff
    style COMPLETED fill:#4CAF50,color:#fff
    style FAILED fill:#f44336,color:#fff
    style DIRTY fill:#FF9800,color:#fff
    style RETRY_EARLY fill:#FF5722,color:#fff
    style RETRY_CONS fill:#FF5722,color:#fff
    style RETRY_FIX fill:#FF5722,color:#fff
    style PUBLISH fill:#2196F3,color:#fff
    style SCENE fill:#7E57C2,color:#fff
    style PLAN fill:#7E57C2,color:#fff
    style GEN_IE fill:#26A69A,color:#fff
    style GEN_VE fill:#26A69A,color:#fff
    style GEN_ST fill:#26A69A,color:#fff
    style GEN_TR fill:#26A69A,color:#fff
    style REVIEW fill:#42A5F5,color:#fff
    style VALIDATE fill:#66BB6A,color:#fff
    style FIXER fill:#EF5350,color:#fff
```

## Farbkodierung

| Farbe | Bedeutung |
|-------|-----------|
| 🟣 Lila | Analyse & Planung |
| 🟢 Türkis | Spec-Generierung (Phase 3a–3d) |
| 🔵 Blau | Review & Validierung |
| 🟠 Orange | Dirty-Steps-Bestimmung (Retry-Einstieg) |
| 🔴 Rot | Fehler-Handling & Retry-Scope |
| 🟢 Grün | Start / Erfolg |

## Retry-Loops im Überblick

Das Diagramm zeigt **3 Retry-Einstiegspunkte**, die alle zum selben Punkt zurückführen:

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
  ┌── Retry 1: ElementNameMismatchError (Phase 3) ──┐           │
  ├── Retry 2: Consistency-Fehler (Phase 4) ─────────┼──→ dirty_steps ──→ Phase 3
  └── Retry 3: Validation-Fehler (Phase 5+6) ───────┘           │
                    │                                             │
                    └──── max_attempts erschöpft? ──→ FAILED ────┘
```

## Hinweis: Steps überspringen

In der vereinfachten Darstellung nicht explizit gezeigt:
Jeder Generierungs-Step (3a–3d) wird **nur ausgeführt wenn er `dirty` UND `active` ist**.
Nicht betroffene Steps werden übersprungen – das ist der Kern der effizienten Retry-Strategie.
