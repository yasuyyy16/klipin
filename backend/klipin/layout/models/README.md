# Model deteksi wajah (dibundel, dipakai offline)

Diunduh 2026-11-21 atas izin pemilik proyek (T-031). Jangan diganti tanpa mencatat sumber,
lisensi, dan SHA256 baru di sini.

| File | Sumber | Lisensi | SHA256 |
|---|---|---|---|
| `blaze_face_short_range.tflite` | MediaPipe Face Detector, `https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite` | Apache-2.0 (Google MediaPipe) | `b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f` |
| `face_detection_yunet_2023mar.onnx` | OpenCV Zoo YuNet, `https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet` | MIT (OpenCV Zoo) | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |

Pemakaian: `layout/face_detect.py` — MediaPipe dulu, YuNet (OpenCV DNN `FaceDetectorYN`) bila
MediaPipe tidak menemukan wajah pada frame itu atau gagal dimuat.
