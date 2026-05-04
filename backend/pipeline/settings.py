"""Configuration values for backend pipeline preparation."""

ORDERED_VIEW_NAMES = [
    "front",
    "back",
    "left",
    "right",
    "top",
    "bottom",
    "iso_top_left",
    "iso_top_right",
]
RGB_SUFFIX_BLACKLIST = ("_seg", "_depth", "_normal")
SEND_IMAGES_TO_AGENT = True

