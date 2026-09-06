from peewee import Model, CharField, DateTimeField
import datetime
from .connection import db

class BaseModel(Model):
    class Meta:
        database = db

class Tenant(BaseModel):
    id = CharField(max_length=36, primary_key=True)
    name = CharField(max_length=255, null=False)
    llm_id = CharField(max_length=255, null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    
    class Meta:
        table_name = 'tenant'

class User(BaseModel):
    id = CharField(max_length=36, primary_key=True)
    email = CharField(max_length=255, null=False, unique=True)
    password_hash = CharField(max_length=255, null=False)
    nickname = CharField(max_length=255, null=True)
    
    class Meta:
        table_name = 'user'

class UserTenant(BaseModel):
    user_id = CharField(max_length=36, null=False)
    tenant_id = CharField(max_length=36, null=False)
    role = CharField(max_length=255, null=False) # Enum validation handled at service layer typically, or we can enforce constraints
    
    class Meta:
        table_name = 'user_tenant'
        indexes = (
            (('user_id', 'tenant_id'), True), # Unique constraint
        )

class Dataset(BaseModel):
    id = CharField(max_length=36, primary_key=True)
    name = CharField(max_length=255, null=False)
    description = CharField(max_length=1000, null=True)
    tenant_id = CharField(max_length=36, null=False)
    created_by = CharField(max_length=36, null=False)
    status = CharField(max_length=50, null=False, default='active')
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = 'dataset'

class Document(BaseModel):
    id = CharField(max_length=36, primary_key=True)
    dataset_id = CharField(max_length=36, null=False)
    tenant_id = CharField(max_length=36, null=False)
    name = CharField(max_length=255, null=False)
    size = CharField(max_length=20, null=False) # storing int as str to avoid 64bit issues in simple ORM
    type = CharField(max_length=100, null=False)
    minio_path = CharField(max_length=500, null=False)
    parse_status = CharField(max_length=50, null=False, default='pending')
    created_by = CharField(max_length=36, null=False)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = 'document'
