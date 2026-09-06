import sys
import os

# Add the project root to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.db.connection import db
from api.db.db_models import AgentCanvas

def main():
    db.connect()
    db.create_tables([AgentCanvas], safe=True)
    print("Successfully migrated AgentCanvas table.")
    db.close()

if __name__ == '__main__':
    main()
