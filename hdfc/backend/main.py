import os
import cv2
import numpy as np
from dotenv import load_dotenv
load_dotenv()
print("SUPABASE_URL:", os.getenv("SUPABASE_URL"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import base64
import requests
import time
from uuid import uuid4

from backend.idfy_endpoints import router as idfy_router
from backend.supabase_uploads import router as supabase_router
from backend.cartesia_tts import router as cartesia_router

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "HDFC KYC Voice Backend Running"}


from fastapi import Request
import base64
import tempfile
from fastapi.responses import JSONResponse

app.include_router(idfy_router)
app.include_router(cartesia_router)
app.include_router(supabase_router)

def detect_face_from_bytes(img_bytes: bytes):
    image_array = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image data")
    gray_image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_classifier = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = face_classifier.detectMultiScale(
        gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )
    if faces is None or len(faces) == 0:
        raise ValueError("No face detected in image")
    (x, y, w, h) = faces[0]
    cropped_face = img[y:y + h, x:x + w]
    success, encoded = cv2.imencode('.png', cropped_face)
    if not success:
        raise ValueError("Failed to encode cropped face")
    return encoded.tobytes()

def upload_image_bytes(img_bytes: bytes, doc_type: str):
    from backend.supabase_uploads import supabase
    file_id = os.urandom(8).hex()
    file_path = f"{file_id}_{doc_type}.png"
    supabase.storage.from_('kyc_document').upload(file_path, img_bytes, {"content-type": "image/png"})
    url = supabase.storage.from_('kyc_document').get_public_url(file_path)
    return url

# --- KYC PROCESS ENDPOINTS ---
@app.post("/kyc/process-aadhaar")
async def process_aadhaar(request: Request):
    data = await request.json()
    aadhaar_b64 = data.get("aadhaar_image")
    session_id = data.get("session_id", str(uuid4()))
    
    def upload_image(b64, doc_type):
        img_bytes = base64.b64decode(b64.split(",")[-1])
        return upload_image_bytes(img_bytes, doc_type)
    
    aadhaar_url = upload_image(aadhaar_b64, "aadhaar")
    print(f"Session ID: {session_id}")
    print(f"Aadhaar uploaded: {aadhaar_url}")
    
    # Create session first
    from backend.supabase_uploads import supabase
    try:
        supabase.table('kyc_sessions').insert({
            "session_id": session_id,
            "status": "processing"
        }).execute()
    except Exception as e:
        print(f"Session creation info: {e}")
    
    aadhaar_face_url = None
    try:
        print("Starting face extraction from Aadhaar...")
        aadhaar_img_bytes = base64.b64decode(aadhaar_b64.split(",")[-1])
        print(f"Decoded image: {len(aadhaar_img_bytes)} bytes")
        
        cropped_face_bytes = detect_face_from_bytes(aadhaar_img_bytes)
        print(f"Face extracted: {len(cropped_face_bytes)} bytes")
        
        aadhaar_face_url = upload_image_bytes(cropped_face_bytes, "aadhaar_face")
        print(f"Face uploaded: {aadhaar_face_url}")
        
        supabase.table('kyc_documents').insert({
            "session_id": session_id,
            "doc_type": "aadhaar_face",
            "image_url": aadhaar_face_url,
            "extracted_data": {
                "source": "opencv_haar_cascade"
            }
        }).execute()
        print(f"✓ Aadhaar face extracted and stored: {aadhaar_face_url}")
    except Exception as e:
        import traceback
        print(f"⚠ Aadhaar face extraction failed: {e}")
        print(traceback.format_exc())
        aadhaar_face_url = None
    
    IDFY_API_KEY = os.getenv("IDFY_API_KEY")
    IDFY_ACCOUNT_ID = os.getenv("IDFY_ACCOUNT_ID")
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }
    
    aadhaar_task = requests.post("https://eve.idfy.com/v3/tasks/async/extract/ind_aadhaar_plus", 
        json={"task_id": session_id + "_aadhaar", "group_id": "kyc_group", 
              "data": {"document1": aadhaar_url, "consent": "yes"}}, 
        headers=headers).json()
    
    print(f"\n=== AADHAAR SUBMITTED ===")
    print("Task ID:", aadhaar_task.get('request_id'))
    
    time.sleep(5)
    aadhaar_response = requests.get(f"https://eve.idfy.com/v3/tasks?request_id={aadhaar_task.get('request_id')}", headers=headers).json()
    aadhaar_result = aadhaar_response[0] if isinstance(aadhaar_response, list) and len(aadhaar_response) > 0 else aadhaar_response
    
    if aadhaar_result.get('error') or aadhaar_result.get('status') == 'failed':
        time.sleep(3)
        aadhaar_response = requests.get(f"https://eve.idfy.com/v3/tasks?request_id={aadhaar_task.get('request_id')}", headers=headers).json()
        aadhaar_result = aadhaar_response[0] if isinstance(aadhaar_response, list) and len(aadhaar_response) > 0 else aadhaar_response
    
    print("Aadhaar result:", aadhaar_result)
    
    # Check for IDfy errors
    if aadhaar_result.get('error') or aadhaar_result.get('status') == 'failed':
        error_msg = aadhaar_result.get('message', 'Unknown error')
        print(f"⚠ IDfy Error: {error_msg}")
        
        # Store with error information
        try:
            supabase.table('kyc_documents').insert({
                "session_id": session_id,
                "doc_type": "aadhaar",
                "image_url": aadhaar_url,
                "extracted_data": {
                    "full_response": aadhaar_result,
                    "error": aadhaar_result.get('error'),
                    "error_message": error_msg
                }
            }).execute()
        except Exception as e:
            print(f"Error storing Aadhaar: {e}")
        
        return JSONResponse({
            "session_id": session_id, 
            "status": "aadhaar_failed",
            "error": error_msg
        }, status_code=400)
    
    try:
        aadhaar_extracted = {}
        if aadhaar_result.get('result') and aadhaar_result['result'].get('extraction_output'):
            aadhaar_extracted = aadhaar_result['result']['extraction_output']
        
        supabase.table('kyc_documents').insert({
            "session_id": session_id,
            "doc_type": "aadhaar",
            "image_url": aadhaar_url,
            "extracted_data": {
                "full_response": aadhaar_result,
                "full_name": aadhaar_extracted.get('name_on_card'),
                "aadhaar_number": aadhaar_extracted.get('id_number'),
                "dob": aadhaar_extracted.get('date_of_birth'),
                "gender": aadhaar_extracted.get('gender'),
                "address": aadhaar_extracted.get('address')
            }
        }).execute()
        print(f"✓ Aadhaar stored")
    except Exception as e:
        print(f"Error storing Aadhaar: {e}")
    
    return JSONResponse({"session_id": session_id, "status": "aadhaar_processed"})

@app.post("/kyc/process-pan")
async def process_pan(request: Request):
    data = await request.json()
    pan_b64 = data.get("pan_image")
    session_id = data.get("session_id")
    
    def upload_image(b64, doc_type):
        img_bytes = base64.b64decode(b64.split(",")[-1])
        return upload_image_bytes(img_bytes, doc_type)
    
    pan_url = upload_image(pan_b64, "pan")
    
    IDFY_API_KEY = os.getenv("IDFY_API_KEY")
    IDFY_ACCOUNT_ID = os.getenv("IDFY_ACCOUNT_ID")
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }
    
    pan_task = requests.post("https://eve.idfy.com/v3/tasks/async/extract/ind_pan",
        json={"task_id": session_id + "_pan", "group_id": "kyc_group",
              "data": {"document1": pan_url}},
        headers=headers).json()
    
    print(f"\n=== PAN SUBMITTED ===")
    print("Task ID:", pan_task.get('request_id'))
    
    time.sleep(5)
    pan_response = requests.get(f"https://eve.idfy.com/v3/tasks?request_id={pan_task.get('request_id')}", headers=headers).json()
    pan_result = pan_response[0] if isinstance(pan_response, list) and len(pan_response) > 0 else pan_response
    
    if pan_result.get('error') or pan_result.get('status') == 'failed':
        time.sleep(3)
        pan_response = requests.get(f"https://eve.idfy.com/v3/tasks?request_id={pan_task.get('request_id')}", headers=headers).json()
        pan_result = pan_response[0] if isinstance(pan_response, list) and len(pan_response) > 0 else pan_response
    
    print("PAN result:", pan_result)
    
    from backend.supabase_uploads import supabase
    try:
        pan_extracted = {}
        if pan_result.get('result') and pan_result['result'].get('extraction_output'):
            pan_extracted = pan_result['result']['extraction_output']
        
        supabase.table('kyc_documents').insert({
            "session_id": session_id,
            "doc_type": "pan",
            "image_url": pan_url,
            "extracted_data": {
                "full_response": pan_result,
                "full_name": pan_extracted.get('name_on_card'),
                "pan_number": pan_extracted.get('id_number'),
                "dob": pan_extracted.get('date_of_birth')
            }
        }).execute()
        print(f"✓ PAN stored")
    except Exception as e:
        print(f"Error storing PAN: {e}")
    
    return JSONResponse({"session_id": session_id, "status": "pan_processed"})

@app.post("/kyc/process-face")
async def process_face(request: Request):
    data = await request.json()
    face_b64 = data.get("face_image")
    session_id = data.get("session_id")
    
    def upload_image(b64, doc_type):
        img_bytes = base64.b64decode(b64.split(",")[-1])
        from backend.supabase_uploads import supabase
        file_id = os.urandom(8).hex()
        file_path = f"{file_id}_{doc_type}.png"
        supabase.storage.from_('kyc_document').upload(file_path, img_bytes, {"content-type": "image/png"})
        url = supabase.storage.from_('kyc_document').get_public_url(file_path)
        return url
    
    face_url = upload_image(face_b64, "face")
    
    # Get Aadhaar face URL from stored documents
    from backend.supabase_uploads import supabase
    aadhaar_face_doc = supabase.table('kyc_documents').select('image_url').eq('session_id', session_id).eq('doc_type', 'aadhaar_face').execute()
    aadhaar_face_url = aadhaar_face_doc.data[-1]['image_url'] if aadhaar_face_doc.data else None
    
    print(f"Session ID: {session_id}")
    print(f"Aadhaar face URL: {aadhaar_face_url}")
    print(f"Face documents found: {len(aadhaar_face_doc.data) if aadhaar_face_doc.data else 0}")
    
    if not aadhaar_face_url:
        print(f"⚠ Aadhaar face not found for session {session_id}")
        return JSONResponse({"session_id": session_id, "status": "face_failed", "error": "Aadhaar face not found. Please recapture Aadhaar."}, status_code=400)

    IDFY_API_KEY = os.getenv("IDFY_API_KEY")
    IDFY_ACCOUNT_ID = os.getenv("IDFY_ACCOUNT_ID")
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }

    face_match_task = requests.post("https://eve.idfy.com/v3/tasks/async/compare/face",
        json={"task_id": session_id + "_face", "group_id": "kyc_group",
              "data": {"document1": aadhaar_face_url, "document2": face_url}},
        headers=headers).json()
    
    print(f"\n=== FACE COMPARISON SUBMITTED ===")
    print("Task ID:", face_match_task.get('request_id'))
    
    time.sleep(5)
    face_match_response = requests.get(f"https://eve.idfy.com/v3/tasks?request_id={face_match_task.get('request_id')}", headers=headers).json()
    face_match_result = face_match_response[0] if isinstance(face_match_response, list) and len(face_match_response) > 0 else face_match_response
    
    print("Face match result:", face_match_result)
    
    try:
        supabase.table('kyc_face_checks').insert({
            "session_id": session_id,
            "liveness_result": {},
            "face_match_result": face_match_result,
            "risk_flag": False
        }).execute()
        print(f"✓ Face comparison stored")
    except Exception as e:
        print(f"Error storing face comparison: {e}")
    
    def is_face_match(result: dict):
        try:
            comp = result.get('result', {}).get('comparison_output', {})
            match_val = comp.get('match')
            if isinstance(match_val, bool):
                return match_val
            if isinstance(match_val, str):
                return match_val.strip().lower() in {"true", "yes", "match"}
            score = comp.get('match_score') or comp.get('confidence')
            if isinstance(score, (int, float)):
                return score >= 0.6
        except Exception:
            pass
        return False

    face_match = is_face_match(face_match_result)

    return JSONResponse({"session_id": session_id, "status": "face_processed", "face_match": face_match})

@app.get("/kyc/get-details/{session_id}")
async def get_kyc_details(session_id: str):
    from backend.supabase_uploads import supabase
    
    try:
        documents = supabase.table('kyc_documents').select('*').eq('session_id', session_id).execute()
        
        details = {}
        for doc in documents.data:
            if doc['doc_type'] == 'aadhaar':
                extracted = doc.get('extracted_data', {})
                details['aadhaar_name'] = extracted.get('full_name', 'N/A')
                details['aadhaar_number'] = extracted.get('aadhaar_number', 'N/A')
                details['aadhaar_dob'] = extracted.get('dob', 'N/A')
            elif doc['doc_type'] == 'pan':
                extracted = doc.get('extracted_data', {})
                details['pan_number'] = extracted.get('pan_number', 'N/A')
                details['pan_name'] = extracted.get('full_name', 'N/A')
        
        print(f"\n=== FETCHED DETAILS FROM DB ===")
        print(details)
        return JSONResponse({"details": details})
    except Exception as e:
        print(f"Error fetching details: {e}")
        return JSONResponse({"details": {}, "error": str(e)}, status_code=500)

@app.post("/kyc/update")
async def kyc_update(request: Request):
    data = await request.json()
    print("\n=== KYC UPDATE DATA ===")
    print(data)
    from backend.supabase_uploads import supabase
    try:
        # Update the session status to confirmed
        session_id = data.get("session_id", "kyc-session")
        
        # Only update status field (kyc_sessions doesn't have detail columns)
        supabase.table('kyc_sessions').update({
            "status": "confirmed"
        }).eq("session_id", session_id).execute()
        
        # Store updated details as metadata if needed
        # (Details are already in kyc_documents table extracted_data)
        
        print(f"✓ Session {session_id} confirmed")
    except Exception as e:
        print(f"Error updating session: {e}")
    return {"status": "success"}
