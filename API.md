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
| `voice` | String | `alloy` | Voice ID (e.g., `assistant`, `voice-c`, `a voice`). |
| `response_format`| String | `mp3` | Output format: `mp3`, `wav`, `opus`, `flac`. |
| `speed` | Float | `1.0` | Synthesis speed (0.5 to 2.0). |
| `language` | String | `en` | Language code (e.g., `en`, `es`, `fr`). |
| `temperature` | Float | `0.75` | Controls randomness/expressiveness. |
| `length_penalty` | Float | `1.0` | Controls the length of the output. |
| `repetition_penalty`| Float | `5.0` | Prevents word/phrase repetition. |
| `top_k` | Integer | `50` | Limits sampling to the top K tokens. |
| `top_p` | Float | `0.85` | Nucleus sampling threshold. |

### `POST /v1/audio/speech/stream`

Real-time streaming TTS endpoint. Returns chunked audio as it is generated.
*Note: This endpoint only runs on the Hot Lane and does not use caching.*

**Example Request:**
```bash
curl -X POST "http://localhost:5100/v1/audio/speech/stream" \
     -H "Content-Type: application/json" \
     -d '{
       "input": "I am generating this audio in real time.",
       "voice": "narrator"
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
       "voice": "narrator",
       "language": "en",
       "temperature": 0.85
     }' --output speech.mp3
```

### Using Form-data (with Personality Tuning)
```bash
curl -X POST "http://localhost:5100/v1/audio/speech" \
     -F "input=Señor, el análisis ha terminado." \
     -F "voice=assistant" \
     -F "language=es" \
     -F "temperature=0.5" \
     --output speech.mp3
```

### Custom Voice Upload (Multipart only)
You can provide a local `.wav` file as a reference for one-shot cloning:
```bash
curl -X POST "http://localhost:5100/v1/audio/speech" \
     -F "input=Cloning this specific voice sample." \
     -F "custom_voice_file=@/path/to/reference.wav" \
     --output cloned_speech.mp3
```

---

## 3. Responses

### Success (200 OK)
Returns the binary audio file in the requested format.
- `Content-Type: audio/mpeg` (for mp3)
- `Content-Type: audio/wav` (for wav)

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
  "version": "1.4.10",
  "model": "tts_models/multilingual/multi-dataset/xtts_v2",
  "hot_worker_loaded": true,
  "hot_worker_error": null
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
  "voices": ["alloy", "voice-d", "echo", "fable", "voice-b", "voice-e", "voice-c", "narrator", "voice-g", "nova", "onyx", "voice-h", "voice-a", "shimmer", "voice-f"]
}
```
