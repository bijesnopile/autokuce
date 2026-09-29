"""Inline SVG icon paths (24x24, stroke based, Feather/Lucide/Tabler style — MIT/ISC).

Use in templates via the `icon(name)` macro from `_icons.html`. Adding an
icon = adding one entry here. No external icon fonts or sprites.
"""

ICONS: dict[str, str] = {
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 '
    "19.8 19.8 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 "
    "1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 "
    '0 0 1 22 16.92z"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "map-pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/>'
    '<circle cx="12" cy="10" r="3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "menu": '<path d="M3 6h18M3 12h18M3 18h18"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m18 15-6-6-6 6"/>',
    "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "arrow-left": '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
    "filter": '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "facebook": '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/>',
    "instagram": '<rect x="2" y="2" width="20" height="20" rx="5"/>'
    '<path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37zM17.5 6.5h.01"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4 12 14.01l-3-3"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "shield-check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "award": '<circle cx="12" cy="8" r="7"/><path d="M8.21 13.89 7 23l5-3 5 3-1.21-9.12"/>',
    "star": '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 '
    '9.27l6.91-1.01L12 2z"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "printer": '<path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 '
    '2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
    "play": '<path d="m6 3 14 9-14 9V3z"/>',
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "tag": '<path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 '
    '2.82z"/><path d="M7 7h.01"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 '
    '0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "chart": '<path d="M18 20V10M12 20V4M6 20v-6"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
    '<path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 '
    "2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 "
    "0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 "
    "1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 "
    "0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 "
    "1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 "
    "2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 "
    '1.65 0 0 0-1.51 1z"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "server": '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" '
    'height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>'
    '<path d="m21 15-5-5L5 21"/>',
    "trash": '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 '
    '0 1 2 2v2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "edit": '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    "grip": '<circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" '
    'r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" '
    'cy="19" r="1"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "alert": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 '
    '0 0 0-3.42 0zM12 9v4M12 17h.01"/>',
    "external": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 '
    '14 21 3"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 '
    '2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "send": '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/>',
    "refresh": '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 '
    '14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "maximize": '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M16 21h3a2 2 0 0 0 '
    '2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "fuel": '<path d="M3 22h12M4 9h10M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18"/>'
    '<path d="M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 4 0V9.83a2 2 0 0 0-.59-1.42L18 5"/>',
    "gearbox": '<circle cx="5" cy="5" r="2"/><circle cx="12" cy="5" r="2"/><circle cx="19" cy="5" '
    'r="2"/><circle cx="5" cy="19" r="2"/><circle cx="12" cy="19" r="2"/>'
    '<path d="M5 7v10M12 7v10M19 7v5H5"/>',
    "car": '<path d="M5 17H3v-5l2.2-5.2A2 2 0 0 1 7.04 5.5h9.92a2 2 0 0 1 1.84 1.3L21 12v5h-2"/>'
    '<circle cx="7.5" cy="17" r="2"/><circle cx="16.5" cy="17" r="2"/><path d="M9.5 17h5M3 12h18"/>',
    "van": '<path d="M2 17V7a2 2 0 0 1 2-2h11l5 5h1a1 1 0 0 1 1 1v6h-2"/><circle cx="7" cy="17" '
    'r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 17h6M15 5v5h5"/>',
    "motorcycle": '<circle cx="5" cy="17" r="3"/><circle cx="19" cy="17" r="3"/>'
    '<path d="M5 17h5l3-5h3l3 5M13 12l-2-4H8M16 12l-1-4h3"/>',
    "camper": '<path d="M2 17V6a1 1 0 0 1 1-1h13a4 4 0 0 1 4 4v1l2 2v5h-2"/><circle cx="7" cy="17" '
    'r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 17h6M5 8h4v3H5zM12 8h4v3h-4z"/>',
    "truck": '<path d="M1 3h15v13H1zM16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/>'
    '<circle cx="18.5" cy="18.5" r="2.5"/>',
    "heart": '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 '
    '7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78z"/>',
    "handshake": '<path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-'
    "3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 "
    '0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3M3 4h8"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 '
    '7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "log-in": '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>',
    "smartphone": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7l10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>',
    "rss": '<path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/>',
    "calculator": '<rect x="4" y="2" width="16" height="20" rx="2"/>'
    '<path d="M8 6h8M16 14v4M16 10h.01M12 10h.01M8 10h.01M12 14h.01M8 14h.01M12 18h.01M8 18h.01"/>',
    # Brand-like glyphs (Tabler-style outlines), used with the service name as text.
    "whatsapp": '<path d="m3 21 1.65-3.8a9 9 0 1 1 3.4 2.9L3 21"/>'
    '<path d="M9 10a.5.5 0 0 0 1 0V9a.5.5 0 0 0-1 0v1a5 5 0 0 0 5 5h1a.5.5 0 0 0 0-1h-1a.5.5 0 0 0 0 1"/>',
    "viber": '<path d="M5 18.5c-2.5-2.2-2.5-10.8 0-13 2.5-2.2 11.5-2.2 14 0 2.5 2.2 2.5 10.8 0 13-1.7 1.5-5.3 '
    '2-8.5 1.4L7 22v-3.1"/><path d="M12 7.5a3.5 3.5 0 0 1 3.5 3.5M12 5a6 6 0 0 1 6 6"/>'
    '<path d="M9.5 9.5c.3 1.9 1.6 3.5 3.5 4.5l1-1 1.5 1-.5 1.5c-2.9-.2-5.8-3-6-6l1.5-.5 1 1.5-1 1z"/>',
    "calendar-check": '<rect x="3" y="4" width="18" height="18" rx="2"/>'
    '<path d="M16 2v4M8 2v4M3 10h18M9 16l2 2 4-4"/>',
}
