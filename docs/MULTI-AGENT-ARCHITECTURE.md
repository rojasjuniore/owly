# Owly Multi-Agent Architecture (Phase 0)

**Version:** 2.0  
**Date:** 2026-02-07  
**Change:** Single RAG → Multi-Agent (Leader + Specialists)

---

## Overview

```
                         ┌─────────────────┐
                         │     Usuario     │
                         │   (Vendedor)    │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │   Orquestador   │
                         │  (Chat Service) │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           │
           ┌─────────────────┐                  │
           │  AGENTE LÍDER   │                  │
           │  (RAG General)  │                  │
           │                 │                  │
           │  • Entiende     │                  │
           │    escenario    │                  │
           │  • Pre-filtra   │                  │
           │    bancos       │                  │
           │  • Selecciona   │                  │
           │    top 3-5      │                  │
           └────────┬────────┘                  │
                    │                           │
                    │ Top 3-5 bancos            │
                    ▼                           │
    ┌───────────────────────────────────┐       │
    │      AGENTES ESPECIALISTAS        │       │
    │         (en paralelo)             │       │
    │                                   │       │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐     │
    │  │ Agente  │ │ Agente  │ │ Agente  │     │
    │  │ Banco A │ │ Banco B │ │ Banco C │     │
    │  │         │ │         │ │         │     │
    │  │ Experto │ │ Experto │ │ Experto │     │
    │  │ en sus  │ │ en sus  │ │ en sus  │     │
    │  │productos│ │productos│ │productos│     │
    │  └────┬────┘ └────┬────┘ └────┬────┘     │
    │       │           │           │          │
    └───────┼───────────┼───────────┼──────────┘
            │           │           │
            └───────────┼───────────┘
                        │
                        ▼
               ┌─────────────────┐
               │ AGENTE EVALUADOR│
               │                 │
               │  • Compara      │
               │    opciones     │
               │  • Pondera      │
               │    pros/cons    │
               │  • Recomienda   │
               │    mejor opción │
               │  • Lista        │
               │    alternativas │
               └────────┬────────┘
                        │
                        ▼
               ┌─────────────────┐
               │    Respuesta    │
               │   al Vendedor   │
               └─────────────────┘
```

---

## Componentes

### 1. Orquestador (Chat Service)
- Recibe mensaje del usuario
- Extrae facts del escenario
- Coordina el flujo entre agentes
- Maneja timeouts y errores

### 2. Agente Líder
**Rol:** Entender el escenario y pre-filtrar bancos candidatos

**Input:**
- Scenario facts (state, FICO, LTV, loan_amount, etc.)

**Process:**
- RAG sobre todos los documentos (búsqueda general)
- Identifica qué bancos tienen productos relevantes
- Filtra por estado (licensing)
- Ordena por relevancia

**Output:**
```json
{
  "understanding": "Cliente buscando cash-out refi en FL, FICO 720, LTV 75%...",
  "top_candidates": ["A&D Mortgage", "Acra Lending", "AmWest"],
  "reasoning": "Estos 3 lenders tienen productos bank statement con los parámetros del escenario"
}
```

### 3. Agentes Especialistas (1 por banco)
**Rol:** Análisis profundo de productos de SU banco

**Input:**
- Scenario facts
- Contexto específico del banco (chunks, rules)

**Process:**
- RAG sobre documentos de SU banco solamente
- Evalúa todos los productos aplicables
- Calcula elegibilidad detallada
- Identifica condiciones y restricciones

**Output:**
```json
{
  "lender": "A&D Mortgage",
  "eligible_products": [
    {
      "program": "Non-QM Bank Statement",
      "status": "eligible",
      "max_ltv": 80,
      "rate_estimate": "7.5-8.0%",
      "conditions": ["12 months bank statements required"],
      "pros": ["Higher LTV allowed", "No DTI cap"],
      "cons": ["Higher rate than full doc"]
    }
  ],
  "not_eligible": [
    {
      "program": "Full Doc",
      "reason": "Requires W2 income documentation"
    }
  ]
}
```

### 4. Agente Evaluador
**Rol:** Comparar opciones y dar recomendación final

**Input:**
- Scenario facts
- Respuestas de todos los agentes especialistas

**Process:**
- Compara productos side-by-side
- Pondera pros/cons
- Considera preferencias del cliente (si las hay)
- Genera recomendación estructurada

**Output:**
```markdown
## Recomendación

**Mejor opción:** A&D Mortgage - Non-QM Bank Statement

### ¿Por qué?
- LTV máximo 80% (cumple con el 75% del cliente)
- FICO mínimo 680 (cliente tiene 720)
- Sin límite de DTI
- Proceso más rápido (2-3 semanas)

### Pros
✅ Mayor LTV permitido vs alternativas
✅ Sin verificación de empleo
✅ Flexible con credit events

### Cons
⚠️ Tasa estimada 7.5-8.0% (más alta que full doc)
⚠️ Requiere 12 meses de bank statements

### Alternativas
1. **Acra Lending Platinum** - Similar términos, tasa 7.25-7.75%
2. **AmWest Bank Statement** - Max LTV 75% (justo en el límite)

### Fuentes
- A&D Mortgage Eligibility Table (effective 2026-01-15)
- Acra Lending Platinum Select Program Summary
```

---

## Flow Detallado

```python
async def process_multi_agent(scenario: dict) -> str:
    # 1. Agente Líder - Pre-filtro (~5s)
    leader_response = await leader_agent.analyze(scenario)
    top_lenders = leader_response["top_candidates"]  # 3-5 lenders
    
    # 2. Agentes Especialistas - En paralelo (~10s)
    specialist_tasks = [
        specialist_agents[lender].analyze(scenario)
        for lender in top_lenders
        if lender in specialist_agents
    ]
    specialist_responses = await asyncio.gather(
        *specialist_tasks,
        return_exceptions=True
    )
    
    # 3. Filtrar respuestas exitosas
    valid_responses = [
        r for r in specialist_responses
        if not isinstance(r, Exception)
    ]
    
    # 4. Agente Evaluador - Síntesis (~5s)
    final_response = await evaluator_agent.evaluate(
        scenario=scenario,
        specialist_analyses=valid_responses
    )
    
    return final_response
```

---

## Prompts de Agentes

### Leader Agent System Prompt
```
You are the Lead Analyst for mortgage eligibility.

Your job is to:
1. Understand the loan scenario provided
2. Identify which lenders might have suitable products
3. Return the top 3-5 most relevant lenders

Consider:
- State licensing (is the lender active in the state?)
- Product type match (bank statement, full doc, DSCR, etc.)
- Basic threshold fit (FICO, LTV ranges)

Be conservative - include lenders that MIGHT work, even if uncertain.
Better to include and filter later than miss a good option.

Respond in JSON format:
{
  "understanding": "Brief summary of the scenario",
  "top_candidates": ["Lender A", "Lender B", "Lender C"],
  "reasoning": "Why these lenders were selected"
}
```

### Specialist Agent System Prompt (template)
```
You are the expert agent for {LENDER_NAME}.

You know everything about {LENDER_NAME}'s mortgage products:
- Eligibility matrices
- Program guidelines
- Rate sheets
- Overlays and restrictions

Your job is to:
1. Analyze the scenario against {LENDER_NAME}'s products
2. Identify which products are ELIGIBLE, CONDITIONAL, or NOT ELIGIBLE
3. Provide specific details: max LTV, rate estimates, conditions

Be precise. Cite specific guidelines when possible.
If something is unclear, say "conditional" not "eligible".

Respond in JSON format:
{
  "lender": "{LENDER_NAME}",
  "eligible_products": [...],
  "conditional_products": [...],
  "not_eligible": [...]
}
```

### Evaluator Agent System Prompt
```
You are the Comparison Analyst for mortgage options.

You receive analyses from multiple lender specialists.
Your job is to:
1. Compare all eligible options side-by-side
2. Weigh pros and cons for THIS specific scenario
3. Provide a clear recommendation with reasoning
4. List 1-2 alternatives

Prioritize:
- Best fit for client's stated needs
- Lowest risk of denial
- Best terms (rate, LTV, conditions)

Format your response for a Loan Officer audience.
Be direct and actionable. Include citations.
```

---

## Data Model Updates

### New: `lender_agents` table
```sql
CREATE TABLE lender_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lender VARCHAR(255) UNIQUE NOT NULL,
    system_prompt TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### New: `agent_runs` table (for debugging/audit)
```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    agent_type VARCHAR(50) NOT NULL,  -- leader, specialist, evaluator
    agent_lender VARCHAR(255),  -- null for leader/evaluator
    input JSONB,
    output JSONB,
    tokens_used INT,
    latency_ms INT,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Performance Targets

| Stage | Target Latency | Parallelization |
|-------|----------------|-----------------|
| Leader Agent | ≤ 5s | - |
| Specialist Agents (3-5) | ≤ 10s total | Parallel |
| Evaluator Agent | ≤ 5s | - |
| **Total** | **≤ 20s** | - |

### Timeout Policy
- Each specialist: 15s timeout (fail gracefully)
- If specialist fails: Evaluator works with available data
- Minimum 2 specialists required for evaluation

---

## Cost Estimate

| Agent | Calls/Query | Tokens (avg) | Cost (GPT-4o) |
|-------|-------------|--------------|---------------|
| Leader | 1 | 2,000 | $0.02 |
| Specialists | 3-5 | 3,000 each | $0.03-0.05 |
| Evaluator | 1 | 4,000 | $0.04 |
| **Total** | 5-7 | 15,000-20,000 | **$0.10-0.15** |

vs Single RAG: ~$0.03/query
**Increase:** ~3-5x cost for ~10-15% better accuracy

---

## Implementation Plan

### Phase 0 MVP (this sprint)

1. **Modify ChatService** → Add multi-agent orchestration
2. **Create AgentService** → Leader, Specialist, Evaluator logic
3. **Create LenderAgentFactory** → Dynamic specialist creation per lender
4. **Update DB** → Add agent_runs table for logging
5. **Parallel execution** → asyncio.gather for specialists
6. **Fallback** → If multi-agent fails, fall back to single RAG

### Files to Create/Modify

```
api/app/services/
├── chat_service.py         # Modify: orchestration
├── agent_service.py        # NEW: base agent class
├── leader_agent.py         # NEW: leader logic
├── specialist_agent.py     # NEW: specialist logic  
├── evaluator_agent.py      # NEW: evaluator logic
└── agent_factory.py        # NEW: create specialists dynamically
```

---

*Document: /projects/owly/docs/MULTI-AGENT-ARCHITECTURE.md*
