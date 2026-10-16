"""Create each service's .env from its .env.example if it doesn't exist yet. Never overwrites."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
for example in root.glob("**/.env.example"):
    target = example.with_name(".env")
    if target.exists():
        print(f"exists   {target.relative_to(root)}")
    else:
        target.write_text(example.read_text())
        print(f"created  {target.relative_to(root)}  (fill in your keys)")
