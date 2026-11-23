"""Launcher: the code is sg/views/locus_view.py (run it here as before)."""
if __name__ == "__main__":
    import runpy
    from pathlib import Path
    runpy.run_path(str(Path(__file__).resolve().parent / "sg" / "views" / "locus_view.py"), run_name="__main__")
