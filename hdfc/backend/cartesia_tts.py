import os
from fastapi import APIRouter, Request
from cartesia import Cartesia
import base64

router = APIRouter()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID")

@router.post("/cartesia/tts")
async def cartesia_tts(request: Request):
    data = await request.json()
    text = data.get("text")
    
    try:
        client = Cartesia(api_key=CARTESIA_API_KEY)
        audio_gen = client.tts.bytes(
            model_id="sonic-2",
            transcript=text,
            voice={
                "mode": "id",
                "id": CARTESIA_VOICE_ID,
            },
            language="hi",
            output_format={
                "container": "wav",
                "sample_rate": 44100,
                "encoding": "pcm_f32le",
            },
        )
        audio_bytes = b''.join(audio_gen)
        audio_b64 = base64.b64encode(audio_bytes).decode()
        return {"audio_b64": audio_b64}
    except Exception as e:
        # Return empty response on error - frontend will fallback to browser TTS
        print(f"Cartesia TTS error: {e}")
        return {"audio_b64": None, "error": str(e)}
