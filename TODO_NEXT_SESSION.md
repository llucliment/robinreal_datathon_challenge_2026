# Pendiente para próxima sesión

## Estado actual del sistema (todo en main, 43/43 tests OK)

### Pipeline completo implementado
- Hard extraction: LLM (Haiku) + fallback regex
- Soft extraction: LLM con 20 labels canónicos
- Soft filtering: keywords/sinónimos multilingüe, distancias estructuradas, transit time SBB real, landmark geocoding
- Ranking: weighted soft_scores + sentence-transformers embeddings + profile multiplier
- Image descriptions: generando para SRED (~11k listings) — script en background
- User history: tabla SQLite + Claude genera perfil JSON + multipliers en ranking

---

## Lo que FALTA por implementar

### 1. Deployment público HTTPS (OBLIGATORIO para entregar)
El challenge pide una API HTTPS pública. Ahora solo hay HTTP local (puerto 8000).

**Opción más rápida para datathon:**
- Railway.app: `railway up` desde la raíz, detecta Dockerfile automáticamente
- O Render.com: conectar repo GitHub, build con Dockerfile
- O ngrok temporal: `ngrok http 8000` para demo rápida

**Variables de entorno a configurar en el deploy:**
```
ANTHROPIC_API_KEY=...
LISTINGS_DB_PATH=/data/listings.db   # necesita volumen persistente
LISTINGS_RAW_DATA_DIR=/app/raw_data
AWS_ACCESS_KEY_ID=...  (opcional, para S3)
AWS_SECRET_ACCESS_KEY=...
```

**Problema**: la DB SQLite (~500MB con imágenes) necesita persistirse. En Railway usar un volumen. Alternativamente, commitar la DB o generarla en el build.

---

### 2. Integrar image_description en el widget frontend
El campo `image_description` existe en la DB y se devuelve en `ListingData` pero el widget React (`apps_sdk/web/src/components/RankedList.tsx`) no lo muestra.

**Qué hacer**: mostrar la descripción visual bajo el título del listing o como tooltip en la imagen.

---

### 3. Logging de clicks desde el frontend
El sistema de historial está implementado en el backend pero nadie llama a los endpoints.

**Endpoints disponibles:**
```
POST /users/{user_id}/interactions
  Body: {"user_id": "...", "listing_id": "...", "event_type": "click|favorite|hide"}

GET /users/{user_id}/profile
```

**Qué falta**: que el widget React llame a `POST /users/{user_id}/interactions` cuando el usuario:
- Hace click en un listing → event_type: "click"
- Marca favorito → event_type: "favorite"
- Oculta un resultado → event_type: "hide"

Y que el `user_id` se pase en las llamadas a `POST /listings` (ya acepta el campo).

---

### 4. Probar el pipeline end-to-end con queries reales
No hay evidencia de que se haya probado manualmente el sistema completo.

**Queries a probar:**
```bash
curl -X POST http://localhost:8000/listings \
  -H "Content-Type: application/json" \
  -d '{"query": "bright modern apartment in Zurich max 2800 CHF with balcony", "limit": 5}'

curl -X POST http://localhost:8000/listings \
  -H "Content-Type: application/json" \
  -d '{"query": "max 30 min to ETH Zurich by public transport, family friendly", "limit": 5, "user_id": "test_user"}'
```

---

### 5. Terminar las image_descriptions
El script sigue corriendo. Estado actual: ~48% SRED descritas.
Cuando termine, las descripciones empezarán a influir en soft_filtering automáticamente.

Para ver el progreso:
```python
from app.config import get_settings
from app.db import get_connection
s = get_settings()
with get_connection(s.db_path) as c:
    r = c.execute("SELECT scrape_source, SUM(image_description IS NOT NULL) as d, COUNT(*) as t FROM listings GROUP BY scrape_source").fetchall()
    [print(f"{row[0]}: {row[1]}/{row[2]}") for row in r]
```

---

### 6. Mejorar el perfil de usuario con listings reales
Actualmente el perfil solo ve queries y listing_ids. Para que Claude infiera mejor, habría que enriquecer el contexto enviando también los datos del listing (ciudad, precio, habitaciones, features) cuando se registra un click.

**Dónde cambiar**: `app/harness/user_interactions.py` → añadir columna `listing_snapshot_json` y popularlo desde `search_service.py` con los datos del listing clicado.

---

### 7. Tests para el sistema de historial
No hay tests para:
- `user_interactions.py` (log, get, save, needs_regen)
- `user_profile.py` (get_or_generate_profile)
- Endpoints `/users/{user_id}/interactions` y `/users/{user_id}/profile`

Añadir en `tests/test_user_profile.py`.

---

## Archivos clave para el sistema de historial

| Archivo | Rol |
|---------|-----|
| `app/harness/user_interactions.py` | CRUD SQLite para interacciones y perfiles |
| `app/participant/user_profile.py` | Claude Haiku genera perfil JSON |
| `app/api/routes/interactions.py` | Endpoints REST para registrar eventos |
| `app/participant/ranking.py` | `_profile_multiplier()` aplica boosts |
| `app/harness/search_service.py` | Conecta todo: log search + fetch profile |

## Cómo funciona el historial (resumen)

1. User hace query con `user_id` → se loggea en `user_interactions`
2. Cada 5 interacciones → Claude regenera el perfil JSON
3. Perfil incluye: `preferred_cities`, `feature_affinity`, `aesthetic_preferences`, `typical_budget_chf`, `negative_patterns`, `confidence`
4. En ranking, `_profile_multiplier` aplica hasta +25% boost a listings que coincidan con ciudad, features, presupuesto y estética histórica
5. El `reason` del resultado muestra: `"profile: preferred city, features: balcony"`
