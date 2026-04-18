"""
Bench 160 concurrent TTS — 4 rounds × 40 prompts of ~40 words.

Cache avoidance: each round uses a DIFFERENT voice so (text, voice_id)
never repeats across the 160 requests.

Usage:
    python bench_160x40w.py [URL]
    python bench_160x40w.py http://sphinx:9004/v1/audio/speech
"""
import asyncio
import glob
import os
import sys
import time
import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9004/v1/audio/speech"
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts_40w")
VOICES_PER_ROUND = ["alloy", "echo", "fable", "nova"]
ROUNDS = len(VOICES_PER_ROUND)

# Load 40 text files sorted by name
prompt_files = sorted(glob.glob(os.path.join(PROMPT_DIR, "prompt_*.txt")))
assert len(prompt_files) == 40, f"Expected 40 prompt files, got {len(prompt_files)}"
PROMPTS = []
for pf in prompt_files:
    with open(pf) as f:
        PROMPTS.append(f.read().strip())

N = ROUNDS * len(PROMPTS)  # 4 × 40 = 160
print(f"Loaded {len(PROMPTS)} prompts (avg {sum(len(p.split()) for p in PROMPTS)//len(PROMPTS)} words)")
print(f"Launching {N} concurrent requests against {URL}")
print(f"Voices per round: {VOICES_PER_ROUND} → {N} unique (text, voice) combos, 0 cache hits")
print()


async def one(client, j):
    round_idx = j // len(PROMPTS)
    prompt_idx = j % len(PROMPTS)
    voice = VOICES_PER_ROUND[round_idx]
    text = PROMPTS[prompt_idx]

    body = {
        "model": "tts-1",
        "voice": voice,
        "input": text,
        "language": "es",
    }
    t0 = time.time()
    try:
        r = await client.post(URL, json=body, timeout=600)
        return r.status_code, time.time() - t0, len(r.content), r.headers.get("X-Route", "?")
    except Exception as e:
        return 0, time.time() - t0, 0, str(e)[:60]


async def main():
    limits = httpx.Limits(max_connections=N + 10, max_keepalive_connections=N + 10)
    async with httpx.AsyncClient(limits=limits) as client:
        t0 = time.time()
        results = await asyncio.gather(*[one(client, j) for j in range(N)])
        total = time.time() - t0

    ok = [r for r in results if r[0] == 200]
    fail = [r for r in results if r[0] != 200]
    lats = sorted(r[1] for r in ok)

    routes = {}
    for r in ok:
        routes[r[3]] = routes.get(r[3], 0) + 1

    print(f"N={N}  total={total:.1f}s  rps={N / total:.2f}  ok={len(ok)}  fail={len(fail)}")
    if lats:
        print(f"lat  min={lats[0]:.2f}s  p50={lats[len(lats) // 2]:.2f}s  "
              f"p90={lats[int(len(lats) * 0.90)]:.2f}s  p95={lats[int(len(lats) * 0.95)]:.2f}s  "
              f"p99={lats[int(len(lats) * 0.99)]:.2f}s  max={max(lats):.2f}s  "
              f"avg={sum(lats) / len(lats):.2f}s")
        print(f"avg_payload={sum(r[2] for r in ok) // len(ok):,} bytes")
        print(f"words_total={sum(len(p.split()) for p in PROMPTS) * ROUNDS}  "
              f"words_per_req≈{sum(len(p.split()) for p in PROMPTS) // len(PROMPTS)}")
    print(f"route: {routes}")
    for f in fail[:5]:
        print(f"FAIL: status={f[0]} elapsed={f[1]:.1f}s err={f[3]}")


asyncio.run(main())
