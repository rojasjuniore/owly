# Análisis del Chat de LendingSpot - Preguntas de Loan Officers

## Resumen Ejecutivo

Del análisis del chat de WhatsApp, identifiqué **las preguntas más frecuentes que hacen los Loan Officers al momento de procesar un borrower**. Estas preguntas se centran en encontrar el lender correcto para escenarios específicos.

---

## Categorías de Preguntas Identificadas

### 1. 🏦 Selección de Lender por Tipo de Producto (MÁS FRECUENTE)
**Ejemplos:**
- "Which lender allows no escrow on a 15% down payment on bank statement loan?"
- "Who is the best FHA lender for a low score manual underwrite?"
- "Which of these lenders is best for a bank statement loan?"
- "Does anyone know which lender does DSCR 80LTV short term rental?"
- "Who's our go to for 100LTV Doctor Programs?"
- "Who is a good lender for VA loans?"

**Frecuencia:** ~35% de las preguntas

---

### 2. 📊 Elegibilidad por Perfil del Borrower
**Ejemplos:**
- "Does any DSCR lender do 5 units?"
- "Do we have any lenders that will use a P&L to purchase a warehouse?"
- "Are there any lenders that would accept recent mortgage lates?"
- "Does anyone know of a lender that does P&L without bank statement?"

**Frecuencia:** ~25% de las preguntas

---

### 3. 💰 Cálculo de Income/Eligibility
**Ejemplos:**
- "If income increase from 23-24 is very high (40k to 150k) - is this ok if I average over 24 months?"
- "How do I calculate variable income for a pilot?"
- "Can I combine W2 and bank statement for 1 borrower?"
- "Which lenders can calculate Airbnb income for me?"

**Frecuencia:** ~20% de las preguntas

---

### 4. 📋 Requisitos Específicos de Guidelines
**Ejemplos:**
- "How many IRS installment agreement payments need to be made for FHA?"
- "Does VA have an anti flip rule like FHA?"
- "Do all lenders require P&L to be done by CPA or enrolled agent?"

**Frecuencia:** ~15% de las preguntas

---

### 5. 🏠 Property-Specific Questions
**Ejemplos:**
- "Should I send a condo on the unavailable list to TLS?"
- "Can we do cashout on a lot in Wynwood that's free and clear?"
- "Anyone know who does barn properties?"

**Frecuencia:** ~5% de las preguntas

---

## Top 10 Preguntas Más Recurrentes (Patrones)

| # | Patrón de Pregunta | Productos Mencionados |
|---|--------------------|-----------------------|
| 1 | "Which lender is best for [product type] with [specific condition]?" | Bank Statement, DSCR, FHA, VA |
| 2 | "Does any lender do [unusual scenario]?" | 5+ units DSCR, P&L without bank statement |
| 3 | "Who can do [LTV]% on [product]?" | 80% DSCR, 85% Bank Statement, 100% Doctor |
| 4 | "What's the min FICO for [product] with [lender]?" | Non-QM, DSCR, Jumbo |
| 5 | "Can I qualify borrower with [income type]?" | P&L, 1099, Bank Statement, VOE |
| 6 | "Who is fastest for [product]?" | DSCR, Fix-and-Flip, Bridge |
| 7 | "Does [lender] allow [condition]?" | No escrow, waived reserves |
| 8 | "How do I document [income situation]?" | Variable income, self-employed |
| 9 | "Is [property type] eligible for [product]?" | Condo, Condotel, 5+ units |
| 10 | "What are the requirements for [special program]?" | Foreign National, ITIN, DPA |

---

## Conclusiones para el Agente Owly

El agente debe ser capaz de:

1. **Matching rápido**: Dado un perfil de borrower, identificar qué lenders/productos son elegibles
2. **Filtrado por restricciones**: Aplicar filtros como FICO mínimo, LTV máximo, tipo de income
3. **Comparación**: Recomendar el "mejor" lender basado en criterios (velocidad, pricing, flexibilidad)
4. **Edge cases**: Manejar escenarios poco comunes (5+ units, condotel, foreign national)
5. **Documentation guidance**: Explicar qué documentación se necesita para cada producto

---

## Próximos Pasos

Ver archivo `TEST_CASES.md` para los 3 casos de prueba generados.
