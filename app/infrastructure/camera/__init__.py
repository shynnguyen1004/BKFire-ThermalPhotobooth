"""Camera adapters."""

from app.infrastructure.camera.auto_camera import AutoCamera, Camera
from app.infrastructure.camera.gphoto_camera import CameraError, GPhotoCamera
from app.infrastructure.camera.webcam_camera import WebcamCamera

__all__ = ["AutoCamera", "Camera", "CameraError", "GPhotoCamera", "WebcamCamera"]
