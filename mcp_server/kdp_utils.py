import os

from PIL import Image


def resize_and_crop_kdp_cover(source_path: str, dest_path: str) -> None:
    """
    Format-agnostic utility to format, convert, and upscale an existing image
    into an Amazon KDP-compliant cover image (1600x2560 pixels, RGB, JPEG, at 300 DPI)
    with 5MB size limit validation and fallback compression.
    """
    target_width = 1600
    target_height = 2560
    target_ratio = target_width / target_height  # 1.6 aspect ratio (0.625)

    # Attempt to remove AI watermark (Gemini sparkle) first
    cleaned_img = None
    try:
        import cv2
        from remove_ai_watermarks.gemini_engine import GeminiEngine
        
        cv_img = cv2.imread(source_path)
        if cv_img is not None:
            engine = GeminiEngine()
            processed_cv = engine.remove_watermark(cv_img)
            cleaned_rgb = cv2.cvtColor(processed_cv, cv2.COLOR_BGR2RGB)
            cleaned_img = Image.fromarray(cleaned_rgb)
    except Exception:
        pass

    if cleaned_img is not None:
        img = cleaned_img
        img = img.convert("RGB")
        width, height = img.size
        current_ratio = width / height
        
        if current_ratio > target_ratio:
            new_height = target_height
            new_width = int(new_height * current_ratio)
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - target_width) // 2
            right = left + target_width
            img_final = img_resized.crop((left, 0, right, target_height))
        else:
            new_width = target_width
            new_height = int(new_width / current_ratio)
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            top = (new_height - target_height) // 2
            bottom = top + target_height
            img_final = img_resized.crop((0, top, target_width, bottom))
            
        img_final.save(dest_path, "JPEG", quality=90, dpi=(300, 300))
    else:
        with Image.open(source_path) as img:
            # Convert to RGB color space
            img = img.convert("RGB")
            
            # Calculate current aspect ratio
            width, height = img.size
            current_ratio = width / height
            
            if current_ratio > target_ratio:
                # Image is too wide (aspect ratio is larger than 0.625)
                # Resize based on height, then crop sides
                new_height = target_height
                new_width = int(new_height * current_ratio)
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Crop horizontally from center
                left = (new_width - target_width) // 2
                right = left + target_width
                img_final = img_resized.crop((left, 0, right, target_height))
            else:
                # Image is too tall (aspect ratio is smaller than 0.625)
                # Resize based on width, then crop top/bottom
                new_width = target_width
                new_height = int(new_width / current_ratio)
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Crop vertically from center
                top = (new_height - target_height) // 2
                bottom = top + target_height
                img_final = img_resized.crop((0, top, target_width, bottom))
                
            # Save as JPEG with 300 DPI
            img_final.save(dest_path, "JPEG", quality=90, dpi=(300, 300))

    # Enforce 5MB limit
    max_size_bytes = 5 * 1024 * 1024  # 5MB
    file_size = os.path.getsize(dest_path)
    if file_size > max_size_bytes:
        # Fallback to lower quality compression (quality=75)
        with Image.open(dest_path) as saved_img:
            saved_img.save(dest_path, "JPEG", quality=75, dpi=(300, 300))
        
        file_size = os.path.getsize(dest_path)
        if file_size > max_size_bytes:
            # If still too large, clean up and raise error
            try:
                os.remove(dest_path)
            except OSError:
                pass
            raise ValueError(
                f"Generated KDP cover image file size ({file_size / (1024 * 1024):.2f}MB) "
                f"exceeds the 5MB limit even after quality reduction."
            )


def is_kdp_compliant(file_path: str) -> bool:
    """
    Checks if a local image file meets Amazon KDP ebook cover criteria:
    - Format: JPEG
    - Dimensions: Exactly 1600 x 2560 pixels
    - Mode: RGB
    - Size: <= 5 MB (5,242,880 bytes)
    """
    if not os.path.exists(file_path):
        return False
        
    # Check file size first (avoid loading huge files into memory)
    try:
        if os.path.getsize(file_path) > 5 * 1024 * 1024:
            return False
    except OSError:
        return False
        
    # Check format, dimensions, mode using Pillow
    try:
        with Image.open(file_path) as img:
            if img.format not in ("JPEG", "MPO"):
                return False
            if img.size != (1600, 2560):
                return False
            if img.mode != "RGB":
                return False
            # Check DPI (if present, must be 300)
            dpi = img.info.get("dpi")
            if dpi:
                if round(dpi[0]) != 300 or round(dpi[1]) != 300:
                    return False
    except Exception:
        return False
        
    return True
