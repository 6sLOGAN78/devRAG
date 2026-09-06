from minio import Minio
from common.settings import load_config
import os

class StorageService:
    def __init__(self):
        cfg = load_config('conf/service_conf.yaml')
        self.client = Minio(
            cfg.minio.endpoint,
            access_key=cfg.minio.access_key,
            secret_key=cfg.minio.secret_key,
            secure=False
        )
    
    def download_file(self, bucket_name: str, object_name: str, file_path: str):
        self.client.fget_object(bucket_name, object_name, file_path)

storage_service = StorageService()
