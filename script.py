import os
from dotenv import load_dotenv

result = load_dotenv()
print("Loaded:", result)          # True = found .env, False = didn't find it
print(os.getenv("DATABASE_URL"))