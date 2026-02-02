import os
from fastapi import APIRouter, Request, HTTPException
from cartesia import Cartesia
from cartesia.core.api_error import ApiError
import base64

router = APIRouter()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID")

@router.post("/cartesia/tts")
async def cartesia_tts(request: Request):
    try:
        data = await request.json()
        text = data.get("text")
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
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
    
    except ApiError as e:
        if e.status_code == 402:
            raise HTTPException(
                status_code=402,
                detail="Cartesia credits limit reached. Please upgrade your subscription."
            )
        else:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"Cartesia API error: {e.body}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
