"""
Sample Certificate & Test Data Generator
Generates realistic sample certificates for testing:
  1. sample_genuine_st.jpg   (Genuine ST Certificate with verified QR code)
  2. sample_tampered_fake.jpg (Photoshopped with mismatched pixel compression)
  3. sample_non_st.jpg       (Claims non-ST caste)
"""

from pathlib import Path
from PIL import Image, ImageDraw
import json
import hashlib
import qrcode

DATA_DIR = Path(__file__).resolve().parent.parent / "sample_docs"
DATA_DIR.mkdir(exist_ok=True)

def create_sample_certificates():
    # 1. Official Signed Payload for QR
    cert_no = "JH/2024/ST/84920"
    mock_sig = hashlib.sha256(f"GOVT_MOCK_SALT_{cert_no}".encode()).hexdigest()[:16]
    
    qr_payload = {
        "cert_no": cert_no,
        "name": "Rahul Munda",
        "father_name": "Birsa Munda",
        "caste": "Munda",
        "category": "ST",
        "state": "Jharkhand",
        "annual_income": 45000,
        "digital_signature": mock_sig
    }

    # Generate real scannable QR Code
    # Generate real scannable QR Code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=3,
    )
    qr.add_data(json.dumps(qr_payload))
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    # Base Genuine Certificate (Rahul Munda, ST Tribe: Munda)
    img_genuine = Image.new('RGB', (800, 1050), color=(252, 252, 250))
    draw = ImageDraw.Draw(img_genuine)
    
    # Border & Header
    draw.rectangle([(20, 20), (780, 1030)], outline=(10, 37, 64), width=3)
    draw.rectangle([(26, 26), (774, 1024)], outline=(180, 190, 200), width=1)
    
    draw.text((260, 50), "GOVERNMENT OF JHARKHAND", fill=(10, 37, 64))
    draw.text((275, 75), "Office of the Sub-Divisional Officer", fill=(50, 60, 70))
    draw.text((250, 110), "SCHEDULED TRIBE CERTIFICATE", fill=(16, 149, 193))
    
    draw.text((50, 180), f"Certificate No: {cert_no}", fill=(20, 20, 20))
    draw.text((550, 180), "Date: 12-Feb-2024", fill=(20, 20, 20))
    
    body_text = (
        "This is to certify that Shri RAHUL MUNDA son of Shri BIRSA MUNDA\n"
        "of Village: RAMPUR, Post: BARHI, Thana: BARHI, District: HAZARIBAGH\n"
        "in the State of Jharkhand belongs to the MUNDA community which is\n"
        "recognized as a Scheduled Tribe under the Constitution (Scheduled Tribes)\n"
        "Order, 1950 as amended from time to time.\n\n"
        "Shri Rahul Munda and his family ordinarily reside in the Hazaribagh\n"
        "District of the State of Jharkhand.\n\n"
        "Annual Family Income: Rs. 45,000 (Forty Five Thousand Only)"
    )
    draw.multiline_text((50, 240), body_text, fill=(30, 30, 30), spacing=12)
    
    # Signature & Seal Area
    draw.text((50, 850), "Seal of the Issuing Authority", fill=(120, 130, 140))
    draw.text((500, 885), "Sub-Divisional Officer (SDO)", fill=(10, 37, 64))
    draw.text((500, 910), "Digital Signature Verified [OK]", fill=(16, 185, 129))
    
    # Paste actual real scannable QR Code
    img_genuine.paste(qr_img, (490, 600))
    
    genuine_path = DATA_DIR / "sample_genuine_st.jpg"
    img_genuine.save(genuine_path, "JPEG", quality=95)

    # 2. Tampered / Photoshopped Fake Certificate
    img_fake = img_genuine.copy()
    draw_fake = ImageDraw.Draw(img_fake)
    
    # Spliced text over income with high contrast anomaly
    draw_fake.rectangle([(220, 420), (380, 450)], fill=(255, 255, 255))
    draw_fake.text((225, 425), "Rs. 15,000 (Fifteen Thousand)", fill=(0, 0, 0))
    
    # Scratch/tamper across the QR area
    draw_fake.line([(490, 600), (750, 860)], fill=(255, 0, 0), width=16)
    draw_fake.line([(490, 860), (750, 600)], fill=(255, 0, 0), width=16)
    
    fake_path = DATA_DIR / "sample_tampered_fake.jpg"
    img_fake.save(fake_path, "JPEG", quality=95)

    # 3. Non-ST Certificate
    non_st_qr_payload = {
        "cert_no": "JH/2024/OBC/19284",
        "name": "Rahul Kushwaha",
        "caste": "Kushwaha",
        "category": "OBC",
        "digital_signature": "mock_sig_obc"
    }
    qr_non = qrcode.QRCode(box_size=5, border=3)
    qr_non.add_data(json.dumps(non_st_qr_payload))
    qr_non.make(fit=True)
    qr_non_img = qr_non.make_image(fill_color="black", back_color="white").convert('RGB')

    img_non_st = img_genuine.copy()
    draw_non = ImageDraw.Draw(img_non_st)
    draw_non.rectangle([(40, 100), (700, 140)], fill=(252, 252, 250))
    draw_non.text((250, 110), "OTHER BACKWARD CLASS (OBC) CERTIFICATE", fill=(180, 40, 40))
    
    draw_non.rectangle([(40, 280), (700, 360)], fill=(252, 252, 250))
    non_st_text = (
        "belongs to the KUSHWAHA community which is recognized as an\n"
        "Other Backward Class (OBC) and NOT a Scheduled Tribe."
    )
    draw_non.multiline_text((50, 290), non_st_text, fill=(30, 30, 30), spacing=12)
    draw_non.rectangle([(490, 600), (760, 870)], fill=(252, 252, 250))
    img_non_st.paste(qr_non_img, (490, 600))
    
    non_st_path = DATA_DIR / "sample_non_st.jpg"
    img_non_st.save(non_st_path, "JPEG", quality=95)

    print(f"Realistic sample certificates updated at: {DATA_DIR}")

if __name__ == "__main__":
    create_sample_certificates()
