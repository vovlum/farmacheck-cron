# FarmaCheck — Contexto del Proyecto

## Idea Central

FarmaCheck es un SaaS de monitoreo y alertas de medicamentos en Argentina. Detecta cambios en el estado de comercialización del VNM (ANMAT/PAMI) y notifica a los usuarios suscritos vía Telegram. Se posiciona como **professional-first, citizen-accessible**: lanzar con la narrativa de herramienta para profesionales de la salud (farmacéuticos, médicos) con acceso gratuito al ciudadano como efecto secundario.

**Producto = Buscador + Monitor de cambios + Notificaciones**

---

## Problema que Resuelve

- En Argentina circulan medicamentos falsificados, vencidos, retirados del mercado o no registrados.
- ANMAT tiene los datos pero están dispersos en sistemas poco accesibles.
- Los retiros del mercado (ej. Clindamicina Klonal, Propofol HLB, Dopamina HLB en 2025) no llegan a tiempo a los profesionales de salud.
- No existe un sistema de alertas automáticas para cambios en el estado de comercialización de medicamentos.

---

## ICP (Ideal Customer Profile)

| Segmento | Universo estimado | Palanca de adopción |
|---|---|---|
| Farmacéuticos / directores técnicos | ~50.000 matriculados | Riesgo de matrícula si dispensan producto retirado |
| Médicos | ~135.000 activos | Verificación rápida en punto de prescripción |
| Obras sociales / prepagas | ~300 entidades | Auditoría de recetas y cobertura |
| Farmacias (institucional) | ~15.000 habilitadas | API de verificación integrada en su sistema |
| Pacientes crónicos / cuidadores | Millones | Acceso gratuito, alertas sobre sus medicamentos |

---

## Funcionalidades Core

1. **Buscador en tiempo real** — proxy al VNM de ANMAT/PAMI, resultados instantáneos
2. **Suscripción a medicamentos** — el usuario elige qué medicamentos monitorear
3. **Cron de monitoreo completo** — escanea todo el VNM diariamente y detecta cambios
4. **Notificaciones por Telegram** — alertas configurables por tipo de cambio y canal
5. **Dashboard con historial** — línea de tiempo de cambios, métricas por laboratorio y principio activo
6. **Canal público de alertas** — @FarmaCheckAlertas en Telegram como herramienta de adquisición gratuita

---

## Tipos de Alerta (Configurables por Usuario)

| Tipo | Descripción | Severidad |
|---|---|---|
| Retiro del mercado | Prohibición activa de comercialización | 🔴 Crítica |
| Discontinuación temporal | Problemas de producción, fecha estimada de retorno | 🟡 Media |
| Cambio de titularidad | Cambió el laboratorio titular | 🟡 Media |
| Cambio de estado | ACTIVO → INACTIVO o viceversa | 🔴 Crítica |
| Cambio de condición de expendio | Ej. venta libre → bajo receta | 🟡 Media |

---

## Modelo de Negocio

| Palanca | Target | Precio estimado |
|---|---|---|
| Plan premium profesional | Farmacéuticos, médicos | USD 10–20/mes |
| API B2B | Obras sociales, farmacias cadena | USD 500–1.500/mes |
| Datos agregados anonimizados | Laboratorios farmacéuticos | A negociar |

La versión gratuita incluye búsqueda básica y suscripción a hasta 5 medicamentos con alertas por Telegram.

---

## Arquitectura MVP

```
GitHub Actions (cron diario)
        │
        ├─ Scraper ZK → VNM completo (~15.000 presentaciones)
        ├─ Compara snapshot actual vs anterior (Supabase)
        ├─ Detecta deltas en campo "disponibilidad" y "estado"
        │
        ↓
Supabase (PostgreSQL)
        │
        ├─ tabla: medicamentos        (snapshot actual del VNM)
        ├─ tabla: snapshots           (historial diario de cambios)
        ├─ tabla: alertas             (eventos detectados)
        ├─ tabla: usuarios            (suscriptores)
        └─ tabla: suscripciones       (usuario ↔ medicamento)
        │
        ↓
Telegram Bot
        ├─ Canal público: @FarmaCheckAlertas (todos los retiros críticos)
        └─ Mensajes privados: alertas personalizadas por suscripción
```

---

## Fuentes de Datos

| Fuente | URL | Acceso | Frecuencia | Estado |
|---|---|---|---|---|
| VNM (ANMAT/PAMI) | `servicios.pami.org.ar/vademecum` | Scraping ZK | Diaria | ✅ Validado |
| Alertas/retiros | `boletinoficial.gob.ar` | Scraping | Diaria | 🟡 Pendiente |
| Precios PAMI | `datos.pami.org.ar` | CSV público | Mensual | 🟡 Pendiente |
| Farmacias CABA | `data.buenosaires.gob.ar` | API/CSV | Irregular | 🟡 V2 |
| Farmacias PBA | `catalogo.datos.gba.gob.ar` | CSV | Irregular | 🟡 V2 |
| TrazaMed SOAP | WS ANMAT/PAMI | CUFE/GLN | Tiempo real | 🔴 V3 |

---

## Validación Técnica Completada — VNM

### Mecanismo

El portal VNM usa **ZK Framework 7.0.3** (Java). Comunicación via POST a `/vademecum/zkau` con comandos ZK serializados. No hay API REST documentada pero el protocolo es completamente reproducible.

### Flujo de sesión

```
1. GET /vademecum/views/consultaPublica/listado.zul
   → Obtiene JSESSIONID (cookie) y DTID (desktop ID dinámico en el HTML)

2. POST /vademecum/zkau  (onChange — escribir en el campo de búsqueda)
   → Headers: Content-Type: application/x-www-form-urlencoded, zk-sid: N

3. POST /vademecum/zkau  (onClick — click en buscar)
   → Devuelve JSON con árbol de componentes ZK con los resultados

4. GET /vademecum/views/consultaPublica/presentacion.zul
   → Devuelve detalle completo del medicamento seleccionado
```

### Mapa de componentes confirmado

| Campo | UUID | Notas |
|---|---|---|
| Nombre comercial / genérico | `zk_comp_34` | mín. 3 chars, búsqueda substring |
| Nombre genérico (campo secundario) | `zk_comp_28` | comportamiento distinto, menos resultados |
| GTIN / código de barras | `zk_comp_73` | mín. 6 chars, max 14 |
| Nº certificado | `zk_comp_67` | max 10 chars |
| Buscar | `zk_comp_80` | — |
| Limpiar | `zk_comp_81` | — |

### Layout de respuesta (stride 20, confirmado)

```
zk_comp_BASE+0   → Nº certificado
zk_comp_BASE+2   → Laboratorio
zk_comp_BASE+4   → Nombre comercial   ← campo clave
zk_comp_BASE+6   → Forma farmacéutica
zk_comp_BASE+8   → Presentación
zk_comp_BASE+10  → GTIN
zk_comp_BASE+12  → Genérico (principio activo + concentración)
zk_comp_BASE+14  → Botón Ver Detalles
```

### Comportamiento de búsqueda — hallazgo crítico

El buscador hace **búsqueda substring**, no por prefijo. "AMO" devuelve PARACETAMOL (contiene "amo") además de AMOXICILINA. Esto implica:

- El scraping por trigramas/tetragramas aleatorios **no garantiza cobertura completa**
- El cron de monitoreo debe operar sobre una lista de medicamentos conocidos, no por exploración ciega
- La búsqueda live (proxy en tiempo real) es el método correcto para el buscador del producto

### Casos de prueba ejecutados

| Búsqueda | Tipo | Resultado |
|---|---|---|
| GTIN `07795333007682` | Por código | TOBRALER — ACTIVO ✅ |
| "IBUPIRAC" | Por nombre comercial | 3 variantes ✅ |
| "CLINDAMICINA KLONAL" | Por nombre comercial | Cert. 43852 — PROHIBIDA lote I2501 ✅ |
| "OZEMPIC" | Por nombre comercial | Sin resultados (nunca registrado en VNM) ✅ |

### Alerta activa confirmada

```
Disponibilidad en el Mercado:
"Prohibida la comercialización y distribución en todo el territorio
nacional del producto: CLINDAMICINA KLONAL / CLINDAMICINA (COMO FOSFATO),
concentración 600 mg/4 ml, inyectable para perfusión, 100 frascos ampolla.
Aplica para el lote I2501 con fecha de vencimiento en 01/2027"
```
Disposición ANMAT 7695/2025 — partículas en suspensión detectadas.

---

## Plan de Validación — 30 Días

### Objetivo

Antes de construir el producto completo, validar tres hipótesis críticas con un cron mínimo:

| Hipótesis | Cómo validar |
|---|---|
| El VNM cambia con frecuencia suficiente para justificar alertas | Medir cuántos cambios de `disponibilidad` y `estado` ocurren en 30 días |
| ANMAT no bloquea el scraping diario | Correr el cron 30 días seguidos sin interrupciones |
| El intervalo correcto de polling es diario | Comparar snapshots para detectar si hay cambios intra-día |

### Infraestructura del cron de testeo

```
GitHub Actions  →  Supabase  →  Telegram (canal privado de testeo)
```

Todo gratuito:
- GitHub Actions: 2.000 min/mes gratis (el cron usa ~120 min/día)
- Supabase: PostgreSQL gratuito hasta 500MB
- Telegram Bot: sin costo ni límites relevantes

### Lista semilla para monitoreo inicial

Empezar con ~200 medicamentos de alto consumo y casos conocidos:

- Medicamentos con retiros recientes confirmados (Clindamicina Klonal, Propofol HLB, Dopamina HLB)
- Top 50 medicamentos más dispensados en farmacias argentinas
- Medicamentos de enfermedades crónicas (hipertensión, diabetes, tiroides)
- Algunos controles que nunca deberían cambiar (para detectar falsos positivos)

### Métricas a registrar en 30 días

1. **Frecuencia de cambios** — cuántos eventos por semana en promedio
2. **Tipo de cambios** — retiros vs discontinuaciones vs cambios de titularidad
3. **Distribución por laboratorio** — qué laboratorios generan más alertas
4. **Estabilidad del scraping** — tasa de éxito de los requests al VNM
5. **Latencia de detección** — cuánto tarda ANMAT en reflejar un cambio en el VNM vs la publicación en el Boletín Oficial

### Estructura de tablas Supabase (mínima para el cron de testeo)

```sql
-- Medicamentos monitoreados
CREATE TABLE medicamentos (
    certificado     TEXT PRIMARY KEY,
    nombre_comercial TEXT,
    laboratorio     TEXT,
    generico        TEXT,
    gtin            TEXT,
    estado          TEXT,
    condicion_expendio TEXT,
    disponibilidad  TEXT,   -- campo clave de alertas
    retiro_count    INTEGER,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de cambios detectados
CREATE TABLE alertas (
    id              BIGSERIAL PRIMARY KEY,
    certificado     TEXT,
    nombre_comercial TEXT,
    campo           TEXT,    -- 'disponibilidad', 'estado', etc.
    valor_anterior  TEXT,
    valor_nuevo     TEXT,
    detectado_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Decisiones de Producto Tomadas

| Decisión | Justificación |
|---|---|
| Notificaciones por Telegram (no WhatsApp) | WhatsApp API requiere verificación de negocio y es paga. Telegram es gratuito, sin fricción, con API REST simple. |
| Canal público @FarmaCheckAlertas | Growth hack gratuito — cualquier profesional se suscribe sin registrarse |
| Búsqueda live (proxy al VNM) | El scraping masivo no garantiza cobertura completa por el límite de 10 resultados y búsqueda substring del VNM |
| Cron de monitoreo sobre lista conocida | Más eficiente y confiable que exploración ciega del catálogo |
| Infraestructura gratuita para MVP | GitHub Actions + Supabase + Telegram cubre el cron de testeo sin costo |

---

## Riesgos Técnicos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| ANMAT bloquea scraping del VNM | Media | Alto | Gestionar acceso formal vía `trazabilidad@anmat.gov.ar` — en paralelo con el cron |
| ZK cambia estructura de componentes | Baja | Alto | Tests de regresión automáticos en el mismo cron |
| Baja frecuencia de cambios en el VNM | Media | Alto | El cron de 30 días lo valida antes de construir el producto |
| Falsos positivos en detección de cambios | Media | Medio | Lista control de medicamentos estables para calibrar |

---

## Próximos Pasos

1. **Semana 1** — Armar cron mínimo: scraper → Supabase → Telegram (canal privado)
2. **Semana 2-4** — Correr el cron 30 días, registrar métricas
3. **Paralelo** — Contactar `trazabilidad@anmat.gov.ar` para acceso formal al VNM
4. **Post validación** — Con datos reales, definir stack del producto completo y arrancar desarrollo

---

## Score de Viabilidad (Actualizado)

| Factor | Peso | Score | Ponderado | Justificación |
|---|---|---|---|---|
| Tamaño y urgencia del mercado | 22% | 7.0/10 | 1.54 | Mercado real, dolor concreto en profesionales |
| Validación del dolor / PMF inicial | 25% | 8.5/10 | 2.13 | Alertas activas reales confirmadas en producción |
| Diferenciación y defensibilidad | 18% | 7.0/10 | 1.26 | Canal Telegram + historial propio como moat; modelo SaaS de alertas más claro que solo buscador |
| Riesgos y barreras estructurales | 15% | 7.0/10 | 1.05 | Scraping ZK validado; cron de 30 días valida frecuencia de cambios |
| Viabilidad del modelo económico | 12% | 7.5/10 | 0.90 | SaaS recurrente con free tier Telegram; willingness-to-pay B2B aún sin validar |
| Capacidad de ejecución | 8% | 7.0/10 | 0.56 | Infraestructura gratuita definida; stack por confirmar |
| **Total** | **100%** | **7.4/10** | **7.44** | **PoS estimada: ~72%** |

> **Cambio respecto a versión anterior:** +5 puntos porcentuales (67% → 72%). El driver principal es la claridad del modelo de producto: SaaS de alertas con canal Telegram público como growth hack, búsqueda live en tiempo real, y cron de monitoreo sobre lista conocida. El siguiente salto a ~78% requiere validar frecuencia real de cambios en el VNM (cron de 30 días) y confirmar willingness-to-pay con 3–5 farmacéuticos reales.

---

*Última actualización: Mayo 2026*
*Estado: Definición de producto completada. Próximo paso: cron de testeo de 30 días sobre infraestructura gratuita (GitHub Actions + Supabase + Telegram).*
