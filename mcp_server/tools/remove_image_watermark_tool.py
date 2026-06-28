import os

import cv2
from remove_ai_watermarks.gemini_engine import GeminiEngine

from mcp_server.mcp_server import server


@server.register_tool(name='remove_image_watermark', description='Removes AI watermarks (such as the Nano Banana logo or Gemini sparkle) from a standalone image file.', schema={'type': 'object', 'properties': {'source_filename': {'type': 'string', 'description': 'Absolute path to the source image file to be cleaned.'}, 'target_filename': {'type': 'string', 'description': 'Absolute path to where the watermark-free image should be saved.'}}, 'required': ['source_filename', 'target_filename']})
def remove_image_watermark_tool(source_filename: str, target_filename: str) -> dict:
    try:
        src_path = os.path.expanduser(source_filename)
        dest_path = os.path.expanduser(target_filename)
        if not os.path.exists(src_path):
            return {'content': [{'type': 'text', 'text': f"Error: Source file does not exist at '{src_path}'"}], 'isError': True}
        cv_img = cv2.imread(src_path)
        if cv_img is None:
            return {'content': [{'type': 'text', 'text': f"Error: Failed to read image from '{src_path}'. Ensure it is a valid image format."}], 'isError': True}
        target_dir = os.path.dirname(dest_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        engine = GeminiEngine()
        processed_cv = engine.remove_watermark(cv_img)
        success = cv2.imwrite(dest_path, processed_cv)
        if not success:
            return {'content': [{'type': 'text', 'text': f"Error: Failed to save the processed image to '{dest_path}'"}], 'isError': True}
        return {'content': [{'type': 'text', 'text': f"Successfully removed watermark from '{src_path}' and saved the cleaned image to '{dest_path}'."}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error removing watermark: {str(e)}'}], 'isError': True}
