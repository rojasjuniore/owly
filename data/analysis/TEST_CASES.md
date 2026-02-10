# Test Cases para Owly Agent

Basados en el documento LendingSpot_All_Programs_Categorized.docx y el análisis del chat.

---

## Caso 1: ✅ CALIFICA EN ALGUNOS PRODUCTOS

### Escenario
```
Borrower: María González
- Estado: Florida
- Ocupación: Self-employed (3 años)
- FICO Score: 720
- Income: $12,000/mes en bank statements (24 meses)
- Propósito: Purchase
- Propiedad: Single Family Home
- Precio: $450,000
- Down Payment: 20% ($90,000)
- LTV: 80%
- Tipo de Income Documentation: Bank Statements
```

### Resultado Esperado
El borrower **CALIFICA** para:

| Programa | Lender Sugerido | Razón |
|----------|-----------------|-------|
| ✅ Bank Statement Loan | Acra Lending, AmWest | FICO 720 > min 660, LTV 80% ≤ max 80%, 24 meses BS |
| ✅ Full Doc (si tiene P&L) | Multiple | Con P&L de CPA calificaría también |
| ❌ FHA | N/A | FHA no acepta Bank Statement como income |
| ❌ Conventional | N/A | Requiere tax returns tradicionales |

### Pregunta de Prueba
> "Tengo una clienta self-employed con 720 FICO que quiere comprar casa de $450k con 20% down. Tiene 24 meses de bank statements mostrando $12k/mes. ¿Qué opciones tengo?"

---

## Caso 2: ❌ NO CALIFICA EN NINGÚN PRODUCTO

### Escenario
```
Borrower: Carlos Mendez
- Estado: Florida  
- Ocupación: Self-employed (6 meses)
- FICO Score: 580
- Income: $8,000/mes (solo 6 meses de bank statements)
- Propósito: Purchase
- Propiedad: Condo (Non-Warrantable)
- Precio: $350,000
- Down Payment: 5% ($17,500)
- LTV: 95%
- Credit History: 2 mortgage lates en los últimos 12 meses
```

### Resultado Esperado
El borrower **NO CALIFICA** para ningún producto:

| Programa | Razón de Rechazo |
|----------|------------------|
| ❌ Bank Statement | FICO 580 < min 620, solo 6 meses (requiere 12-24), LTV 95% > max 85% |
| ❌ FHA | Mortgage lates recientes, non-warrantable condo |
| ❌ Conventional | FICO muy bajo, LTV muy alto para non-warrantable |
| ❌ DSCR | No es investment property |
| ❌ Non-QM | FICO demasiado bajo, historial crediticio pobre |

### Pregunta de Prueba
> "Tengo un cliente self-employed de 6 meses con score de 580 que quiere comprar un condo non-warrantable de $350k con solo 5% down. Tiene 2 mortgage lates recientes. ¿Hay algo que pueda hacer?"

### Respuesta Esperada
"Lamentablemente, este borrower no califica actualmente para ninguno de nuestros productos debido a:
1. FICO 580 está por debajo del mínimo (generalmente 620-660)
2. Solo 6 meses self-employed (mínimo 12-24 meses)
3. LTV 95% excede límites para non-warrantable condos
4. Mortgage lates recientes descalifican para la mayoría de programas

**Recomendación:** El cliente necesita trabajar en su crédito y tener más tiempo de self-employment antes de aplicar."

---

## Caso 3: ✅ CALIFICA EN MÚLTIPLES PRODUCTOS

### Escenario
```
Borrower: Robert Smith
- Estado: Florida
- Ocupación: W-2 Employee + Side Business (1099)
- FICO Score: 780
- W-2 Income: $85,000/año
- 1099 Income: $45,000/año (2 años documentados)
- Propósito: Investment Property Purchase
- Propiedad: Single Family Home
- Precio: $400,000
- Down Payment: 25% ($100,000)
- LTV: 75%
- Rental Income Proyectado: $3,200/mes
- DSCR: 1.25 (property cash flows positive)
```

### Resultado Esperado
El borrower **CALIFICA** para múltiples productos:

| Programa | Elegibilidad | Ventajas | Desventajas |
|----------|-------------|----------|-------------|
| ✅ Conventional (Full Doc) | Sí | Mejor rate, puede usar ambos incomes | Requiere tax returns completos |
| ✅ DSCR | Sí | No necesita income docs, cierre rápido | Rate más alto |
| ✅ Bank Statement | Sí | Usa 1099 income fácilmente | Rate medio |
| ✅ 1099 Income Loan | Sí | Diseñado para este perfil | Menos lenders disponibles |

### Pregunta de Prueba
> "Tengo un cliente con W-2 de $85k y 1099 de $45k adicionales, FICO 780, quiere comprar investment property de $400k con 25% down. La propiedad va a generar $3,200/mes de renta. ¿Cuál es la mejor opción?"

### Respuesta Esperada (Ejemplo)
"Excelente perfil! Este borrower califica para múltiples productos:

**Opción 1: Conventional Full Doc** ⭐ RECOMENDADO si tiene tax returns limpios
- Mejor rate (aproximadamente 6.5-7%)
- Puede combinar W-2 + 1099 income
- Requiere 2 años de tax returns

**Opción 2: DSCR Loan** ⭐ RECOMENDADO si quiere proceso rápido
- No requiere income documentation
- DSCR 1.25 es excelente (mínimo usualmente 1.0)
- Cierre en 15-21 días
- Rate aproximado 7.5-8%

**Opción 3: 1099 Income Loan**
- Usa solo el 1099 income
- Útil si tax returns muestran deducciones altas

**Mi recomendación:** Si el cliente quiere el mejor rate y tiene tax returns que reflejan buen income, ir con Conventional. Si prioriza velocidad o tiene deducciones agresivas en taxes, ir con DSCR."

---

## Métricas de Evaluación

Para cada caso, el agente debe:

| Métrica | Target |
|---------|--------|
| Identificar productos elegibles | 100% accuracy |
| Identificar productos NO elegibles | 100% accuracy |  
| Dar razón específica de elegibilidad/rechazo | Citar guideline específico |
| Tiempo de respuesta | < 20 segundos |
| Confidence Score | > 85% para casos claros |

---

## Cómo Usar Estos Test Cases

1. Ingresar cada pregunta de prueba en el chat de Owly
2. Verificar que la respuesta coincida con el resultado esperado
3. Confirmar que se citan las fuentes correctas (PDF guidelines)
4. Medir tiempo de respuesta
5. Evaluar confidence score reportado

---

*Generado: 2026-02-08*
*Fuentes: LendingSpot_All_Programs_Categorized.docx, _chat.txt*
