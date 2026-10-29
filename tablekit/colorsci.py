"""Colour science helpers: sRGB <-> CIELAB, CIEDE2000, colour-vision-deficiency
simulation and plain-language colour names. Standard library only."""

import math

# --- conversions -----------------------------------------------------------

def hex_to_rgb(hex_str):
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"not a hex colour: {hex_str!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def _to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c):
    c = max(0.0, min(1.0, c))
    v = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return v * 255.0


_WHITE = (0.95047, 1.0, 1.08883)  # D65


def rgb_to_lab(rgb):
    r, g, b = (_to_linear(c) for c in rgb)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x / _WHITE[0]), f(y / _WHITE[1]), f(z / _WHITE[2])
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lab_to_rgb(lab):
    L, a, b = lab
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    def finv(t):
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)

    x, y, z = finv(fx) * _WHITE[0], finv(fy) * _WHITE[1], finv(fz) * _WHITE[2]
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bl = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return tuple(_from_linear(c) for c in (r, g, bl))


def hex_to_lab(hex_str):
    return rgb_to_lab(hex_to_rgb(hex_str))


def lab_to_hex(lab):
    return rgb_to_hex(lab_to_rgb(lab))


def lab_to_lch(lab):
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


# --- colour difference -----------------------------------------------------

def delta_e2000(lab1, lab2):
    """CIEDE2000 colour difference (Sharma et al. 2005)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + G), a2 * (1 + G)
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0

    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2

    T = (1 - 0.17 * math.cos(math.radians(hbp - 30))
         + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6))
         - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def contrast_ratio(hex1, hex2):
    """WCAG relative-luminance contrast ratio (1..21)."""
    def lum(h):
        r, g, b = (_to_linear(c) for c in hex_to_rgb(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    l1, l2 = sorted((lum(hex1), lum(hex2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


# --- colour-vision deficiency ---------------------------------------------

# Machado, Oliveira & Fernandes (2009), severity 1.0, applied in linear RGB.
CVD_MATRICES = {
    "protanopia": ((0.152286, 1.052583, -0.204868),
                   (0.114503, 0.786281, 0.099216),
                   (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968),
                     (0.280085, 0.672501, 0.047413),
                     (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779),
                   (-0.078411, 0.930809, 0.147602),
                   (0.004733, 0.691367, 0.303900)),
}


def simulate_cvd(hex_str, kind):
    lin = [_to_linear(c) for c in hex_to_rgb(hex_str)]
    m = CVD_MATRICES[kind]
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return rgb_to_hex(_from_linear(c) for c in out)


# --- naming -----------------------------------------------------------------

_HUES = [  # (upper hue bound in CIELAB degrees, light name, mid name, dark name)
    (15, "pink", "raspberry", "berry"),
    (45, "coral", "red", "brick"),
    (70, "peach", "orange", "terracotta"),
    (85, "apricot", "amber", "caramel"),
    (105, "butter yellow", "yellow", "mustard"),
    (135, "pistachio", "lime", "olive"),
    (165, "mint green", "leaf green", "forest green"),
    (200, "mint", "jade", "deep green"),
    (235, "aqua", "teal", "deep teal"),
    (285, "sky blue", "blue", "navy"),
    (300, "periwinkle", "violet", "indigo"),
    (345, "lilac", "orchid", "plum"),
    (361, "pink", "raspberry", "berry"),
]


def color_name(hex_str):
    """A rough, human-friendly name such as 'dusty sage' or 'deep teal'."""
    L, C, h = lab_to_lch(hex_to_lab(hex_str))
    if C < 10:
        tone = "warm " if C >= 3 and 20 <= h <= 110 else ("cool " if C >= 3 else "")
        if L > 92:
            return "white"
        if L > 80:
            return "oatmeal" if tone == "warm " else f"{tone}light grey".strip()
        if L > 45:
            return "greige" if tone == "warm " else f"{tone}grey".strip()
        if L > 20:
            return f"{tone}charcoal".strip()
        return "black"
    for bound, light, mid, dark in _HUES:
        if h < bound:
            break
    if 40 <= h < 85 and L < 45 and C < 45:
        return "chocolate brown" if L < 35 else "mocha"
    if 105 <= h < 165 and C < 25 and L >= 55:
        return "sage" if L < 80 else "pale sage"
    if 45 <= h < 70 and 40 <= L < 65 and C < 55:
        return "terracotta"
    base = light if L >= 72 else (mid if L >= 35 else dark)
    if C < 22:
        prefix = "dusty " if L < 75 else "pale "
    elif C > 60:
        prefix = "bright "
    else:
        prefix = ""
    return (prefix + base).strip()
