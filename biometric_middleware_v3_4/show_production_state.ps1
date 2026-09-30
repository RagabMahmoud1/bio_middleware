Set-Location $PSScriptRoot
& ".\.venv\Scripts\python.exe" -c "from app.config import load_config; from app.db import Database; c=load_config(); d=Database(c['app']['database_path']); p=d.get_setting('go_live_at'); x=c.get('sync',{}).get('go_live_at'); print('Persisted go_live_at =', p if p else '<not initialized yet>'); print('Configured go_live_at =', x if x else '<missing>')"
