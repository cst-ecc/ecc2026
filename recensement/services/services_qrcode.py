"""Service de génération des QR codes officiels des paroisses."""

from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def generer_qrcode_png(contenu):
    """Retourne un QR code PNG sous forme d'octets."""

    contenu = (contenu or "").strip()

    if not contenu:
        raise ValueError("Le contenu du QR code ne peut pas être vide.")

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )

    qr.add_data(contenu)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")

    return buffer.getvalue()
