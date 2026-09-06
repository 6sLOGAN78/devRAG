import sys
try:
    import infinity
    from infinity.common import ConflictType
    from infinity.index import IndexInfo, IndexType
    import infinity.connection_pool
    print("Infinity SDK imported successfully!")
    print(dir(infinity))
except Exception as e:
    print(f"Error: {e}")
