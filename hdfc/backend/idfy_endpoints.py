import os
import requests
from fastapi import APIRouter, Form
from supabase import create_client, Client

router = APIRouter()

IDFY_API_KEY = os.getenv("IDFY_API_KEY")
IDFY_ACCOUNT_ID = os.getenv("IDFY_ACCOUNT_ID")
IDFY_GROUP_ID = os.getenv("IDFY_GROUP_ID", "test_group")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

# Aadhaar OCR
@router.post("/idfy/aadhaar")
def idfy_aadhaar(session_id: str = Form(...), image_url: str = Form(...)):
    url = "https://eve.idfy.com/v3/tasks/async/extract/ind_aadhaar_plus"
    payload = {
        "task_id": session_id,
        "group_id": "aadhaar_ocr_plus",
        "data": {
            "document1": image_url,
            "consent": "yes",
            "advanced_details": {
                "extract_qr_info": True,
                "extract_last_4_digit": True
            }
        }
    }
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

# PAN OCR
@router.post("/idfy/pan")
def idfy_pan(session_id: str = Form(...), image_url: str = Form(...)):
    url = "https://eve.idfy.com/v3/tasks/async/extract/ind_pan"
    payload = {
        "task_id": session_id,
        "group_id": IDFY_GROUP_ID,
        "data": {
            "document1": image_url
        }
    }
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

# Liveness
@router.post("/idfy/liveness")
def idfy_liveness(session_id: str = Form(...), image_url: str = Form(...)):
    url = "https://eve.idfy.com/v3/tasks/async/check_photo_liveness/face"
    payload = {
        "task_id": session_id,
        "group_id": IDFY_GROUP_ID,
        "data": {
            "document1": image_url,
            "detect_face_mask": True,
            "detect_front_facing": True,
            "detect_nsfw": True
        }
    }
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

# Face Match
@router.post("/idfy/face_match")
def idfy_face_match(session_id: str = Form(...), image1_url: str = Form(...), image2_url: str = Form(...)):
    url = "https://eve.idfy.com/v3/tasks/async/compare/face"
    payload = {
        "task_id": session_id,
        "group_id": IDFY_GROUP_ID,
        "data": {
            "document1": image1_url,
            "document2": image2_url
        }
    }
    headers = {
        'Content-Type': 'application/json',
        'account-id': IDFY_ACCOUNT_ID,
        'api-key': IDFY_API_KEY
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

# ...existing code...
