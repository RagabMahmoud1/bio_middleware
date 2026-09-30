from abc import ABC,abstractmethod
class DeviceAdapter(ABC):
    def __init__(self,cfg): self.cfg=cfg; self.device_id=cfg["id"]
    @abstractmethod
    def test_connection(self): ...
    @abstractmethod
    def fetch_events(self): ...
