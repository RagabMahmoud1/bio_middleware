import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
def setup_logging(path, level="INFO"):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    root=logging.getLogger(); root.setLevel(getattr(logging,level.upper(),logging.INFO)); root.handlers.clear()
    fmt=logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    fh=RotatingFileHandler(p,maxBytes=5_000_000,backupCount=5,encoding="utf-8"); fh.setFormatter(fmt); root.addHandler(fh)
    sh=logging.StreamHandler(); sh.setFormatter(fmt); root.addHandler(sh)
