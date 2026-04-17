# Coqui TTS Local Server API Documentation

The server provides an OpenAI-compatible API for high-performance text-to-speech synthesis.

**Base URL:** `http://localhost:5100`

---

## 1. Synthesis Endpoint

### `POST /v1/audio/speech`

Generates audio from input text using the specified voice and personality parameters.

#### Headers
- `Content-Type: application/json` (Recommended)
- `Content-Type: multipart/form-data` (Supported for forms and custom voice uploads)

#### Request Body Parameters (JSON)

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `input` | String | **Required** | The text to be synthesized. |
| `model` | String | `tts-1` | Model identifier (OpenAI compatible). |
| `voice` | String | `alloy` | Voice ID from `voices.json` (e.g., `alloy`, `echo`, `nova`). |
| `response_format`| String | `mp3` | Output format: `mp3`, `wav`, `opus`, `flac`. |
| `speed` | Float | `1.0` | Synthesis speed (0.5 to 2.0). |
| `language` | String | `en` | Language code (e.g., `en`, `es`, `fr`). |
| `temperature` | Float | `0.75` | Controls randomness/expressiveness. |
| `length_penalty` | Float | `1.0` | Controls the length of the output. |
| `repetition_penalty`| Float | `5.0` | Prevents word/phrase repetition. |
| `top_k` | Integer | `50` | Limits sampling to the top K tokens. |
| `top_p` | Float | `0.85` | Nucleus sampling threshold. |
| `cache` | Bool | `null` | Per-request cache opt-out. `false` (or `0`) tells the server neither to read from nor write to the audio cache for this request — privacy-sensitive workloads (medical/legal dictation, personal notes) can guarantee nothing is persisted on disk about this single call. `true` is the explicit opt-in; `null`/omitted follows the server default (cache on whenever `CACHE_TTL_MINUTES > 0`). See §3 for the equivalent HTTP-header mechanism and the `X-Cache` response header. |

### `POST /v1/audio/speech/stream`

Real-time streaming TTS endpoint. Returns chunked audio as it is generated.
*Note: This endpoint only runs on the Hot Lane and does not use caching.*

**Example Request:**
```bash
curl -X POST "http://localhost:5100/v1/audio/speech/stream" \
     -H "Content-Type: application/json" \
     -d '{
       "input": "I am generating this audio in real time.",
       "voice": "alloy"
     }' --output stream.wav
```

---

## 2. Examples

### Using JSON (Standard)
```bash
curl -X POST "http://localhost:5100/v1/audio/speech" \
     -H "Content-Type: application/json" \
     -d '{
       "input": "Hello sir, the system is operational.",
       "voice": "alloy",
       "language": "en",
       "temperature": 0.85
     }' --output speech.mp3
```

### Using Form-data (with Personality Tuning)
```bash
curl -X POST "http://localhost:5100/v1/audio/speech" \
     -F "input=Señor, el análisis ha terminado." \
     -F "voice=alloy" \
     -F "language=es" \
     -F "temperature=0.5" \
     --output speech.mp3
```

### Custom Voice Upload (Multipart only) — stateless adhoc cloning

You can provide a local reference audio file for **one-shot cloning**. The server does not persist the sample or any derived latents — the upload lives for the single request only. Any libsndfile-readable format works (wav, flac, mp3, ogg, m4a).

Canonical field name: **`custom_voice_file`**.

```bash
curl -X POST "http://localhost:5100/v1/audio/speech" \
     -F "input=Cloning this specific voice sample." \
     -F "custom_voice_file=@/path/to/reference.wav" \
     --output cloned_speech.mp3
```

Since v2.1.0 the server also accepts `speaker_wav` as an alias for the same field, so client code written against `uttera-tts-vllm` works unchanged here:

```bash
curl -X POST "http://localhost:5100/v1/audio/speech" \
     -F "input=Cloning this specific voice sample." \
     -F "speaker_wav=@/path/to/reference.wav" \
     --output cloned_speech.mp3
```

If both fields are present on the same request, `custom_voice_file` wins.

---

## 3. Responses

### Success (200 OK)
Returns the binary audio file in the requested format.
- `Content-Type: audio/mpeg` (for mp3)
- `Content-Type: audio/wav` (for wav)

### Response headers
- `X-Route: HOT` — synthesised now by the persistent hot worker.
- `X-Route: COLD-POOL` — synthesised now by a subprocess cold worker from the pool.
- `X-Route: COLD-POOL>HOT` — cold worker failed mid-request and the item was re-queued and completed by the hot worker.
- `X-Cache: HIT` — bytes came from the on-disk cache; no synthesis ran.
- `X-Cache: MISS` — cache was enabled but this entry had to be synthesised.
- `X-Cache: BYPASS` — the client asked us to skip the cache for this request.
- `X-Cache: DISABLED` — the operator has disabled the cache globally (`CACHE_TTL_MINUTES <= 0`).

### Cache opt-out — per-request privacy control

By default the server caches synthesised audio on disk keyed by `MD5(model | voice | speed | format | params | text)` for the window configured by `CACHE_TTL_MINUTES`. For **privacy-sensitive workloads** (medical/legal dictation, personal notes, one-off text a user does not want persisted), a client can opt out of the cache on a per-request basis. When the opt-out is requested, the server neither reads from nor writes to the cache for that call; the audio is returned from a temp file that is unlinked as soon as the response is flushed.

Three equivalent mechanisms:

1. **JSON body field**:
   ```bash
   curl -X POST http://localhost:5100/v1/audio/speech \
     -H 'Content-Type: application/json' \
     -d '{"input":"Notas privadas","voice":"alloy","cache":false}' \
     -o out.mp3
   ```

2. **Multipart form field** (accepts `0`, `false`, `no`, `off`):
   ```bash
   curl -X POST http://localhost:5100/v1/audio/speech \
     -F input='Notas privadas' -F voice=alloy -F cache=false -o out.mp3
   ```

3. **HTTP header** (standard `Cache-Control`):
   ```bash
   curl -X POST http://localhost:5100/v1/audio/speech \
     -H 'Cache-Control: no-cache' -H 'Content-Type: application/json' \
     -d '{"input":"Notas privadas","voice":"alloy"}' \
     -o out.mp3
   ```

The response carries `X-Cache: BYPASS` in all three cases so the client can verify. `Cache-Control: no-store` is accepted equivalently.

Notes:
- The opt-out is per-request; the operator's `CACHE_TTL_MINUTES` default is unaffected.
- Adhoc voice-cloning requests (`custom_voice_file` or `speaker_wav` multipart upload) were already cache-ineligible before this feature — they behave identically with or without the `cache` field.
- This server itself logs only the uvicorn access line (method, path, status, response time). The opt-out does not control logging done by reverse proxies or wrapping applications.

### Error (500 Internal Server Error)
Returns a JSON object with error details:
```json
{
  "detail": "Error message description"
}
```

---

## 4. Default Values Configuration

The default values for all parameters (except `input`) can be modified system-wide using environment variables in the `.env` file:
- `DEFAULT_LANGUAGE`
- `DEFAULT_TEMPERATURE`
- `DEFAULT_LENGTH_PENALTY`
- `DEFAULT_REPETITION_PENALTY`
- `DEFAULT_TOP_K`
- `DEFAULT_TOP_P`

---

## 5. Utility Endpoints

### `GET /health`

Returns server liveness and hot worker status. Suitable for proxies and Docker healthchecks.

**Example Request:**
```bash
curl -X GET "http://localhost:5100/health"
```

**Example Response:**
```json
{
  "status": "ok",
  "version": "1.7.0",
  "model": "tts_models/multilingual/multi-dataset/xtts_v2",
  "precision": "fp32",
  "hot_worker_loaded": true,
  "hot_worker_error": null,
  "routing": {
    "load_score": 0.0,
    "accepts_requests": true
  },
  "smart_routing": {
    "ema_spw": 0.3931,
    "cold_start_calibrated": true,
    "cold_ema_start_seconds": 11.18,
    "queue_depth": 0,
    "queue_words": 0.0,
    "queue_drain_estimate_seconds": 0.0,
    "pool_workers_active": 0,
    "pool_workers_loading": 0,
    "pool_workers_optimal": 0,
    "pool_size_cap": 6,
    "vram_free_gb": 20.02,
    "cold_vram_ema_gb": 2.29,
    "vram_sufficient_for_cold": true
  }
}
```

### `GET /v1/models`

OpenAI-compatible model listing. Returns the supported TTS model IDs.

**Example Request:**
```bash
curl -X GET "http://localhost:5100/v1/models"
```

**Example Response:**
```json
{
  "object": "list",
  "data": [
    {"id": "tts-1", "object": "model", "created": 1677610602, "owned_by": "uttera-legacy"},
    {"id": "tts-1-hd", "object": "model", "created": 1677610602, "owned_by": "uttera-legacy"}
  ]
}
```

### `GET /v1/voices`

Returns a list of all available voice identifiers configured on the server.

**Example Request:**
```bash
curl -X GET "http://localhost:5100/v1/voices"
```

**Example Response:**
```json
{
  "voices": ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
}
```
*The list depends on the contents of `voices.json`. Custom voices can be added without modifying application code.*
