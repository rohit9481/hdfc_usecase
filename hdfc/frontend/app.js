// app.js - HDFC KYC Voice Flow (skeleton)

// This file will handle the voice-driven flow, permissions, camera, and communication with backend


let mediaRecorder = null;
let recordedChunks = [];
let recordingStream = null;

document.addEventListener('DOMContentLoaded', () => {
    // Voice-driven permission and camera flow
    const steps = [
        {
            id: 'mic',
            prompt: 'Please allow microphone access to continue your KYC process.'
        },
        {
            id: 'audio',
            prompt: 'Please allow audio access to continue your KYC process.'
        },
        {
            id: 'location',
            prompt: 'Please allow location access to continue your KYC process.'
        }
    ];

    let currentStep = 0;

    const BACKEND_URL = 'http://127.0.0.1:8000';

    async function cartesiaSpeak(text) {
        // Call backend endpoint to get Cartesia TTS audio
        const response = await fetch(`${BACKEND_URL}/cartesia/tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        const data = await response.json();
        if (data.audio_url) {
            const audio = new Audio(data.audio_url);
            audio.play();
        } else if (data.audio_b64) {
            const audio = new Audio(`data:audio/wav;base64,${data.audio_b64}`);
            audio.play();
        }
    }

    function speak(text) {
        // Use Cartesia TTS if available, else fallback to browser TTS
        cartesiaSpeak(text).catch(() => {
            const synth = window.speechSynthesis;
            const utter = new SpeechSynthesisUtterance(text);
            synth.speak(utter);
        });
    }

    async function startScreenAudioRecording() {
        try {
            const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
            const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            // Combine screen and mic audio
            const combinedTracks = [
                ...screenStream.getVideoTracks(),
                ...audioStream.getAudioTracks()
            ];
            recordingStream = new MediaStream(combinedTracks);
            recordedChunks = [];
            mediaRecorder = new MediaRecorder(recordingStream, { mimeType: 'video/webm; codecs=vp8,opus' });
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) recordedChunks.push(e.data);
            };
            mediaRecorder.start();
        } catch (err) {
            alert('Screen/audio recording permission denied or not supported.');
        }
    }

    async function stopAndUploadRecording(session_id = 'kyc-session') {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            return new Promise((resolve) => {
                mediaRecorder.onstop = async () => {
                    const blob = new Blob(recordedChunks, { type: 'video/webm' });
                    const formData = new FormData();
                    formData.append('session_id', session_id);
                    formData.append('file', blob, 'kyc_recording.webm');
                    formData.append('recording_type', 'full_process');
                    await fetch(`${BACKEND_URL}/upload/recording`, {
                        method: 'POST',
                        body: formData
                    });
                    resolve();
                };
                mediaRecorder.stop();
                if (recordingStream) {
                    recordingStream.getTracks().forEach(track => track.stop());
                }
            });
        }
    }

    function askPermission(step) {
        app.innerHTML = `<img id="logo" src="logo.png" alt="HDFC Logo"><h2>${step.prompt}</h2>`;
        speak(step.prompt);
        // Show allow button for manual fallback
        app.innerHTML += `<button id="allowBtn">Allow</button>`;
        document.getElementById('allowBtn').onclick = async () => {
            if (currentStep === 0) {
                await startScreenAudioRecording(); // Start recording at the beginning
            }
            nextStep();
        };
    }

    function nextStep() {
        currentStep++;
        if (currentStep < steps.length) {
            askPermission(steps[currentStep]);
        } else {
            startCameraFlow();
        }
    }

    function startCameraFlow() {
        navigator.mediaDevices.getUserMedia({ video: true, audio: true })
            .then(stream => {
                askAadhaarCard(stream);
            })
            .catch(err => {
                app.innerHTML = `<p>Camera access denied. Please enable camera to continue.</p>`;
            });
    }

    let aadhaarImage = null;
    let panImage = null;
    let faceImage = null;
    let sessionId = null;
    let processingPromises = []; // Track async processing for Aadhaar/PAN
    let pendingFaceRetry = false;

    function captureImage(type, stream) {
        const video = document.getElementById('video');
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/png');
        
        if (type === 'aadhaar') {
            aadhaarImage = dataUrl;
        } else if (type === 'pan') {
            panImage = dataUrl;
        } else if (type === 'face') {
            faceImage = dataUrl;
        }
        
        if (type === 'aadhaar') {
            if (pendingFaceRetry) {
                app.innerHTML = `<h2>Comparing your face with your documents...</h2>`;
                speak('Comparing your face with your documents.');
                sendToIDfyAsync('aadhaar', dataUrl)
                    .then(() => sendToIDfyAsync('face', faceImage))
                    .then((result) => handleFaceMatchResult(result, stream))
                    .catch(() => {
                        app.innerHTML = `<h2>Error processing your details. Please try again.</h2>`;
                    });
                return;
            }

            // Send to IDfy in background (don't show "Processing..." message)
            const p = sendToIDfyAsync('aadhaar', dataUrl);
            processingPromises.push(p);
            speak('Aadhaar card captured. Now please show your PAN card.');
            askPanCard(stream);
        } else if (type === 'pan') {
            const p = sendToIDfyAsync('pan', dataUrl);
            processingPromises.push(p);
            speak('PAN card captured. Now please align your face for verification.');
            askFace(stream);
        } else if (type === 'face') {
            app.innerHTML = `<h2>Comparing your face with your documents...</h2>`;
            speak('Comparing your face with your documents.');
            sendToIDfyAsync('face', dataUrl)
                .then((result) => handleFaceMatchResult(result, stream))
                .catch(() => {
                    app.innerHTML = `<h2>Error processing your details. Please try again.</h2>`;
                });
        }
    }

    async function sendToIDfyAsync(type, imageData) {
        const endpoint = type === 'aadhaar' ? '/kyc/process-aadhaar' :
                        type === 'pan' ? '/kyc/process-pan' :
                        '/kyc/process-face';
        
        const requestBody = {
            [type + '_image']: imageData
        };
        
        if (sessionId) {
            requestBody.session_id = sessionId;
        }
        
        try {
            const response = await fetch(`${BACKEND_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });
            const data = await response.json();
            if (!response.ok) {
                const err = new Error(data && data.error ? data.error : 'Request failed');
                err.data = data;
                throw err;
            }
            
            if (data.session_id && !sessionId) {
                sessionId = data.session_id;
                console.log(`Session ID generated: ${sessionId}`);
            }
            return data;
        } catch (err) {
            console.error('Error processing:', err);
            throw err;
        }
    }

    function handleFaceMatchResult(result, stream) {
        if (result && (result.face_match === false || result.error || result.status === 'face_failed')) {
            pendingFaceRetry = true;
            speak('Face does not match the Aadhaar photo. Please capture your Aadhaar card again.');
            askAadhaarCard(stream);
            return;
        }

        pendingFaceRetry = false;
        speak('Face matched. Processing your information...');
        setTimeout(() => {
            Promise.all(processingPromises)
                .then(() => fetchAndShowDetails())
                .catch(() => {
                    app.innerHTML = `<h2>Error processing your details. Please try again.</h2>`;
                });
        }, 3000);
    }

    function fetchAndShowDetails() {
        fetch(`${BACKEND_URL}/kyc/get-details/${sessionId}`)
            .then(res => res.json())
            .then(data => {
                showReviewAndModify(data.details || {});
            })
            .catch(() => {
                app.innerHTML = `<h2>Error fetching details. Please try again.</h2>`;
            });
    }

    function askPanCard(stream) {
        app.innerHTML = `<h2>Now, please show your PAN card to the camera and click Capture.</h2><video id="video" autoplay playsinline width="300"></video><br><button id="panCaptureBtn">Capture PAN</button>`;
        speak('Now, please show your PAN card to the camera and click Capture.');
        document.getElementById('video').srcObject = stream;
        document.getElementById('panCaptureBtn').onclick = () => {
            captureImage('pan', stream);
        };
    }

    function askAadhaarCard(stream) {
        app.innerHTML = `<h2>Please show your Aadhaar card to the camera and click Capture.</h2><video id="video" autoplay playsinline width="300"></video><br><button id="aadhaarCaptureBtn">Capture Aadhaar</button>`;
        speak('Please show your Aadhaar card to the camera and click Capture.');
        document.getElementById('video').srcObject = stream;
        document.getElementById('aadhaarCaptureBtn').onclick = () => {
            captureImage('aadhaar', stream);
        };
    }

    function askFace(stream) {
        app.innerHTML = `<h2>Now, please align your face in the camera and click Capture Face.</h2><video id="video" autoplay playsinline width="300"></video><br><button id="faceCaptureBtn">Capture Face</button>`;
        speak('Now, please align your face in the camera and click Capture Face.');
        document.getElementById('video').srcObject = stream;
        document.getElementById('faceCaptureBtn').onclick = () => {
            captureImage('face', stream);
        };
    }



    function showConfirmation(name) {
        app.innerHTML = `<h2>${name}, I confirm that the information given is correct and with my own will, I am interested in an HDFC loan.</h2><button id='finalConfirmBtn'>Confirm</button>`;
        speak(`${name}, I confirm that the information given is correct and with my own will, I am interested in an HDFC loan.`);
        document.getElementById('finalConfirmBtn').onclick = () => {
            app.innerHTML = `<h2>Thank you, ${name}! Your KYC is completed.</h2>`;
            speak(`Thank you, ${name}! Your KYC is completed.`);
        };
    }

    function showReviewAndModify(details) {
        const formattedDetails = {
            'Full Name': details.aadhaar_name || details.pan_name || 'N/A',
            'Aadhaar Number': details.aadhaar_number || 'N/A',
            'Date of Birth': details.aadhaar_dob || 'N/A',
            'PAN Number': details.pan_number || 'N/A',
            'PAN Name': details.pan_name || 'N/A'
        };
        
        let html = '<h2>Review and Confirm Your Details</h2>';
        for (const [key, value] of Object.entries(formattedDetails)) {
            // Always show fields, even if empty
            html += `<div style="margin: 10px 0;"><label>${key}:</label> <input type="text" id="field_${key}" value="${value}" style="width: 100%; padding: 8px; margin-top: 5px;"></div>`;
        }
        html += '<button id="confirmBtn" style="margin-top: 20px; padding: 10px 20px; background: #00A699; color: white; border: none; border-radius: 5px; cursor: pointer;">Confirm Details</button>';
        app.innerHTML = html;
        speak('Please review your details. You can modify them if needed, then click Confirm.');
        document.getElementById('confirmBtn').onclick = () => {
            const updated = {};
            for (const key of Object.keys(formattedDetails)) {
                updated[key] = document.getElementById(`field_${key}`).value;
            }
            // Send updated details to backend
            fetch(`${BACKEND_URL}/kyc/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({...updated, session_id: sessionId})
            }).then(() => {
                // Use the updated value from the form, not the original
                const userName = updated['Full Name'] && updated['Full Name'] !== 'N/A' ? updated['Full Name'] : 'User';
                showLegalConfirmation(userName);
            });
        };
    }

    function showLegalConfirmation(name) {
        const greeting = name === 'User' || name === 'N/A' ? 'Please' : `${name}, please`;
        const legalMsg = `${greeting} read the following statement on camera: I confirm that the information given is correct and with my own will, I am interested in an HDFC loan.`;
        app.innerHTML = `
            <h2>Final Confirmation</h2>
            <video id="confirmVideo" autoplay playsinline width="300"></video>
            <div style="background: #FAF3E6; padding: 1.5em; border-radius: 8px; margin: 1em 0; border: 2px solid #D17300;">
                <p style="font-size: 1.1em; line-height: 1.6; color: #6D3C00; font-weight: 600;">${legalMsg}</p>
            </div>
            <button id='readOnCameraBtn'>I'm Ready to Read</button>
        `;
        speak(legalMsg);
        
        // Show user's face in video while they read
        navigator.mediaDevices.getUserMedia({ video: true, audio: true })
            .then(stream => {
                document.getElementById('confirmVideo').srcObject = stream;
            });
        
        document.getElementById('readOnCameraBtn').onclick = () => {
            app.innerHTML = `
                <h2>Recording... Please read the statement aloud</h2>
                <video id="recordVideo" autoplay playsinline width="300"></video>
                <div style="background: #FAF3E6; padding: 1.5em; border-radius: 8px; margin: 1em 0; border: 2px solid #D17300;">
                    <p style="font-size: 1.1em; line-height: 1.6; color: #6D3C00; font-weight: 600;">${legalMsg}</p>
                </div>
            `;
            navigator.mediaDevices.getUserMedia({ video: true, audio: true })
                .then(stream => {
                    document.getElementById('recordVideo').srcObject = stream;
                });
            
            // Record for 10 seconds, then finish and upload
            setTimeout(async () => {
                await stopAndUploadRecording(sessionId);
                const thankYouMsg = name === 'User' || name === 'N/A' 
                    ? 'Thank you! Your KYC is completed.' 
                    : `Thank you, ${name}! Your KYC is completed.`;
                app.innerHTML = `<h2>${thankYouMsg}</h2>`;
                speak(thankYouMsg);
            }, 10000);
        };
    }

    askPermission(steps[currentStep]);
});
