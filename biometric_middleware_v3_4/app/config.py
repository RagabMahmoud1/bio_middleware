from pathlib import Path
import yaml
BASE_DIR = Path(__file__).resolve().parent.parent
def load_config():
    p=BASE_DIR/"config.yaml"
    with p.open("r",encoding="utf-8") as f: cfg=yaml.safe_load(f) or {}
    app=cfg.setdefault("app",{})
    for key in ("database_path","log_path"):
        v=app.get(key)
        if v:
            pp=Path(v)
            if not pp.is_absolute(): app[key]=str(BASE_DIR/pp)
    return cfg
