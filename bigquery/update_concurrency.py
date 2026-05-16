with open("control_center/src/screens/generation_screen.py", "r") as f:
    code = f.read()

old_block = """                            if "too many concurrent queries" in error_msg or "rate limit" in error_msg or "exceeded rate limits" in error_msg:
                                self.write_log(f"Rate limit hit for worker {i}. Retrying after a short delay...\\n")"""

new_block = """                            if "too many concurrent queries" in error_msg or "rate limit" in error_msg or "exceeded rate limits" in error_msg or "could not serialize access" in error_msg or "concurrent update" in error_msg:
                                self.write_log(f"Concurrency/Rate limit hit for worker {i}. Retrying after a short delay...\\n")"""

if old_block in code:
    code = code.replace(old_block, new_block)
    with open("control_center/src/screens/generation_screen.py", "w") as f:
        f.write(code)
    print("Updated successfully!")
else:
    print("Block not found!")
