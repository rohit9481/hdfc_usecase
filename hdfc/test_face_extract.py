import cv2
import numpy as np
import requests
from io import BytesIO
import base64
import sys

def detect_face_from_bytes(img_bytes: bytes):
    """Extract face from image bytes using OpenCV Haar Cascade"""
    image_array = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image data")
    
    print(f"Image shape: {img.shape}")
    
    gray_image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_classifier = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    
    print("Detecting faces...")
    faces = face_classifier.detectMultiScale(
        gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )
    
    print(f"Faces found: {len(faces)}")
    
    if faces is None or len(faces) == 0:
        raise ValueError("No face detected in image")
    
    (x, y, w, h) = faces[0]
    print(f"Face coordinates: x={x}, y={y}, w={w}, h={h}")
    
    cropped_face = img[y:y + h, x:x + w]
    print(f"Cropped face shape: {cropped_face.shape}")
    
    success, encoded = cv2.imencode('.png', cropped_face)
    if not success:
        raise ValueError("Failed to encode cropped face")
    
    return encoded.tobytes()

def test_with_url(image_url):
    """Test face extraction with image URL"""
    print(f"\n=== Testing Face Extraction ===")
    print(f"Image URL: {image_url}\n")
    
    try:
        # Download image
        print("Downloading image...")
        response = requests.get(image_url)
        response.raise_for_status()
        img_bytes = response.content
        print(f"Downloaded: {len(img_bytes)} bytes")
        
        # Extract face
        print("\nExtracting face...")
        cropped_face_bytes = detect_face_from_bytes(img_bytes)
        print(f"✓ Face extracted successfully: {len(cropped_face_bytes)} bytes")
        
        # Save extracted face
        with open("extracted_face.png", "wb") as f:
            f.write(cropped_face_bytes)
        print("✓ Saved to extracted_face.png")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_with_local_file(file_path):
    """Test face extraction with local file"""
    print(f"\n=== Testing Face Extraction ===")
    print(f"File: {file_path}\n")
    
    try:
        # Read file
        print("Reading file...")
        with open(file_path, "rb") as f:
            img_bytes = f.read()
        print(f"Read: {len(img_bytes)} bytes")
        
        # Extract face
        print("\nExtracting face...")
        cropped_face_bytes = detect_face_from_bytes(img_bytes)
        print(f"✓ Face extracted successfully: {len(cropped_face_bytes)} bytes")
        
        # Save extracted face
        with open("extracted_face.png", "wb") as f:
            f.write(cropped_face_bytes)
        print("✓ Saved to extracted_face.png")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    print("Face Extraction Test\n")
    
    if len(sys.argv) > 1:
        # Command line argument provided
        file_path = sys.argv[1]
        test_with_local_file(file_path)
    else:
        # Interactive mode
        option = input("Enter 'url' for URL or 'file' for local file: ").strip().lower()
        
        if option == "url":
            image_url = input("Enter image URL: ").strip()
            test_with_url(image_url)
        elif option == "file":
            file_path = input("Enter file path: ").strip()
            test_with_local_file(file_path)
        else:
            print("Invalid option")
