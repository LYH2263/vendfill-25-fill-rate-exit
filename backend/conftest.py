import os

# 必须在导入 app.* 之前设置：database.py 在导入时即按此 URL 建引擎。
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_EMPTY", "false")
