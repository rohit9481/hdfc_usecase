import os
from dotenv import load_dotenv
from fastapi import APIRouter, UploadFile, File, Form
from supabase import create_client, Client
from uuid import uuid4

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

router = APIRouter()

@router.post("/upload/image")
async def upload_image(session_id: str = Form(...), doc_type: str = Form(...), file: UploadFile = File(...)):
    ext = file.filename.split('.')[-1]
    file_id = str(uuid4())
    file_path = f"kyc_document/{file_id}.{ext}"
    content = await file.read()
    supabase.storage.from_('kyc_document').upload(file_path, content)
    public_url = supabase.storage.from_('kyc_document').get_public_url(file_path)
    # Insert into kyc_documents table
    supabase.table('kyc_documents').insert({
        "session_id": session_id,
        "doc_type": doc_type,
        "image_url": public_url,
    }).execute()
    return {"url": public_url}

@router.post("/upload/recording")
async def upload_recording(session_id: str = Form(...), file: UploadFile = File(...), recording_type: str = Form(...)):
    ext = file.filename.split('.')[-1]
    file_id = str(uuid4())
    file_path = f"kyc_recording/{file_id}.{ext}"
    content = await file.read()
    supabase.storage.from_('kyc_recording').upload(file_path, content)
    public_url = supabase.storage.from_('kyc_recording').get_public_url(file_path)
    
    # Store recording URL in kyc_recordings table
    try:
        if recording_type == "full_process":
            supabase.table('kyc_recordings').insert({
                "session_id": session_id,
                "screen_recording_url": public_url,
                "mic_audio_url": public_url
            }).execute()
        print(f"✓ Recording stored for session {session_id}")
    except Exception as e:
        print(f"Error storing recording: {e}")
    
    return {"url": public_url}
