import sys
import peewee
from .connection import db
from .db_models import Tenant, User, UserTenant

def main():
    db.connect()
    
    # Verify Go data exists
    t_go = Tenant.get(Tenant.id == 't-go')
    assert t_go.name == 'Go Tenant'
    
    # Insert Python data
    Tenant.create(id='t-py', name='Python Tenant')
    User.create(id='u-py', email='py@devrag.local', password_hash='hash')
    UserTenant.create(user_id='u-py', tenant_id='t-py', role='admin')
    
    # Test unique constraint on email
    try:
        User.create(id='u-py-2', email='py@devrag.local', password_hash='hash')
        sys.exit("Failed: Email unique constraint not enforced")
    except peewee.IntegrityError:
        pass
        
    # Test composite unique constraint on UserTenant
    try:
        UserTenant.create(user_id='u-py', tenant_id='t-py', role='invite')
        sys.exit("Failed: UserTenant unique constraint not enforced")
    except peewee.IntegrityError:
        pass

    print("Python reading, insertion, and constraints successful.")

if __name__ == '__main__':
    main()
