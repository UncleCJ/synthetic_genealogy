"""Launcher: the code is sg/records/other_trees.py."""
if __name__ == "__main__":
    import runpy
    from pathlib import Path
    runpy.run_path(str(Path(__file__).resolve().parent / "sg" / "records" / "other_trees.py"), run_name="__main__")
