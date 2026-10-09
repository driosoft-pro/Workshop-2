# Merge into config/superset_config.py ONLY after upgrading the image to Superset >= 6.0
# (native light/dark themes do not exist in 4.1.x; there the bootstrap uses CSS templates).
#
# With both themes defined, Superset follows the OS preference and users can switch it in
# the UI. Keep the brand tokens in both dicts: a partial override replaces the whole dict.

_BRAND = {
    "brandLogoUrl": "/static/assets/images/superset-logo-horiz.png",
    "brandLogoHref": "/",
}

THEME_DEFAULT = {
    "token": {**_BRAND, "colorPrimary": "#C9A227", "colorLink": "#8A6D0B"},
}

THEME_DARK = {
    "algorithm": "dark",
    "token": {**_BRAND, "colorPrimary": "#E5C158", "colorLink": "#E5C158"},
}
