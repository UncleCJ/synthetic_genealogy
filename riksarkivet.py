"""Launcher: the code is sg/records/riksarkivet.py (run it here as before)."""
if __name__ == "__main__":
    import runpy
    from pathlib import Path
    runpy.run_path(str(Path(__file__).resolve().parent / "sg" / "records" / "riksarkivet.py"), run_name="__main__")
