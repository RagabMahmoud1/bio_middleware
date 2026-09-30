# Middleware v3.4 - employee filter handling

- Compatible with Odoo bridge v1.2 employee validation.
- Odoo accepted events -> local `synced`.
- Odoo unknown/ambiguous employee events -> local `ignored` and never retried.
- Keeps the production go-live cutoff protection.
- Includes the ZKTeco +03:00 timezone patch.
